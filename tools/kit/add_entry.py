"""Add one door entry to a harness config, in this process, without anyone opening the file.

Harness configs often hold other inline keys. An agent that opens one with an editor reads all of
them into its context, so agents never open them. This module reads the config here, checks it
parses, copies it to an owner-only backup in the run folder, adds one entry, checks the result
parses and keeps every earlier entry, and replaces the file atomically. It prints only what it did.

Formats: JSON (`mcpServers` or `servers`), JSON with comments (refused unless --allow-rewrite, which
drops the comments), TOML (a table appended), YAML (an entry inserted under the existing block, so
comments stay; a full rewrite only with --allow-rewrite).
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from kit.core import FOUND, MISSING, _strip_jsonc, load_yaml, read_bytes
from kit.harnesses import PLAIN_KEY, entry_body, entry_problem, toml_table
from kit.smoke import load_key

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    tomllib = None  # type: ignore[assignment]
try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover
    yaml = None  # type: ignore[assignment]

FORMATS: dict[str, tuple[str, str]] = {
    "claude-code": ("json", "mcpServers"),    # a project's .mcp.json; user scope uses `claude mcp add-json`
    "claude-desktop": ("json", "mcpServers"),
    "cursor": ("json", "mcpServers"),
    "windsurf": ("json", "mcpServers"),
    "vscode": ("jsonc", "servers"),
    "cline": ("json", "mcpServers"),
    "zed": ("jsonc", "context_servers"),
    "goose": ("yaml", "extensions"),
    "hermes": ("yaml", "mcp_servers"),
    "openmausbot": ("json", "mcpServers"),
    "codex": ("toml", "mcp_servers"),
}


class Refused(Exception):
    """A fixed reason; nothing was changed. The text never holds file content."""


def _parse(text: str, fmt: str) -> Any:
    try:
        if fmt == "toml":
            return tomllib.loads(text)
        if fmt == "yaml":
            return load_yaml(text) or {}
        return json.loads(text)
    except Exception:  # noqa: BLE001 - parser errors can quote content
        return None


def _body(a, harness: str) -> tuple[dict, str]:
    """(entry, how the key is held)."""
    if harness == "claude-desktop":
        if not a.bridge_command or not a.key_file:
            raise Refused("Claude Desktop needs --bridge-command (the local bridge) and --key-file (its path goes in the entry)")
        return ({"command": a.bridge_command, "args": [a.url], "env": {"DOOR_KEY_FILE": str(Path(a.key_file).expanduser())}},
                "the bridge reads it from the key file at start (only the path is in the config)")
    if harness in PLAIN_KEY or (harness in ("cursor", "windsurf") and a.key_file):
        if not a.key_file:
            raise Refused(f"{harness} keeps the door key in its own config: pass --key-file with this harness's door key")
        key, problem = load_key(a.key_file)
        if not key:
            raise Refused(problem)
        return entry_body(harness, a.url, a.key_env, a.name, a.read_timeout, key=key), \
            "written into the config from the key file, here, never shown (this harness keeps it in plain text)"
    return entry_body(harness, a.url, a.key_env, a.name, a.read_timeout), f"by reference ({a.key_env})"


def _yaml_insert(text: str, top: str, name: str, body: dict) -> str | None:
    """Insert `name: body` under an existing `top:` block, matching its indent. None if the block is not a plain mapping."""
    lines = text.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if re.match(rf"^{re.escape(top)}:\s*(#.*)?$", line.rstrip("\n")):
            indent = None
            for nxt in lines[i + 1:]:
                if nxt.strip() and not nxt.lstrip().startswith("#"):
                    lead = len(nxt) - len(nxt.lstrip(" "))
                    indent = lead if lead > 0 else None
                    break
            indent = indent or 2
            block = yaml.safe_dump({name: body}, sort_keys=False, default_flow_style=False, indent=2)
            pad = " " * indent
            new = "".join(pad + ln if ln.strip() else ln for ln in block.splitlines(keepends=True))
            return "".join(lines[: i + 1]) + new + "".join(lines[i + 1:])
    return None


def build(a, harness: str, original: str | None) -> tuple[str, str]:
    """(new text, how the key is held). Raises Refused."""
    fmt, top = FORMATS[harness]
    body, held = _body(a, harness)
    if original is None:
        data: Any = {}
    else:
        data = _parse(original, "json" if fmt == "jsonc" else fmt)
        if data is None and fmt == "jsonc":
            if not a.allow_rewrite:
                raise Refused("this file has comments or trailing commas; add the entry in the harness's own settings, "
                              "or pass --allow-rewrite, which writes it back without comments")
            data = _parse(_strip_jsonc(original), "json")
        if not isinstance(data, dict):
            raise Refused("the config does not parse; nothing was changed. Fix it in the harness first")
    block = data.get(top)
    if block is not None and not isinstance(block, dict):
        raise Refused(f"'{top}' in this file is not a map of entries; add the entry with the harness's own command")
    if isinstance(block, dict) and a.name in block and not a.replace:
        raise Refused(f"an entry named {a.name} is already there; pick another --name or pass --replace")

    if fmt in ("json", "jsonc"):
        data.setdefault(top, {})[a.name] = body
        if harness == "vscode":
            inputs = [i for i in data.get("inputs") or [] if isinstance(i, dict) and i.get("id") != f"{a.name}-key"]
            inputs.append({"type": "promptString", "id": f"{a.name}-key", "description": "Door key", "password": True})
            data["inputs"] = inputs
        return json.dumps(data, indent=2) + "\n", held
    if fmt == "toml":
        if a.name in (block or {}):
            raise Refused("replacing a TOML table is not supported; remove the old one with the harness's own command")
        return (original or "").rstrip("\n") + ("\n\n" if original else "") + toml_table(a.name, body), held
    # yaml
    if block is None:
        tail = yaml.safe_dump({top: {a.name: body}}, sort_keys=False, default_flow_style=False)
        return (original or "").rstrip("\n") + ("\n" if original else "") + tail, held
    if a.name not in block:
        inserted = _yaml_insert(original or "", top, a.name, body)
        if inserted is not None:
            return inserted, held
    if not a.allow_rewrite:
        raise Refused("this YAML block cannot be extended in place; use the harness's own command, "
                      "or pass --allow-rewrite, which writes the file back without comments")
    data[top][a.name] = body
    return yaml.safe_dump(data, sort_keys=False, default_flow_style=False), held


def verify(harness: str, original: str | None, new: str, name: str, url: str) -> None:
    fmt, top = FORMATS[harness]
    after = _parse(new, "json" if fmt == "jsonc" else fmt)
    if not isinstance(after, dict) or not isinstance(after.get(top), dict) or name not in after[top]:
        raise Refused("the new file did not check out; nothing was changed")
    entry_text = json.dumps(after[top][name])
    if url not in entry_text:
        raise Refused("the new entry did not check out; nothing was changed")
    if original is not None:
        before = _parse(original, "json" if fmt == "jsonc" else fmt) or _parse(_strip_jsonc(original), "json") or {}
        if not set(before) <= set(after) or not set(before.get(top) or {}) <= set(after[top]):
            raise Refused("the new file would lose an earlier entry; nothing was changed")


def _private_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path, 0o700)


def run(a, out) -> int:
    harness = a.harness
    problem = entry_problem(a.url, a.key_env, a.name)
    if problem:
        raise Refused(problem)
    cfg = Path(a.config).expanduser()
    real = Path(os.path.realpath(cfg))
    backup_dir = Path(a.backup_dir).expanduser().resolve()
    if backup_dir == real.parent or real.parent in backup_dir.parents:
        raise Refused("backups go in the run folder, never beside the config: pick a --backup-dir outside its folder")
    status, raw = read_bytes(real)
    if status == MISSING:
        original = None
    elif status != FOUND or raw is None:
        raise Refused("the config is not a regular readable file; nothing was changed")
    else:
        try:
            original = raw.decode("utf-8")
        except UnicodeDecodeError:
            raise Refused("the config is not UTF-8 text; nothing was changed") from None
    new, held = build(a, harness, original)
    verify(harness, original, new, a.name, a.url)
    shown = str(cfg).replace(str(Path.home()), "~", 1)
    if a.dry_run:
        out.write(f"dry run: would add entry {a.name} to {shown} ({harness}); key {held}. Nothing written.\n")
        return 0
    _private_dir(backup_dir)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backup = backup_dir / f"{harness}-{real.name}.{stamp}.bak"
    if raw is not None:
        fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
    mode = (real.stat().st_mode & 0o777) if original is not None else 0o600
    if harness in PLAIN_KEY or (harness in ("cursor", "windsurf") and a.key_file):
        mode &= 0o600  # the file now holds a door key: owner only
    real.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=real.parent, prefix=f".{real.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(new)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, mode or 0o600)
        os.replace(tmp, real)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    out.write(f"added entry {a.name} to {shown} ({harness}, method add_entry)\n")
    out.write(f"backup: {str(backup).replace(str(Path.home()), '~', 1) if raw is not None else 'none (new file)'} (0600)\n")
    out.write(f"key: {held}\n")
    out.write("rollback: copy the backup back over the config (or delete the new file), then restart the harness\n")
    return 0
