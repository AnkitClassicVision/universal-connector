"""Command line entry point: `uconnector`.

Commands: serve, connect, revoke, rotate, list, set-tools, doctor, check, login, pause, resume,
reload, install-service and smoke. Every error text is fixed or built from names; none echoes a
value.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import yaml

from universal_connector import portable
from universal_connector.adapters import DEFAULT_URL
from universal_connector.manifest import ManifestError, load_manifest
from universal_connector.scan import RULES, find_secrets
from universal_connector.vault import store_for

ALLOW_FILE = "scan-allow.yaml"
SERVE_EXIT_LINE = "the front door stopped on an exit request"
SKIP_DIRS = {".git", ".venv", "__pycache__", ".ruff_cache", ".pytest_cache", "node_modules"}
RELOAD_WAIT_S = 15.0
RELOAD_WAIT_MAX_S = 120.0
NO_STATE_HERE = "no door state in that folder; nothing to reload"
NO_DOOR_ANSWERED = (
    "no door answered in time; a door still starting applies the request when it is up, "
    "and a door started later reads the files when it starts"
)


def _repo_files(root: Path) -> list[str]:
    """Git-tracked plus untracked-but-not-ignored files. Outside Git, every file but tool folders."""
    try:
        result = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            cwd=root, capture_output=True, check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        files = []
        for folder, dirs, names in os.walk(root):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for name in names:
                files.append((Path(folder) / name).relative_to(root).as_posix())
        return sorted(files)
    return sorted({n for n in result.stdout.decode("utf-8", "surrogateescape").split("\0") if n})


def _read_text(path: Path) -> str | None:
    if not path.is_file():
        return None
    data = path.read_bytes()
    if b"\0" in data[:8192]:
        return None
    return data.decode("utf-8", errors="replace")


def _load_allow(root: Path) -> tuple[dict[str, set[str]], list[str]]:
    """`scan-allow.yaml`: files that hold deliberate fake secrets, each with the rules it may hit."""
    path = root / ALLOW_FILE
    if not path.is_file():
        return {}, []
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return {}, [f"{ALLOW_FILE}: not valid YAML"]
    allow: dict[str, set[str]] = {}
    problems: list[str] = []
    entries = data.get("allow") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        return {}, [f"{ALLOW_FILE}: allow must be a list"]
    for index, entry in enumerate(entries):
        ok = (
            isinstance(entry, dict)
            and isinstance(entry.get("path"), str)
            and bool(entry["path"].strip())
            and isinstance(entry.get("rules"), list)
            and bool(entry["rules"])
            and all(isinstance(rule, str) and rule in RULES for rule in entry["rules"])
            and isinstance(entry.get("why"), str)
            and bool(entry["why"].strip())
        )
        if not ok:
            problems.append(
                f"{ALLOW_FILE}: entry {index} needs path, a non-empty list of known rules and why"
            )
            continue
        if not (root / entry["path"]).exists():
            problems.append(f"{ALLOW_FILE}: entry {index} path does not exist: {entry['path']}")
            continue
        allow.setdefault(entry["path"], set()).update(entry["rules"])
    return allow, problems


def _root() -> Path:
    """The Git top level, or the current folder when there is no repo."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"], capture_output=True, check=True, text=True
        )
    except (OSError, subprocess.CalledProcessError):
        return Path.cwd()
    top = result.stdout.strip()
    return Path(top) if top else Path.cwd()


def _check(manifest_dir: Path | None) -> int:
    root = _root()
    problems: list[str] = []
    try:
        load_manifest(manifest_dir if manifest_dir is not None else root / "manifest")
    except ManifestError as err:
        problems.extend(f"manifest: {p}" for p in err.problems)
    allow, allow_problems = _load_allow(root)
    problems.extend(allow_problems)
    for rel in _repo_files(root):
        text = _read_text(root / rel)
        if text is None:
            continue
        for rule in find_secrets(text):
            if rule not in allow.get(rel, set()):
                problems.append(f"{rel}: {rule}")
    if problems:
        for problem in problems:
            print(problem)
        return 1
    print("ok")
    return 0


def _set_paused(state: Path, paused: bool) -> int:
    from universal_connector.audit import set_paused

    set_paused(state, paused)
    print("paused" if paused else "resumed")
    return 0


def _machine_or_none(path: Path | None = None) -> dict | None:
    """The checked machine settings, or None after fixed lines. A value is never shown."""
    from universal_connector import machine as settings

    try:
        machine = settings.load_machine(path)
    except settings.MachineFileMissing as err:  # fixed text: a named file must exist
        print(err, file=sys.stderr)
        return None
    except (ValueError, yaml.YAMLError, OSError, UnicodeDecodeError):
        print("the machine file is not a valid mapping", file=sys.stderr)
        return None
    problems = settings.problems(machine)
    for problem in problems:
        print(problem, file=sys.stderr)
    return None if problems else machine


def _serve(manifest: Path, state: Path, host: str, port: int, machine_file: Path | None) -> int:
    import asyncio

    from universal_connector import frontdoor
    from universal_connector.machine import door_hosts

    try:
        frontdoor.check_bind(host, port)
    except ValueError as err:  # one fixed line, never a traceback
        print(err, file=sys.stderr)
        return 2
    machine = _machine_or_none(machine_file)
    if machine is None:
        return 2
    try:
        extra_hosts = door_hosts(machine)
        store = store_for(machine)
    except ValueError as err:  # fixed text, never the entry
        print(err, file=sys.stderr)
        return 2
    try:
        holder = frontdoor.Holder(manifest, state, store, machine_file=machine_file)
    except ManifestError as err:
        for problem in err.problems:
            print(f"manifest: {problem}", file=sys.stderr)
        return 1
    try:
        asyncio.run(frontdoor.serve(holder, state, host, port, extra_hosts))
    except KeyboardInterrupt:
        pass
    except SystemExit:  # its text can quote a request value: one fixed line instead
        print(SERVE_EXIT_LINE, file=sys.stderr)
        return 1
    return 0


def _fail(message: str, code: int) -> int:
    print(message, file=sys.stderr)
    return code


def _load_or_report(manifest_dir: Path):
    """The manifest, or None after the problems are printed. Problems never echo a value."""
    try:
        return load_manifest(manifest_dir)
    except ManifestError as err:
        for problem in err.problems:
            print(f"manifest: {problem}", file=sys.stderr)
        return None


def _replace_agents(manifest_dir: Path, agents: list) -> bool:
    """Write `agents.yaml` atomically, load the whole manifest again, and undo on any fault."""
    from universal_connector import adapters

    old = adapters.read_agents_bytes(manifest_dir)
    try:
        adapters.write_agents_bytes(manifest_dir, adapters.render_agents(agents))
        load_manifest(manifest_dir)
    except (OSError, ManifestError):
        adapters.write_agents_bytes(manifest_dir, old)
        return False
    return True


def _parse_connect(args) -> tuple | int:
    """Validate everything before any change. Return (grant, url) or an exit code.

    `--format oddboro` shows the agent the 5 fixed tools only unless `--pinned` is given, and
    gives it a 40 second budget per call, retry included, so the door answers inside Oddboro's
    own wait.
    """
    from universal_connector import adapters
    from universal_connector.manifest import AGENT_NAME, _check_agent
    from universal_connector.models import AddOn, AgentGrant, Reach, Scope

    if not AGENT_NAME.fullmatch(args.name):
        return _fail(f"agent name must match {AGENT_NAME.pattern}", 2)
    reach_text, scopes_text = args.reach, args.scopes
    if reach_text is None or scopes_text is None:
        if not sys.stdin.isatty():
            return _fail("--reach and --scopes are required when there is no terminal", 2)
        if reach_text is None:
            reach_text = input("reach (starter or full-read): ").strip()
        if scopes_text is None:
            scopes_text = input("scopes (work, personal): ").strip()
    try:
        reach = Reach(reach_text)
    except ValueError:
        return _fail("reach must be starter or full-read", 2)
    try:
        scopes = {Scope(s.strip()) for s in scopes_text.split(",") if s.strip()}
        addons = {AddOn(a.strip()) for a in (args.addons or "").split(",") if a.strip()}
    except ValueError:
        return _fail("unknown scope or add-on", 2)
    if not scopes:
        return _fail("at least one scope is needed", 2)
    oddboro = args.format == "oddboro"
    grant = AgentGrant(
        name=args.name,
        scopes=scopes,
        reach=reach,
        addons=addons,
        pinned_tools=args.pinned if oddboro else not args.fixed_tools_only,
        call_timeout_s=adapters.ODDBORO_CALL_TIMEOUT_S if oddboro else None,
    )
    problems: list[str] = []
    _check_agent(grant, problems)  # the manifest's own text, e.g. for the restricted scope
    if problems:
        return _fail("; ".join(problems), 2)
    problem = adapters.address_problem(args.url, args.format)
    if problem:
        return _fail(problem, 2)
    if args.key_file is not None:
        if os.path.lexists(args.key_file):
            return _fail("the key file already exists; nothing was changed", 2)
        if not args.key_file.parent.is_dir():
            return _fail("the key file folder does not exist; nothing was changed", 2)
    return grant, args.url


def _locked(args, body) -> int:
    """Run `body()` under the state lock: one lock for the whole read, change and write.

    A state folder or lock file that is refused gives one fixed line and the true key state.
    """
    from universal_connector import adapters
    from universal_connector.state import StateDirError

    with contextlib.ExitStack() as stack:
        try:
            stack.enter_context(adapters.state_lock(args.state))
        except Exception as err:  # noqa: BLE001 - fixed text only: an OSError's text holds a path
            reason = str(err) if isinstance(err, StateDirError) else "the state folder could not be opened"
            return _fail(f"{reason}; {_key_state_line(args.state, args.name)}", 1)
        return body()


def _connect(args) -> int:
    parsed = _parse_connect(args)
    if isinstance(parsed, int):
        return parsed
    grant, url = parsed
    return _locked(args, lambda: _connect_locked(args, grant, url))


def _key_state_line(state: Path, name: str) -> str:
    """A true sentence about the key state. It never holds a key."""
    from universal_connector import keys

    try:
        active = keys.has_active_key(state, name)
    except Exception:  # noqa: BLE001
        return f"the key state for {name} could not be read; run revoke"
    return f"a key is still active for {name}; run revoke" if active else f"no key is active for {name}"


def _connect_locked(args, grant, url: str) -> int:
    from universal_connector import adapters, keys
    from universal_connector.router import visible_names

    manifest = _load_or_report(args.manifest)
    if manifest is None:
        return 1
    if manifest.agent(args.name) is not None:
        return _fail("already connected; use rotate", 1)
    if args.format == "oddboro":  # before any change: Oddboro refuses a run with a longer name
        refusal, warning = adapters.oddboro_names_problem(url, visible_names(manifest, grant))
        if refusal is not None:
            return _fail(refusal, 2)
        if warning is not None:
            print(warning, file=sys.stderr)
    try:
        stale = keys.has_active_key(args.state, args.name)
    except Exception:  # noqa: BLE001
        return _fail("could not read the state folder", 1)
    if stale:
        return _fail("a key is still active for this name; run revoke first", 1)
    old = adapters.read_agents_bytes(args.manifest)
    kf = adapters.KeyFile(args.key_file) if args.key_file is not None else None
    key = ""
    try:
        if not _replace_agents(args.manifest, [*manifest.agents, grant]):
            line = _key_state_line(args.state, args.name)
            return _fail(f"the new agents file did not load; the old file was put back; {line}", 1)
        if kf is not None:
            kf.create()
        key = keys.mint(args.state, args.name)
        if kf is not None:
            kf.write(key)
    except Exception:  # noqa: BLE001 - no text is kept: it could hold the key or a path
        if key:
            with contextlib.suppress(Exception):
                keys.revoke(args.state, args.name)
        if kf is not None:
            kf.discard()  # only a file this run created
        try:
            adapters.write_agents_bytes(args.manifest, old)
            restored = "agents.yaml was put back"
        except OSError:
            restored = "agents.yaml could not be put back"
        return _fail(f"could not finish; {restored}; {_key_state_line(args.state, args.name)}", 1)
    shown = adapters.KEY_IN_FILE if kf is not None else key
    print(adapters.entry_for(args.format, url, shown))
    print(adapters.RELOAD_HINT)
    return 0


def _set_tools(args) -> int:
    return _locked(args, lambda: _set_tools_locked(args))


def _set_tools_locked(args) -> int:
    from universal_connector import adapters

    manifest = _load_or_report(args.manifest)
    if manifest is None:
        return 1
    if manifest.agent(args.name) is None:
        return _fail("unknown agent", 1)
    pinned = not args.fixed_only
    agents = [a.model_copy(update={"pinned_tools": pinned}) if a.name == args.name else a
              for a in manifest.agents]
    if not _replace_agents(args.manifest, agents):
        return _fail("the new agents file did not load; the old file was put back", 1)
    print(f"{args.name}: " + ("pinned tools on" if pinned else "fixed tools only"))
    print(adapters.RELOAD_HINT)
    return 0


def _revoke_agent(args) -> int:
    return _locked(args, lambda: _revoke_locked(args))


def _revoke_locked(args) -> int:
    from universal_connector import adapters, keys

    try:  # first, and whether or not the agent is listed or enabled: the key matters most
        had = keys.revoke(args.state, args.name)
    except Exception:  # noqa: BLE001
        return _fail(f"could not revoke the key; {_key_state_line(args.state, args.name)}", 1)
    manifest = _load_or_report(args.manifest)
    if manifest is None:
        return _fail(f"the key for {args.name} is revoked, but the manifest did not load", 1)
    agent = manifest.agent(args.name)
    if agent is None:
        case = "its active key is revoked" if had else "no key was active"
        print(f"{args.name} is not in agents.yaml; {case}")
        print(adapters.RELOAD_HINT)
        return 0
    if agent.enabled:
        agents = [a.model_copy(update={"enabled": False}) if a.name == args.name else a
                  for a in manifest.agents]
        if not _replace_agents(args.manifest, agents):
            return _fail("the key is revoked, but agents.yaml could not be updated; run revoke again", 1)
    print(f"revoked {args.name}" + ("" if had else " (no key was active)"))
    print(adapters.RELOAD_HINT)
    return 0


def _rotate_agent(args) -> int:
    if args.key_file is not None:
        if os.path.lexists(args.key_file):
            return _fail("the key file already exists; nothing was changed", 2)
        if not args.key_file.parent.is_dir():
            return _fail("the key file folder does not exist; nothing was changed", 2)
    return _locked(args, lambda: _rotate_locked(args))


def _rotate_locked(args) -> int:
    from universal_connector import adapters, keys

    manifest = _load_or_report(args.manifest)
    if manifest is None:
        return 1
    agent = manifest.agent(args.name)
    if agent is None:
        return _fail("unknown agent", 1)
    if not agent.enabled:
        return _fail("agent is revoked; connect under a new name", 1)
    kf = adapters.KeyFile(args.key_file) if args.key_file is not None else None
    try:
        if kf is not None:
            kf.create()
        key = keys.rotate(args.state, args.name)
    except keys.NoActiveKey:
        if kf is not None:
            kf.discard()
        return _fail("agent has no active key; connect under a new name", 1)
    except Exception:  # noqa: BLE001 - no text is kept
        if kf is not None:
            kf.discard()
        return _fail(f"could not rotate the key; {_key_state_line(args.state, args.name)}", 1)
    if kf is not None:
        try:
            kf.write(key)
        except Exception:  # noqa: BLE001 - fail closed: the new key dies with the file
            with contextlib.suppress(Exception):
                keys.revoke(args.state, args.name)
            kf.discard()
            line = _key_state_line(args.state, args.name)
            if line.startswith("no key is active"):
                line = f"no key is active for {args.name}; connect again under a new name"
            return _fail(f"rotate failed; {line}", 1)
        print(f"{args.name}: new key written to {args.key_file}")
    else:
        print(f"{args.name}: new key")
        print(key)
    print(adapters.RELOAD_HINT)
    return 0


def _list_agents(args) -> int:
    from universal_connector import keys

    manifest = _load_or_report(args.manifest)
    if manifest is None:
        return 1
    if not manifest.agents:
        print("no agents")
        return 0
    print("name scopes reach addons enabled key")
    for a in manifest.agents:
        try:  # a missing state folder means no key is active; `list` never creates one
            active = (args.state / "state.db").is_file() and keys.has_active_key(args.state, a.name)
        except Exception:  # noqa: BLE001
            return _fail("could not read the state folder", 1)
        print(
            " ".join(
                [
                    a.name,
                    ",".join(sorted(s.value for s in a.scopes)),
                    a.reach.value,
                    ",".join(sorted(x.value for x in a.addons)) or "-",
                    "yes" if a.enabled else "no",
                    "active" if active else "none",
                ]
            )
        )
    return 0


def _doctor(manifest_dir: Path, machine_file: Path | None = None) -> int:
    import asyncio

    from universal_connector import doctor
    from universal_connector.upstreams.factory import build_upstreams

    machine = _machine_or_none(machine_file)
    if machine is None:
        return 2
    try:
        manifest = load_manifest(manifest_dir)
    except ManifestError as err:
        for problem in err.problems:
            print(f"manifest: {problem}", file=sys.stderr)
        return 1
    try:
        store = store_for(machine)
    except ValueError as err:  # fixed text
        return _fail(str(err), 2)
    rows = asyncio.run(doctor.run_doctor(manifest, build_upstreams(manifest, store, machine), store))
    print(doctor.render_rows(rows), end="")
    return doctor.exit_code(rows)


def _login(args) -> int:
    from universal_connector import login

    machine = _machine_or_none(args.machine_file)
    if machine is None:
        return 2

    def announce(url: str) -> None:
        print("Open this address in a browser on this machine. Waiting up to 5 minutes.")
        print(url)

    try:
        deps = login.default_deps(machine)
    except ValueError as err:  # fixed text: a bad vault setting, or the memory vault
        return _fail(str(err), 2)
    failed = False
    try:
        login.run_login(args.account, args.manifest, machine, announce=announce, **deps)
    except login.LoginError as err:  # fixed text, never a value
        return _fail(str(err), 1)
    except Exception:  # noqa: BLE001 - no text is kept: it could quote a request
        failed = True
    if failed:
        return _fail("the sign-in failed; nothing was saved", 1)
    print(f"saved the sign-in for {args.account}")
    return 0


def _reload(args) -> int:
    """Ask the running door to reload its manifest, through the state folder. Every system.

    Exit 0: reloaded. 1: the new manifest did not load, so the last good one keeps serving.
    2: no state folder. 3: no door answered in time.
    """
    from universal_connector import audit

    if not 0 <= args.wait <= RELOAD_WAIT_MAX_S:
        return _fail(f"--wait must be between 0 and {int(RELOAD_WAIT_MAX_S)} seconds", 2)
    if not (args.state / "state.db").is_file():  # never create a state folder here
        return _fail(NO_STATE_HERE, 2)
    try:
        number = audit.request_reload(args.state)
    except Exception:  # noqa: BLE001 - fixed text only
        return _fail("the state folder could not be opened; nothing was asked", 1)
    deadline = time.monotonic() + args.wait
    while True:
        try:
            done, outcome = audit.reload_answer(args.state)
        except Exception:  # noqa: BLE001 - fixed text only
            done, outcome = 0, ""
        if done >= number:
            if outcome == "ok":
                print("reloaded")
                return 0
            return _fail("the new manifest did not load; the door keeps the last good one", 1)
        if time.monotonic() >= deadline:
            return _fail(NO_DOOR_ANSWERED, 3)
        time.sleep(0.25)


def _install_service(args) -> int:
    """Print the service template for this system, filled in. Installs nothing."""
    from universal_connector import service

    if not args.print:
        return _fail("install-service only prints a template; add --print. It installs nothing.", 2)
    kind = service.kind_for_platform()
    install_dir = args.install_dir
    if install_dir is None:
        found = shutil.which("uconnector")
        if found is None:
            return _fail("uconnector is not on PATH; pass --install-dir", 2)
        install_dir = Path(found).parent  # the PATH folder, which survives a tool upgrade
    try:
        text = service.render(
            kind,
            install_dir=str(install_dir),
            machine_file=str(args.machine_file),
            manifest_dir=str(args.manifest),
            state_dir=str(args.state),
        )
    except ValueError as err:  # fixed text
        return _fail(str(err), 2)
    if not _machine_file_exists(args.machine_file):  # a service must never start on defaults
        from universal_connector.machine import MISSING_MACHINE_FILE

        return _fail(MISSING_MACHINE_FILE, 2)
    sys.stdout.write(text)
    print(service.INSTALL_STEPS[kind], file=sys.stderr)
    return 0


def _machine_file_exists(path: Path) -> bool:
    return Path(path).is_file()


def _smoke(args) -> int:
    """Check a running door the way Oddboro's client talks to it. Never prints the key."""
    import asyncio

    from universal_connector import smoke

    problem = smoke.address_problem(args.url)
    if problem:
        return _fail(problem, 2)
    try:
        key = smoke.read_key_file(args.key_file)
    except ValueError as err:  # fixed text
        return _fail(str(err), 2)
    checks = asyncio.run(smoke.run_smoke(args.url, key))
    print(smoke.render(checks), end="")
    return smoke.exit_code(checks)


def _resolve_state(args) -> int | None:
    """Fill in the per-user state folder when `--state` was not given. An exit code on failure."""
    if not hasattr(args, "state") or args.state is not None:
        return None
    try:
        args.state = portable.default_state_dir()
    except ValueError as err:  # fixed text
        return _fail(str(err), 2)
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="uconnector")
    sub = parser.add_subparsers(dest="command", required=True)
    state_help = "the state folder; default: the per-user app-data folder"
    machine_help = "the machine file; default: $UCONNECTOR_MACHINE_FILE, else ./machine.yaml"
    chk = sub.add_parser("check", help="validate the manifest and scan the repo for secrets")
    chk.add_argument("--manifest", type=Path, default=None)
    srv = sub.add_parser("serve", help="run the door on loopback, in the foreground")
    srv.add_argument("--manifest", required=True, type=Path)
    srv.add_argument("--state", type=Path, default=None, help=state_help)
    srv.add_argument("--machine-file", type=Path, default=None, help=machine_help)
    srv.add_argument("--host", default="127.0.0.1")
    srv.add_argument("--port", type=int, default=8765)
    pause = sub.add_parser("pause", help="stop every call until resume")
    pause.add_argument("--state", type=Path, default=None, help=state_help)
    resume = sub.add_parser("resume", help="allow calls again")
    resume.add_argument("--state", type=Path, default=None, help=state_help)
    rel = sub.add_parser("reload", help="ask the running door to reload its manifest")
    rel.add_argument("--state", type=Path, default=None, help=state_help)
    rel.add_argument("--wait", type=float, default=RELOAD_WAIT_S, help="seconds to wait for it")
    doc = sub.add_parser("doctor", help="one read-only health row per connection")
    doc.add_argument("--manifest", required=True, type=Path)
    doc.add_argument("--machine-file", type=Path, default=None, help=machine_help)
    paths = argparse.ArgumentParser(add_help=False)
    paths.add_argument("--manifest", required=True, type=Path)
    paths.add_argument("--state", type=Path, default=None, help=state_help)
    con = sub.add_parser("connect", parents=[paths], help="add an agent and mint its key")
    con.add_argument("name")
    con.add_argument("--reach", default=None)
    con.add_argument("--scopes", default=None)
    con.add_argument("--addons", default="")
    con.add_argument("--format", default="generic", choices=["generic", "oddboro"])
    con.add_argument("--url", default=DEFAULT_URL)
    con.add_argument("--key-file", type=Path, default=None)
    tools = con.add_mutually_exclusive_group()
    tools.add_argument("--fixed-tools-only", action="store_true", help="show only the 5 fixed tools")
    tools.add_argument(
        "--pinned", action="store_true", help="with --format oddboro: show pinned tools too"
    )
    rev = sub.add_parser("revoke", parents=[paths], help="disable an agent and revoke its key")
    rev.add_argument("name")
    rot = sub.add_parser("rotate", parents=[paths], help="replace the key of an enabled agent")
    rot.add_argument("name")
    rot.add_argument("--key-file", type=Path, default=None)
    sett = sub.add_parser("set-tools", parents=[paths], help="show an agent fixed tools only, or pinned too")
    sett.add_argument("name")
    mode = sett.add_mutually_exclusive_group(required=True)
    mode.add_argument("--fixed-only", action="store_true")
    mode.add_argument("--pinned", action="store_true")
    sub.add_parser("list", parents=[paths], help="list agents; never a key or a hash")
    log = sub.add_parser("login", help="one sign-in, saved to the vault by the door")
    log.add_argument("provider", choices=["google"])
    log.add_argument("--account", required=True, help="a label such as work, never an address")
    log.add_argument("--manifest", required=True, type=Path)
    log.add_argument("--machine-file", type=Path, default=None, help=machine_help)
    ins = sub.add_parser("install-service", help="print the service file for this system")
    ins.add_argument("--print", action="store_true", help="print it; nothing is installed")
    ins.add_argument("--machine-file", required=True, type=Path, help="absolute path")
    ins.add_argument("--manifest", required=True, type=Path, help="absolute path")
    ins.add_argument("--state", type=Path, default=None, help=state_help)
    ins.add_argument("--install-dir", type=Path, default=None, help="the folder with uconnector")
    smk = sub.add_parser("smoke", help="check a running door the way an agent system talks to it")
    smk.add_argument("target", choices=["oddboro"])
    smk.add_argument("--url", required=True, help="the https address Oddboro uses")
    smk.add_argument("--key-file", required=True, type=Path, help="a file with the agent's key")
    args = parser.parse_args(argv)
    failed = _resolve_state(args)
    if failed is not None:
        return failed
    handlers = {
        "login": _login, "reload": _reload, "install-service": _install_service, "smoke": _smoke,
        "connect": _connect, "revoke": _revoke_agent, "rotate": _rotate_agent,
        "set-tools": _set_tools, "list": _list_agents,
    }  # fmt: skip
    if args.command in handlers:
        return handlers[args.command](args)
    if args.command == "doctor":
        return _doctor(args.manifest, args.machine_file)
    if args.command == "serve":
        return _serve(args.manifest, args.state, args.host, args.port, args.machine_file)
    if args.command in ("pause", "resume"):
        return _set_paused(args.state, args.command == "pause")
    return _check(args.manifest)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
