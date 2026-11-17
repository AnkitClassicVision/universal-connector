"""Scan plug-ins. Each one says where it looks and returns names, kinds and locations.

Add a plug-in: write a `paths(ctx)` (or a `where(ctx)`) and a `scan(ctx, col)` in one of
the modules here, then add one `Plugin(...)` line to that module's `PLUGINS` list.
A plug-in must:
  - never raise on a missing, unreadable or malformed file (use `kit.core.load`)
  - never put a value into a Finding (only names through `ctx.redactor`)
  - record every place it looked with `col.look(path, status)`
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kit.classify import PLAIN, classify_entry, how_to_add
from kit.core import Collector, Ctx, Finding
from kit.redact import risky


@dataclass(frozen=True)
class Plugin:
    id: str
    label: str
    group: str  # harness | skills | environment | cli-login | vault | runtime
    where: Callable[[Ctx], list[str]]
    scan: Callable[[Ctx, Collector], None]
    opt_in: bool = False


def shown(ctx: Ctx, path: Path | str) -> str:
    """A location for output. A path that itself looks like a key is hidden."""
    text = ctx.show(path) if isinstance(path, Path) else str(path)
    return ctx.redactor.hide(text) if risky(text) else text


def server_items(servers: Any) -> list[tuple[str, dict]]:
    """(name, entry) pairs from a map, or from a list of entries that carry a name."""
    if isinstance(servers, dict):
        return [(str(k), v) for k, v in servers.items() if isinstance(v, dict)]
    if isinstance(servers, list):
        out = []
        for i, s in enumerate(servers, 1):
            if isinstance(s, dict):
                out.append((str(s.get("name") or s.get("id") or f"server-{i}"), s))
        return out
    return []


def add_servers(ctx: Ctx, col: Collector, servers: Any, location: str, kind: str = "mcp-server") -> int:
    count = 0
    for name, entry in server_items(servers):
        c = classify_entry(entry, ctx.redactor)
        f = Finding(source=col.source, location=location, kind=kind, name=ctx.redactor.name(name), **c)
        f.plain_file = bool(set(f.key_where) & PLAIN)
        f.how_to_add = how_to_add(f)
        col.add(f)
        count += 1
    return count


def all_plugins() -> list[Plugin]:
    from kit.plugins import cli_logins, environment, harnesses, runtime, skills, vaults

    plugins: list[Plugin] = []
    for module in (harnesses, skills, environment, cli_logins, vaults, runtime):
        plugins.extend(module.PLUGINS)
    ids = [p.id for p in plugins]
    if len(ids) != len(set(ids)):
        raise RuntimeError("two plug-ins share an id")
    return plugins
