"""The checks for the gotchas the reference build hit. Pure functions; no network.

  tool names     a full tool name over the harness limit (64 for most model APIs) is refused
  read limit     the client must wait longer than the door's slowest call
  host           a tailnet route keeps its own Host header; the door must list it exactly
  origin         a request with an Origin header must be refused (keeps browser pages out)
  cursors        list results must drop paging cursors (they trip key-shaped scans)
  first page     some harnesses read only the first page of tools/list
  read only      a Read only grant reaches a tool only when it is marked read-only and has no change word
"""

from __future__ import annotations

import json
import re
from typing import Any

from kit.harnesses import HARNESSES, full_tool_name
from kit.keyshape import rule_hits

CURSOR_KEYS = {"nextpagetoken", "nextcursor", "pagetoken", "cursor", "next_page_token", "next_cursor",
               "continuationtoken", "continuation", "nextlink", "@odata.nextlink", "next_page", "starting_after"}
CHANGE_WORDS = re.compile(
    r"(?i)(^|[_\-.])(create|update|delete|remove|send|post|write|put|patch|set|add|move|cancel|archive|"
    r"edit|modify|insert|upsert|drop|publish|deploy|pay|refund|invite|share|grant|revoke|reply|forward|merge)"
    r"([_\-.]|$)"
)


def long_names(harness: str, server: str, tools: list[str]) -> list[tuple[str, int]]:
    """(full name, length) for every tool over the harness's limit."""
    limit = HARNESSES[harness].name_limit
    out = []
    for t in tools:
        full = full_tool_name(harness, server, t)
        if len(full) > limit:
            out.append((full, len(full)))
    return out


def cursor_paths(value: Any, path: str = "$") -> list[str]:
    """JSON paths of paging cursors anywhere in a result, including JSON inside text content."""
    found: list[str] = []
    if isinstance(value, dict):
        for k, v in value.items():
            p = f"{path}.{k}"
            if str(k).lower() in CURSOR_KEYS and v not in (None, "", [], {}):
                found.append(p)
            found += cursor_paths(v, p)
    elif isinstance(value, list):
        for i, v in enumerate(value[:500]):
            found += cursor_paths(v, f"{path}[{i}]")
    elif isinstance(value, str) and value.strip()[:1] in "{[":
        try:
            found += cursor_paths(json.loads(value), path + "<text>")
        except ValueError:
            pass
    return found


def key_shapes_in(value: Any) -> list[str]:
    """Rule names (never the text) of key shapes anywhere in a result."""
    try:
        text = json.dumps(value)
    except (TypeError, ValueError):
        text = str(value)
    return rule_hits(text)


def read_limit_ok(elapsed: float, client_timeout: float, margin: float = 0.8) -> bool:
    """The call must finish well inside the client's read timeout."""
    return elapsed < client_timeout * margin


def host_allowed(route_host: str, door_hosts: list[str]) -> bool:
    """The door must list the route's Host exactly (no wildcard guessing)."""
    return route_host.strip().lower() in {h.strip().lower() for h in door_hosts}


def read_only_reachable(tool: dict) -> tuple[bool, str]:
    """Would a Read only grant reach this tool? (yes or no, and why not)."""
    ann = tool.get("annotations") if isinstance(tool.get("annotations"), dict) else {}
    name = str(tool.get("name", ""))
    if ann.get("readOnlyHint") is not True:
        return False, "readOnlyHint is not true"
    if "destructiveHint" in ann:
        return False, "it carries a destructiveHint"
    if CHANGE_WORDS.search(name):
        return False, "its name has a change word"
    return True, ""
