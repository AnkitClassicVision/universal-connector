#!/usr/bin/env python3
"""Read-only scan of a machine's connections, keys, logins and skills. Names only.

  python tools/scan.py --out <run folder>/01a-scan/output         # writes inventory.json and inventory.md
  python tools/scan.py --json                                    # the inventory as JSON on stdout
  python tools/scan.py --list-sources                            # every plug-in and where it looks
  python tools/scan.py --include-vaults --out DIR                # also list password-manager entry names

Values are read only inside this process, to classify where a key lives (inline,
env reference, file, keyring, vault, OAuth). No value is ever printed, logged,
stored or returned. Every output passes a key-shape guard before it leaves.
Exit codes: 0 done, 2 bad arguments, 3 the guard stopped the output.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from kit import __version__  # noqa: E402
from kit.core import Collector, Ctx, platform_name  # noqa: E402
from kit.plugins import all_plugins  # noqa: E402
from kit.redact import Redactor  # noqa: E402
from kit.report import GuardTripped, build, guard, markdown, summary  # noqa: E402


def make_ctx(args: argparse.Namespace) -> Ctx:
    extra: dict[str, list[Path]] = {}
    for item in args.extra or []:
        key, sep, value = item.partition("=")
        if not sep or not value:
            raise SystemExit("error: --extra takes ID=PATH, for example --extra openmausbot=/path/to/config.json")
        extra.setdefault(key.strip(), []).append(Path(os.path.expanduser(value)))
    projects = [Path(os.path.expanduser(p)).resolve() for p in (args.project or [])] or [Path.cwd()]
    ctx = Ctx(
        home=Path(os.path.expanduser(args.home)) if args.home else Path.home(),
        env=dict(os.environ), platform=args.platform or platform_name(),
        root=Path(args.root) if args.root else Path("/"), projects=projects,
        follow_projects=not args.no_follow_projects, include_vaults=args.include_vaults, extra=extra,
    )
    salt_path = Path(os.path.expanduser(args.salt_file)) if args.salt_file else ctx.xdg_config() / "universal-connector" / "hidden-salt"
    salt, stable = load_salt(salt_path)
    ctx.redactor = Redactor(salt)
    if not stable:
        ctx.notes_for_run.append("Hidden ids are new this run (the salt file could not be kept), so a diff may show them as changed.")
    for url in args.door_url or []:
        host = ctx.redactor.host(url)
        if host:
            ctx.door_hosts.add(host)
    return ctx


def load_salt(path: Path) -> tuple[bytes, bool]:
    """A random salt kept owner-only, so hidden ids stay the same from run to run. (salt, kept)."""
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
        try:
            data = os.read(fd, 256).strip()
        finally:
            os.close(fd)
        if len(data) >= 32:
            return data, True
    except OSError:
        pass
    salt = secrets.token_hex(32).encode()
    try:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(salt + b"\n")
        return salt, True
    except OSError:
        return salt, False


def pick(plugins, only: str | None, skip: str | None):
    known = {p.id for p in plugins}
    wanted = {x.strip() for x in only.split(",")} if only else None
    dropped = {x.strip() for x in skip.split(",")} if skip else set()
    unknown = ((wanted or set()) | dropped) - known
    if unknown:
        raise SystemExit(f"error: unknown source id(s): {', '.join(sorted(unknown))}. See --list-sources.")
    return [p for p in plugins if (wanted is None or p.id in wanted) and p.id not in dropped]


def run(ctx: Ctx, plugins) -> list[tuple]:
    results = []
    for plugin in plugins:
        col = Collector(plugin.id, ctx)
        try:
            plugin.scan(ctx, col)
        except Exception:  # noqa: BLE001 - a plug-in bug must not stop the scan or quote content
            col.findings.clear()
            col.skills.clear()
            col.look(f"{plugin.id} plug-in", "error")
            col.notes.append(f"The {plugin.id} plug-in failed. Nothing from it is in this inventory. Please report it.")
        results.append((plugin, col))
    return results


def write_private(path: Path, text: str) -> None:
    """Owner-only, never through a link; an existing file is set back to 0600 before it is written."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        os.fchmod(handle.fileno(), 0o600)
        handle.write(text)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", help="folder for inventory.json and inventory.md (created, owner-only)")
    ap.add_argument("--json", action="store_true", help="print the inventory as JSON instead of the summary")
    ap.add_argument("--list-sources", action="store_true", help="print every plug-in and where it looks, then stop")
    ap.add_argument("--include-vaults", action="store_true", help="also list entry names in password managers and keyrings")
    ap.add_argument("--project", action="append", help="a project folder to check (repeat); default: the current folder")
    ap.add_argument("--no-follow-projects", action="store_true", help="do not follow project folders named in harness configs")
    ap.add_argument("--extra", action="append", help="ID=PATH: an extra file for a plug-in (openmausbot=..., mcp=...)")
    ap.add_argument("--door-url", action="append", help="your door's address (repeat for a route): entries for it are expected")
    ap.add_argument("--salt-file", help="where the owner-only salt for stable hidden ids lives "
                                        "(default ~/.config/universal-connector/hidden-salt)")
    ap.add_argument("--only", help="comma list of source ids to run")
    ap.add_argument("--skip", help="comma list of source ids to skip")
    ap.add_argument("--home", help=argparse.SUPPRESS)  # tests: a fixture home
    ap.add_argument("--root", help=argparse.SUPPRESS)  # tests: a fixture root for /etc and /proc
    ap.add_argument("--platform", choices=["linux", "darwin", "windows"], help=argparse.SUPPRESS)
    ap.add_argument("--version", action="version", version=f"universal-connector scan {__version__}")
    args = ap.parse_args(argv)

    ctx = make_ctx(args)
    plugins = pick(all_plugins(), args.only, args.skip)
    try:
        if args.list_sources:
            lines = []
            for p in plugins:
                lines.append(f"{p.id}  [{p.group}{', opt-in' if p.opt_in else ''}]  {p.label}")
                lines += [f"    {w}" for w in p.where(ctx)]
            sys.stdout.write(guard("\n".join(lines) + "\n"))
            return 0
        results = run(ctx, plugins)
        if ctx.notes_for_run and results:
            results[0][1].notes.extend(ctx.notes_for_run)
        inv = build(ctx, results)
        as_json = guard(json.dumps(inv, indent=2, sort_keys=False) + "\n")
        sheet = guard(markdown(inv))
        text = guard(summary(inv))
        if args.out:
            out = Path(args.out)
            if out.is_symlink():
                sys.stderr.write("error: --out is a link; give a real folder\n")
                return 2
            out.mkdir(parents=True, exist_ok=True, mode=0o700)
            try:
                write_private(out / "inventory.json", as_json)
                write_private(out / "inventory.md", sheet)
            except OSError:
                sys.stderr.write("error: could not write the inventory (a file there may be a link); nothing was written through it\n")
                return 2
            text += f"Wrote {ctx.show(out / 'inventory.json')} and inventory.md (owner-only).\n"
        sys.stdout.write(as_json if args.json else text)
        return 0
    except GuardTripped as exc:
        sys.stderr.write(f"Stopped: a key-shaped string reached the output (rules: {exc}). Nothing was written. "
                         "Please report this as a bug.\n")
        return 3


if __name__ == "__main__":
    sys.exit(main())
