"""The checks for the gotchas the reference build hit. Pure functions; no network.

  tool names     a full tool name over the harness limit (64 for most model APIs) is refused
  read limit     the client must wait longer than the door's slowest call
  host           a tailnet route keeps its own Host header; the door must list it exactly
  origin         a request with an Origin header must be refused (keeps browser pages out)
  cursors        list results must drop paging cursors (they trip key-shaped scans)
  first page     some harnesses read only the first page of tools/list
  read only      Oddboro's exact rule for what a Read only grant reaches; this kit uses it before any smoke call
  tiers          a tool the plan did not make green or yellow must not be offered
"""

from __future__ import annotations

import fnmatch
import json
import re
from typing import Any

from kit.harnesses import HARNESSES, full_tool_name
from kit.keyshape import rule_hits

CURSOR_KEYS = {"nextpagetoken", "nextcursor", "pagetoken", "cursor", "next_page_token", "next_cursor",
               "continuationtoken", "continuation", "nextlink", "@odata.nextlink", "next_page", "starting_after"}

# Oddboro's own list of change words, word for word: 42 words. A read tool with one
# of them anywhere among its name's words (`get_post`) is left out too: the rule errs toward less.
CHANGES = frozenset("""
add append approve archive assign cancel capture clear close comment create delete destroy drop edit exec
execute forward insert invite merge modify move patch post publish put remove rename reply reset run save send
set share store submit update upload upsert write
""".split())


def name_words(name: str) -> list[str]:
    """`multica_create_issue`, `createIssue` and `create-issue` all give create and issue (Oddboro's nameWords)."""
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", str(name)).lower()
    return [w for w in re.split(r"[^a-z0-9]+", spaced) if w]


def read_only_reachable(tool: dict) -> tuple[bool, str]:
    """Oddboro's `readsOnly`: readOnlyHint === true, destructiveHint !== true, no change word. (yes or no, why not)."""
    ann = tool.get("annotations") if isinstance(tool.get("annotations"), dict) else {}
    if ann.get("readOnlyHint") is not True:
        return False, "readOnlyHint is not true"
    if ann.get("destructiveHint") is True:
        return False, "destructiveHint is true"
    hit = next((w for w in name_words(str(tool.get("name", ""))) if w in CHANGES), None)
    if hit:
        return False, f"its name has the change word '{hit}'"
    return True, ""


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


def plan_tier(manifest: dict, tool_name: str) -> str | None:
    """The plan's tier for a door tool named `<connection>__<tool>`: the first matching rule, else red.

    None when the name does not start with a connection in the plan (one of the door's own tools).
    """
    conn, sep, tool = str(tool_name).partition("__")
    if not sep:
        return None
    for c in manifest.get("connections") or []:
        if isinstance(c, dict) and c.get("name") == conn:
            for rule in c.get("tools") or []:
                if isinstance(rule, dict) and fnmatch.fnmatchcase(tool, str(rule.get("match", ""))):
                    return str(rule.get("tier", "red"))
            return "red"
    return None


def tools_diff(old: list[dict], new: list[dict]) -> dict[str, list[str]]:
    """New tools (and of those, the ones Oddboro's rule would not call read-only) and removed tools."""
    old_names = {str(t.get("name")) for t in old}
    new_by_name = {str(t.get("name")): t for t in new}
    added = sorted(set(new_by_name) - old_names)
    return {
        "added": added,
        "added_not_read_only": [n for n in added if not read_only_reachable(new_by_name[n])[0]],
        "removed": sorted(old_names - set(new_by_name)),
    }


def tool_marks(tools: list[dict]) -> list[dict]:
    """What may be saved of a tools/list: names and annotations only, never descriptions or schemas."""
    out = []
    for t in tools:
        ann = t.get("annotations") if isinstance(t.get("annotations"), dict) else {}
        out.append({"name": str(t.get("name")), "annotations": {k: ann[k] for k in ("readOnlyHint", "destructiveHint") if k in ann}})
    return out
