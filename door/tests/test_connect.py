from __future__ import annotations

import hashlib
import io
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
import yaml

from universal_connector import adapters, frontdoor, keys
from universal_connector.cli import main
from universal_connector.manifest import load_manifest
from universal_connector.state import LOCK_REFUSED
from universal_connector.upstreams.base import ToolInfo
from universal_connector.vault import MemorySecretStore

KEY_RE = re.compile(r"pc_[A-Za-z0-9_-]{43}")

CONNECTOR_YAML = """\
version: 1
connections:
  - name: mail
    kind: mcp-remote
    upstream: https://up.example.invalid/mcp
    auth: {type: none}
    scopes: [work]
    reach: starter
    tools:
      - {name: search, tier: green, pinned: true}
"""
AGENTS_YAML = """\
# a comment that the rewrite drops
version: 1
agents:
  - {name: alpha, scopes: [work], reach: starter}
"""


@pytest.fixture
def env(tmp_path):
    manifest = tmp_path / "manifest"
    manifest.mkdir()
    (manifest / "connector.yaml").write_text(CONNECTOR_YAML)
    (manifest / "agents.yaml").write_text(AGENTS_YAML)
    state = tmp_path / "state"
    keys.mint(state, "alpha")
    return SimpleNamespace(manifest=manifest, state=state, tmp=tmp_path)


def run(env, *words: str) -> int:
    return main([*words, "--manifest", str(env.manifest), "--state", str(env.state)])


def connect(env, name="bravo", *extra: str) -> int:
    return run(env, "connect", name, "--reach", "starter", "--scopes", "work", *extra)


def agents_bytes(env) -> bytes:
    return (env.manifest / "agents.yaml").read_bytes()


def keys_in(text: str) -> list[str]:
    return KEY_RE.findall(text)


def test_connect_writes_agent_and_mints(env, capsys):
    assert connect(env, "bravo", "--addons", "drafts") == 0
    out = capsys.readouterr().out
    agent = load_manifest(env.manifest).agent("bravo")
    assert agent is not None and agent.enabled is True
    assert [a.value for a in agent.addons] == ["drafts"]
    assert keys.has_active_key(env.state, "bravo")
    (key,) = keys_in(out)
    assert keys.verify(env.state, key) == "bravo"


def test_connect_refuses_restricted(env, capsys):
    before = agents_bytes(env)
    code = run(env, "connect", "bravo", "--reach", "starter", "--scopes", "work,restricted")
    assert code == 2
    assert "restricted cannot be granted in this version" in capsys.readouterr().err
    assert agents_bytes(env) == before
    assert not keys.has_active_key(env.state, "bravo")


def test_connect_refuses_duplicate(env, capsys):
    before = agents_bytes(env)
    assert connect(env, "alpha") == 1
    assert "already connected; use rotate" in capsys.readouterr().err
    assert agents_bytes(env) == before


def test_unknown_scope_exits_2(env, capsys):
    before = agents_bytes(env)
    assert run(env, "connect", "bravo", "--reach", "starter", "--scopes", "work,nope") == 2
    assert agents_bytes(env) == before
    assert not keys.has_active_key(env.state, "bravo")
    assert KEY_RE.search(capsys.readouterr().err) is None


def test_key_printed_exactly_once(env, capsys):
    assert connect(env) == 0
    captured = capsys.readouterr()
    (key,) = keys_in(captured.out)
    assert captured.out.count(key) == 1
    assert key not in captured.err


def test_key_file_mode_and_output(env, capsys):
    path = env.tmp / "agent.key"
    assert connect(env, "bravo", "--key-file", str(path)) == 0
    captured = capsys.readouterr()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    key = path.read_text().strip()
    assert KEY_RE.fullmatch(key)
    assert key not in captured.out and key not in captured.err
    assert "<key in file>" in captured.out
    assert keys.verify(env.state, key) == "bravo"


def test_key_file_refuses_existing_path(env, capsys):
    before = agents_bytes(env)
    existing = env.tmp / "taken.key"
    existing.write_text("keep")
    assert connect(env, "bravo", "--key-file", str(existing)) == 2
    assert existing.read_text() == "keep"
    link = env.tmp / "link.key"
    link.symlink_to(env.tmp / "nowhere")  # a dangling link is an existing path too
    assert connect(env, "bravo", "--key-file", str(link)) == 2
    assert agents_bytes(env) == before
    assert not keys.has_active_key(env.state, "bravo")
    assert not (env.tmp / "nowhere").exists()
    capsys.readouterr()


def test_create_key_file_never_follows_a_link(tmp_path):
    (tmp_path / "t").write_text("x")
    (tmp_path / "l").symlink_to(tmp_path / "t")
    with pytest.raises(OSError):
        adapters.create_key_file(tmp_path / "l")
    assert (tmp_path / "t").read_text() == "x"


def test_no_terminal_without_flags_exits_2(env, monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    before = agents_bytes(env)
    assert run(env, "connect", "bravo") == 2
    assert run(env, "connect", "bravo", "--reach", "starter") == 2
    assert agents_bytes(env) == before
    capsys.readouterr()


def test_terminal_prompts_for_missing_flags(env, monkeypatch, capsys):
    class Tty(io.StringIO):
        def isatty(self) -> bool:
            return True

    answers = iter(["full-read", "work,personal"])
    monkeypatch.setattr("sys.stdin", Tty(""))
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    assert run(env, "connect", "bravo") == 0
    agent = load_manifest(env.manifest).agent("bravo")
    assert agent is not None and agent.reach.value == "full-read"
    assert sorted(s.value for s in agent.scopes) == ["personal", "work"]
    capsys.readouterr()


def test_revoke_disables_and_is_repeatable(env, capsys):
    assert run(env, "revoke", "alpha") == 0
    agent = load_manifest(env.manifest).agent("alpha")
    assert agent is not None and agent.enabled is False
    assert not keys.has_active_key(env.state, "alpha")
    first = agents_bytes(env)
    assert run(env, "revoke", "alpha") == 0
    assert agents_bytes(env) == first
    assert run(env, "revoke", "ghost") == 0  # nothing to do is not a fault
    assert "ghost is not in agents.yaml; no key was active" in capsys.readouterr().out


def test_rotate_changes_key(env, capsys):
    assert connect(env) == 0
    (old,) = keys_in(capsys.readouterr().out)
    assert run(env, "rotate", "bravo") == 0
    out = capsys.readouterr().out
    (new,) = keys_in(out)
    assert new != old
    assert out.count(new) == 1
    assert keys.verify(env.state, new) == "bravo"
    assert keys.verify(env.state, old) is None


def test_rotate_key_file(env, capsys):
    path = env.tmp / "rot.key"
    assert run(env, "rotate", "alpha", "--key-file", str(path)) == 0
    out = capsys.readouterr().out
    key = path.read_text().strip()
    assert key not in out and stat.S_IMODE(path.stat().st_mode) == 0o600
    assert keys.verify(env.state, key) == "alpha"


def test_rotate_refuses_revoked_agent(env, capsys):
    assert run(env, "revoke", "alpha") == 0
    capsys.readouterr()
    assert run(env, "rotate", "alpha") == 1
    assert "connect under a new name" in capsys.readouterr().err
    assert not keys.has_active_key(env.state, "alpha")
    assert load_manifest(env.manifest).agent("alpha").enabled is False


def test_rotate_refuses_unknown_agent(env, capsys):
    assert run(env, "rotate", "ghost") == 1
    assert "unknown agent" in capsys.readouterr().err
    assert not keys.has_active_key(env.state, "ghost")


def test_rotate_refuses_enabled_agent_without_key(env, capsys):
    keys.revoke(env.state, "alpha")  # enabled in the file, no active key
    path = env.tmp / "unused.key"
    assert run(env, "rotate", "alpha", "--key-file", str(path)) == 1
    assert not path.exists()  # the file made for the new key is taken away again
    assert not keys.has_active_key(env.state, "alpha")
    capsys.readouterr()


def test_list_has_no_key_or_hash(env, capsys):
    assert connect(env) == 0
    (key,) = keys_in(capsys.readouterr().out)
    digest = hashlib.sha256(key.encode()).hexdigest()
    assert run(env, "list") == 0
    out = capsys.readouterr().out
    assert key not in out and digest not in out and not KEY_RE.search(out)
    assert "alpha work starter - yes active" in out
    assert run(env, "revoke", "alpha") == 0
    capsys.readouterr()
    run(env, "list")
    assert "alpha work starter - no none" in capsys.readouterr().out


def test_generic_entry_is_valid_json():
    data = json.loads(adapters.entry_for("generic", "http://127.0.0.1:8765/mcp", "K"))
    assert data == {
        "mcpServers": {
            "connector": {
                "type": "http",
                "url": "http://127.0.0.1:8765/mcp",
                "headers": {"Authorization": "Bearer K"},
            }
        }
    }


def test_unknown_format_is_refused_with_the_known_list():
    with pytest.raises(ValueError, match="^unknown format; use one of generic, oddboro$"):
        adapters.entry_for("other", "https://x.example/mcp", "K")


def test_oddboro_entry_has_three_lines():
    lines = adapters.entry_for("oddboro", "https://x.example/mcp", "K").splitlines()
    assert lines == [
        "Address: https://x.example/mcp",
        "Header name: Authorization",
        "Header value: Bearer K",
    ]


def test_unknown_format_is_refused():
    with pytest.raises(ValueError):
        adapters.entry_for("nope", "https://x.example", "K")


def test_oddboro_format_needs_https(env, capsys):
    before = agents_bytes(env)
    assert connect(env, "bravo", "--format", "oddboro") == 2  # the default address is http
    assert "Oddboro needs an https address." in capsys.readouterr().err
    assert agents_bytes(env) == before
    assert not keys.has_active_key(env.state, "bravo")
    assert connect(env, "bravo", "--format", "oddboro", "--url", "https://door.example/mcp") == 0
    out = capsys.readouterr().out
    assert out.startswith("Address: https://door.example/mcp\n")


@pytest.mark.parametrize(
    "url", ["", "ftp://x.example/mcp", "http://", "http://u:p@x.example/mcp", "http://x example/mcp"]
)
def test_bad_address_exits_2(env, capsys, url):
    before = agents_bytes(env)
    assert connect(env, "bravo", "--url", url) == 2
    assert agents_bytes(env) == before
    capsys.readouterr()


def test_failed_mint_restores_agents_file(env, monkeypatch, capsys):
    before = agents_bytes(env)

    def boom(directory, agent):
        raise RuntimeError("MRK-mint-text")

    monkeypatch.setattr(keys, "mint", boom)
    path = env.tmp / "k.key"
    assert connect(env, "bravo", "--key-file", str(path)) == 1
    captured = capsys.readouterr()
    assert agents_bytes(env) == before
    assert not path.exists()
    assert "MRK" not in captured.out + captured.err
    assert load_manifest(env.manifest).agent("bravo") is None


def test_agents_file_that_does_not_load_is_put_back(env, monkeypatch, capsys):
    before = agents_bytes(env)
    monkeypatch.setattr(adapters, "render_agents", lambda agents: b"version: 1\nagents: nope\n")
    assert connect(env) == 1
    assert agents_bytes(env) == before
    assert not keys.has_active_key(env.state, "bravo")
    capsys.readouterr()


def test_manifest_still_loads_after_connect(env, capsys):
    assert connect(env, "bravo", "--addons", "drafts,browser") == 0
    assert connect(env, "charlie") == 0
    manifest = load_manifest(env.manifest)
    assert [a.name for a in manifest.agents] == ["alpha", "bravo", "charlie"]
    data = yaml.safe_load(agents_bytes(env))
    assert data["version"] == 1
    assert not list(env.manifest.glob(".agents-*"))  # no temporary file is left
    capsys.readouterr()


def test_reload_hint_printed(env, capsys):
    assert connect(env) == 0
    assert capsys.readouterr().out.splitlines()[-1] == adapters.RELOAD_HINT
    assert run(env, "rotate", "bravo") == 0
    assert capsys.readouterr().out.splitlines()[-1] == adapters.RELOAD_HINT
    assert run(env, "revoke", "bravo") == 0
    assert capsys.readouterr().out.splitlines()[-1] == adapters.RELOAD_HINT


def test_bad_name_exits_2(env, capsys):
    assert connect(env, "Bad_Name") == 2
    capsys.readouterr()


def test_both_paths_are_required(env):
    with pytest.raises(SystemExit) as stopped:
        main(["list"])
    assert stopped.value.code == 2


def test_stat_of_agents_file_mode_kept(env, capsys):
    (env.manifest / "agents.yaml").chmod(0o640)
    assert connect(env) == 0
    assert stat.S_IMODE((env.manifest / "agents.yaml").stat().st_mode) == 0o640
    capsys.readouterr()


# -- QA round 1: the lock, true failure text, files this run did not create ---------------------

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
# Each child widens two windows, then waits at a shared gate, so an unlocked run always interleaves.
CHILD = """
import os, sys, time
from pathlib import Path
from universal_connector import adapters, keys
WIDEN = 0.05
real_read, real_rotate = adapters.read_agents_bytes, keys.rotate
def slow_read(directory):
    data = real_read(directory)
    time.sleep(WIDEN)  # between reading agents.yaml and writing it
    return data
def slow_rotate(directory, agent):
    time.sleep(WIDEN)  # between rotate's manifest check and its key change
    return real_rotate(directory, agent)
adapters.read_agents_bytes, keys.rotate = slow_read, slow_rotate
from universal_connector.cli import main
gate, count = Path(sys.argv[1]), int(sys.argv[2])
(gate / str(os.getpid())).touch()
deadline = time.monotonic() + 30
while len(os.listdir(gate)) < count:  # every child is imported; all start together
    if time.monotonic() > deadline:
        raise SystemExit(9)
    time.sleep(0.002)
raise SystemExit(main(sys.argv[3:]))
"""


def run_children(env, commands: list[list[str]]) -> list[tuple[str, str, int]]:
    """Run each command in its own process, all released at once. Returns (out, err, code)."""
    gate = tempfile.mkdtemp(prefix="gate-", dir=env.tmp)
    child_env = {**os.environ, "PYTHONPATH": str(SRC_DIR)}
    paths = ["--manifest", str(env.manifest), "--state", str(env.state)]
    procs = [
        subprocess.Popen(
            [sys.executable, "-c", CHILD, gate, str(len(commands)), *words, *paths],
            env=child_env, cwd=env.tmp, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        for words in commands
    ]
    results = []
    for proc in procs:
        out, err = proc.communicate(timeout=60)
        results.append((out, err, proc.returncode))
    return results


def test_concurrent_connects_leave_no_orphan(env):
    names = ["bravo", "charlie", "delta"]
    results = run_children(env, [["connect", n, "--reach", "starter", "--scopes", "work"] for n in names])
    assert [code for _, _, code in results] == [0, 0, 0]
    listed = {a.name for a in load_manifest(env.manifest).agents}
    assert listed == {"alpha", *names}
    for name, (out, err, _) in zip(names, results, strict=True):
        (key,) = keys_in(out)
        assert key not in err
        assert keys.verify(env.state, key) == name  # every printed key belongs to a listed agent
    assert stat.S_IMODE((env.state / "connector.lock").stat().st_mode) == 0o600


def test_concurrent_revokes_and_rotates_are_serialized(env):
    """A rotate and a revoke of one agent at once may only end as some order of the two would.

    Rotate first: it prints a new key, then revoke kills it. Revoke first: rotate sees a revoked
    agent. Without the lock in either command, rotate sees the agent enabled, then finds the key
    gone: `agent has no active key`, an outcome no order of the two can give.
    """
    rot, rev = run_children(env, [["rotate", "alpha"], ["revoke", "alpha"]])
    assert rev[2] == 0
    assert not keys.has_active_key(env.state, "alpha")
    assert load_manifest(env.manifest).agent("alpha").enabled is False
    if rot[2] == 0:
        (key,) = keys_in(rot[0])
        assert keys.verify(env.state, key) is None
    else:
        assert rot[1] == "agent is revoked; connect under a new name\n"


def test_revoke_unknown_agent_kills_active_key(env, capsys):
    key = keys.mint(env.state, "ghost")
    assert run(env, "revoke", "ghost") == 0
    assert "ghost is not in agents.yaml; its active key is revoked" in capsys.readouterr().out
    assert keys.verify(env.state, key) is None
    assert not keys.has_active_key(env.state, "ghost")


def test_revoke_disabled_agent_still_revokes_key(env, capsys):
    (env.manifest / "agents.yaml").write_text(
        "version: 1\nagents:\n  - {name: alpha, scopes: [work], reach: starter, enabled: false}\n"
    )
    assert keys.has_active_key(env.state, "alpha")  # disabled in the file, key still live
    assert run(env, "revoke", "alpha") == 0
    assert not keys.has_active_key(env.state, "alpha")
    capsys.readouterr()


def test_connect_refuses_free_name_with_stale_key(env, capsys):
    keys.mint(env.state, "bravo")
    before = agents_bytes(env)
    assert connect(env, "bravo") == 1
    assert "a key is still active for this name; run revoke first" in capsys.readouterr().err
    assert agents_bytes(env) == before


def _partial_write(self, key: str) -> None:
    os.write(self._fd, key[:20].encode())  # 20 characters reach the file, then the write fails
    self.close()
    raise OSError("MRK-disk-full")


def test_failure_text_matches_key_state(env, monkeypatch, capsys):
    def boom(directory, agent):
        raise RuntimeError("MRK")

    with monkeypatch.context() as m:
        m.setattr(keys, "mint", boom)
        assert connect(env, "bravo") == 1
    assert "no key is active for bravo" in capsys.readouterr().err
    # the write fails and the revoke fails too: the key is still live, and the text says so
    real_revoke = keys.revoke

    def no_revoke(directory, agent):
        raise RuntimeError("MRK")

    with monkeypatch.context() as m:
        m.setattr(adapters.KeyFile, "write", _partial_write)
        m.setattr(keys, "revoke", no_revoke)
        assert connect(env, "bravo", "--key-file", str(env.tmp / "k1.key")) == 1
    assert "a key is still active for bravo; run revoke" in capsys.readouterr().err
    assert real_revoke(env.state, "bravo") is True


def test_failure_text_has_no_key(env, monkeypatch, capsys):
    monkeypatch.setattr(adapters.KeyFile, "write", _partial_write)
    assert connect(env, "bravo", "--key-file", str(env.tmp / "k.key")) == 1
    captured = capsys.readouterr()
    assert not KEY_RE.search(captured.out + captured.err)
    assert "MRK" not in captured.out + captured.err


def test_partial_connect_revokes_key(env, monkeypatch, capsys):
    before = agents_bytes(env)
    monkeypatch.setattr(adapters.KeyFile, "write", _partial_write)
    path = env.tmp / "k.key"
    assert connect(env, "bravo", "--key-file", str(path)) == 1
    assert not keys.has_active_key(env.state, "bravo")
    assert agents_bytes(env) == before
    assert not path.exists()  # no partial key stays in a file
    assert "no key is active for bravo" in capsys.readouterr().err


def test_failed_run_never_deletes_foreign_file(env, monkeypatch, capsys):
    foreign = env.tmp / "foreign.key"
    foreign.write_text("someone else's file")
    before = agents_bytes(env)
    # the path "appears" after the pre-check: the exclusive open must refuse it
    monkeypatch.setattr("universal_connector.cli.os.path.lexists", lambda p: False)
    assert connect(env, "bravo", "--key-file", str(foreign)) == 1
    assert foreign.read_text() == "someone else's file"
    assert agents_bytes(env) == before
    assert not keys.has_active_key(env.state, "bravo")
    assert run(env, "rotate", "alpha", "--key-file", str(foreign)) == 1
    assert foreign.read_text() == "someone else's file"
    assert keys.has_active_key(env.state, "alpha")
    capsys.readouterr()


def test_key_file_open_is_exclusive(env, monkeypatch, capsys):
    taken = env.tmp / "late.key"
    taken.write_text("late arrival")
    monkeypatch.setattr("universal_connector.cli.os.path.lexists", lambda p: False)
    assert connect(env, "bravo", "--key-file", str(taken)) == 1
    assert taken.read_text() == "late arrival"  # not truncated, not overwritten
    capsys.readouterr()


def test_rotate_key_file_failure_fails_closed(env, monkeypatch, capsys):
    path = env.tmp / "rot.key"
    monkeypatch.setattr(adapters.KeyFile, "write", _partial_write)
    assert run(env, "rotate", "alpha", "--key-file", str(path)) == 1
    err = capsys.readouterr().err
    assert "rotate failed; no key is active for alpha; connect again under a new name" in err
    assert not keys.has_active_key(env.state, "alpha")
    assert not path.exists()
    assert not KEY_RE.search(err)


def test_list_creates_nothing(env, capsys):
    fresh = env.tmp / "never-made"
    assert main(["list", "--manifest", str(env.manifest), "--state", str(fresh)]) == 0
    assert not fresh.exists()
    assert "alpha work starter - yes none" in capsys.readouterr().out


def test_no_command_writes_key_to_stderr(env, monkeypatch, capsys):
    outputs: list[str] = []
    assert connect(env) == 0
    outputs.append(capsys.readouterr().err)
    assert run(env, "rotate", "bravo") == 0
    outputs.append(capsys.readouterr().err)
    assert run(env, "list") == 0
    outputs.append(capsys.readouterr().err)
    assert run(env, "revoke", "bravo") == 0
    outputs.append(capsys.readouterr().err)
    monkeypatch.setattr(adapters.KeyFile, "write", _partial_write)
    assert connect(env, "charlie", "--key-file", str(env.tmp / "c.key")) == 1
    assert run(env, "rotate", "alpha", "--key-file", str(env.tmp / "a.key")) == 1
    outputs.append(capsys.readouterr().err)
    assert not any(KEY_RE.search(text) for text in outputs)


def test_agents_file_write_is_atomic(env, monkeypatch, capsys):
    before = agents_bytes(env)

    def crash(src, dst):
        raise OSError("crash before the replace")

    monkeypatch.setattr(os, "replace", crash)
    with pytest.raises(OSError):
        adapters.write_agents_bytes(env.manifest, b"version: 1\nagents: []\n")
    assert agents_bytes(env) == before  # the old file is whole
    assert not list(env.manifest.glob(".agents-*"))  # and no temporary file is left
    assert connect(env) == 1  # the same crash inside a command
    assert agents_bytes(env) == before
    assert not keys.has_active_key(env.state, "bravo")
    capsys.readouterr()


def test_default_url_is_loopback(env, capsys):
    assert adapters.DEFAULT_URL == "http://127.0.0.1:8765/mcp"
    assert connect(env) == 0
    assert "http://127.0.0.1:8765/mcp" in capsys.readouterr().out


# -- QA round 2: the first command on a fresh machine, and the lock file -------------------------

INIT_BODY = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "t", "version": "0"},
    },
}
MCP_HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
DOOR_PORT = 47321  # a Host header value only: nothing binds a socket
WRITERS = [["connect", "bravo", "--reach", "starter", "--scopes", "work"], ["revoke", "alpha"],
           ["rotate", "alpha"]]


class _NoNetUpstream:
    async def list_tools(self) -> list[ToolInfo]:
        return [ToolInfo("search", "fake search", {"type": "object"})]

    async def call_tool(self, name: str, arguments: dict) -> str:  # pragma: no cover - not used
        return "ran"

    async def probe(self):  # pragma: no cover - not used
        raise NotImplementedError

    def secret_values(self) -> list[str]:
        return []

    def purge(self) -> int:
        return 0


async def door_statuses(env, *presented: str) -> list[int]:
    """The front door's own key check: the real app, its startup and its gate, in process."""
    holder = frontdoor.Holder(
        env.manifest, env.state, MemorySecretStore({}), lambda m, s, x: {"mail": _NoNetUpstream()}
    )
    app = frontdoor.build_app(holder, env.state)
    app.state.set_port(DOOR_PORT)
    statuses = []
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        base = f"http://127.0.0.1:{DOOR_PORT}"
        async with httpx.AsyncClient(transport=transport, base_url=base) as http:
            for key in presented:
                headers = {**MCP_HEADERS, "Authorization": f"Bearer {key}"}
                statuses.append((await http.post("/mcp", json=INIT_BODY, headers=headers)).status_code)
    return statuses


@pytest.fixture
def fresh(tmp_path, monkeypatch):
    """A manifest with agent alpha, and a state folder that does not exist. Nothing is minted."""
    (tmp_path / "empty-machine.yaml").write_text("")  # an explicit machine file must exist
    monkeypatch.setenv("UCONNECTOR_MACHINE_FILE", str(tmp_path / "empty-machine.yaml"))
    manifest = tmp_path / "manifest"
    manifest.mkdir()
    (manifest / "connector.yaml").write_text(CONNECTOR_YAML)
    (manifest / "agents.yaml").write_text(AGENTS_YAML)
    return SimpleNamespace(manifest=manifest, state=tmp_path / "new" / "state", tmp=tmp_path)


async def _next_connect_is_served(env, capsys) -> None:
    """A connect works, and the front door accepts its key and nothing else."""
    assert connect(env, "bravo") == 0
    captured = capsys.readouterr()
    (key,) = keys_in(captured.out)
    assert captured.err == ""
    assert sorted(p.name for p in env.state.iterdir()) == [adapters.LOCK_FILE, "state.db"]
    assert await door_statuses(env, key, keys.KEY_PREFIX + "x" * 43) == [200, 401]  # made up


async def test_first_connect_on_fresh_state(fresh, capsys):
    assert not fresh.state.exists()
    await _next_connect_is_served(fresh, capsys)  # this connect is the first command of all
    assert connect(fresh, "charlie") == 0  # and every later one works too
    (second,) = keys_in(capsys.readouterr().out)
    assert await door_statuses(fresh, second) == [200]


async def test_first_revoke_on_fresh_state(fresh, capsys):
    assert not fresh.state.exists()
    assert run(fresh, "revoke", "alpha") == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert "revoked alpha (no key was active)" in captured.out
    assert load_manifest(fresh.manifest).agent("alpha").enabled is False
    await _next_connect_is_served(fresh, capsys)


async def test_first_rotate_on_fresh_state(fresh, capsys):
    assert not fresh.state.exists()
    assert run(fresh, "rotate", "alpha") == 1  # listed and enabled, but no key yet: a true refusal
    assert capsys.readouterr().err == "agent has no active key; connect under a new name\n"
    await _next_connect_is_served(fresh, capsys)


@pytest.mark.parametrize("target", ["dangling", "outside file"])
def test_lock_file_link_refused(env, monkeypatch, capsys, target):
    """A connector.lock link, there before the command or appearing after the check, is refused."""
    outside = env.tmp / "outside.txt"
    if target == "outside file":
        outside.write_text("outside content")
        outside.chmod(0o644)
    lock = env.state / adapters.LOCK_FILE
    before = agents_bytes(env)

    def each_writer_refused(link_first: bool) -> None:
        for words in WRITERS:
            lock.unlink(missing_ok=True)
            if link_first:
                lock.symlink_to(outside)
            assert run(env, *words) == 1
            err = capsys.readouterr().err
            assert err.startswith(LOCK_REFUSED + "; ") and err.count("\n") == 1  # one fixed line
            assert str(env.tmp) not in err and "Traceback" not in err

    each_writer_refused(link_first=True)  # there before the command: `open_state` refuses it
    real_open_state = adapters.open_state

    def link_after_check(directory):
        db = real_open_state(directory)
        lock.symlink_to(outside)  # the link appears after `open_state` looked
        return db

    with monkeypatch.context() as m:
        m.setattr(adapters, "open_state", link_after_check)
        each_writer_refused(link_first=False)  # the O_NOFOLLOW open refuses it
    lock.unlink()
    assert agents_bytes(env) == before
    assert keys.has_active_key(env.state, "alpha") and not keys.has_active_key(env.state, "bravo")
    if target == "outside file":
        assert outside.read_text() == "outside content"
        assert stat.S_IMODE(outside.stat().st_mode) == 0o644
    else:
        assert not outside.exists()  # nothing was created through the link


@pytest.mark.parametrize("kind", ["foreign folder", "linked folder"])
def test_lock_never_touches_a_refused_folder(fresh, capsys, kind):
    """The lock comes after every check of `open_state`: a refused folder gets no connector.lock."""
    real = fresh.tmp / "real"
    real.mkdir()
    real.chmod(0o755)
    if kind == "foreign folder":
        (real / "notes.txt").write_text("not ours")
        fresh.state = real
    else:
        fresh.state = fresh.tmp / "link"
        fresh.state.symlink_to(real, target_is_directory=True)
    before = agents_bytes(fresh)
    for words in WRITERS:
        assert run(fresh, *words) == 1
        err = capsys.readouterr().err
        assert err.endswith("not changed; the key state for " + words[1] + " could not be read; run revoke\n")
        assert err.count("\n") == 1 and str(fresh.tmp) not in err
    assert sorted(p.name for p in real.iterdir()) == (["notes.txt"] if kind == "foreign folder" else [])
    assert (real.stat().st_mode & 0o777) == 0o755
    assert agents_bytes(fresh) == before


# -- QA round 3: lock file mode and defences ------------------------------------------------------


def test_existing_lock_file_is_tightened(env, capsys):
    lock = env.state / adapters.LOCK_FILE
    lock.write_text("")
    lock.chmod(0o644)
    assert connect(env) == 0
    assert stat.S_IMODE(lock.stat().st_mode) == 0o600
    capsys.readouterr()


@pytest.mark.parametrize("kind", ["fifo", "hard link"])
def test_lock_swapped_after_open_state_is_refused(env, monkeypatch, capsys, kind):
    """The lock becomes a FIFO or gains a second link after `open_state` and before the open."""
    lock = env.state / adapters.LOCK_FILE
    extra = env.tmp / "second-link"
    before = agents_bytes(env)
    real_open_state = adapters.open_state

    def swap_after_check(directory):
        db = real_open_state(directory)
        if kind == "fifo":
            os.mkfifo(lock)
        else:
            lock.write_text("")
            lock.chmod(0o644)
            os.link(lock, extra)
        return db

    for words in WRITERS:
        lock.unlink(missing_ok=True)
        extra.unlink(missing_ok=True)
        with monkeypatch.context() as m:
            m.setattr(adapters, "open_state", swap_after_check)
            assert run(env, *words) == 1
        err = capsys.readouterr().err
        assert err.startswith(LOCK_REFUSED + "; ") and err.count("\n") == 1
        assert str(env.tmp) not in err
        if kind == "hard link":  # the other link is a file outside the state folder: untouched
            assert stat.S_IMODE(extra.stat().st_mode) == 0o644
    lock.unlink(missing_ok=True)
    extra.unlink(missing_ok=True)
    assert agents_bytes(env) == before
    assert keys.has_active_key(env.state, "alpha") and not keys.has_active_key(env.state, "bravo")


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores folder and file modes")
def test_other_state_error_prints_fixed_line(fresh, capsys):
    """A plain OSError (the parent folder is not writable) gives one fixed line: no path, no trace."""
    parent = fresh.tmp / "closed"
    parent.mkdir()
    fresh.state = parent / "state"
    parent.chmod(0o500)
    try:
        for words in WRITERS:
            assert run(fresh, *words) == 1
            err = capsys.readouterr().err
            assert err == (
                "the state folder could not be opened; "
                f"the key state for {words[1]} could not be read; run revoke\n"
            )
            assert str(fresh.tmp) not in err and "Traceback" not in err
    finally:
        parent.chmod(0o700)
    assert not fresh.state.exists()


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores file modes")
def test_unopenable_lock_has_its_own_text(env, capsys):
    lock = env.state / adapters.LOCK_FILE
    lock.write_text("")
    lock.chmod(0o000)
    try:
        for words in WRITERS:
            assert run(env, *words) == 1
            err = capsys.readouterr().err
            assert err.startswith(adapters.LOCK_UNREADABLE + "; ") and err.count("\n") == 1
            assert LOCK_REFUSED not in err and str(env.tmp) not in err
    finally:
        lock.chmod(0o600)


# -- fixed tools only (Task B3) ----------------------------------------------------------------


def test_connect_fixed_tools_only_writes_the_flag(env, capsys):
    assert connect(env, "bravo", "--fixed-tools-only") == 0
    manifest = load_manifest(env.manifest)
    assert manifest.agent("bravo").pinned_tools is False
    assert manifest.agent("alpha").pinned_tools is True
    assert "pinned_tools: false" in agents_bytes(env).decode()


def test_connect_default_keeps_pinned_tools(env, capsys):
    assert connect(env) == 0
    assert load_manifest(env.manifest).agent("bravo").pinned_tools is True


def test_set_tools_switches_both_ways_without_a_new_key(env, capsys):
    before = keys.has_active_key(env.state, "alpha")
    assert before
    assert run(env, "set-tools", "alpha", "--fixed-only") == 0
    out = capsys.readouterr()
    assert adapters.RELOAD_HINT in out.out
    assert KEY_RE.search(out.out + out.err) is None
    assert load_manifest(env.manifest).agent("alpha").pinned_tools is False
    assert keys.has_active_key(env.state, "alpha")
    assert run(env, "set-tools", "alpha", "--pinned") == 0
    assert load_manifest(env.manifest).agent("alpha").pinned_tools is True
    assert keys.has_active_key(env.state, "alpha")


def test_set_tools_keeps_other_fields(env, capsys):
    assert connect(env, "bravo", "--addons", "drafts") == 0
    assert run(env, "set-tools", "bravo", "--fixed-only") == 0
    agent = load_manifest(env.manifest).agent("bravo")
    assert agent.pinned_tools is False and agent.enabled is True
    assert {a.value for a in agent.addons} == {"drafts"}


def test_set_tools_unknown_agent_changes_nothing(env, capsys):
    before = agents_bytes(env)
    assert run(env, "set-tools", "ghost", "--fixed-only") == 1
    assert agents_bytes(env) == before
    assert "unknown agent" in capsys.readouterr().err


def test_set_tools_needs_exactly_one_flag(env, capsys):
    before = agents_bytes(env)
    with pytest.raises(SystemExit):
        run(env, "set-tools", "alpha")
    with pytest.raises(SystemExit):
        run(env, "set-tools", "alpha", "--fixed-only", "--pinned")
    assert agents_bytes(env) == before


def test_set_tools_uses_the_state_lock(env, monkeypatch, capsys):
    used = []
    real = adapters.state_lock

    def spy(state):
        used.append(state)
        return real(state)

    monkeypatch.setattr(adapters, "state_lock", spy)
    assert run(env, "set-tools", "alpha", "--fixed-only") == 0
    assert used == [env.state]
