"""Shared parts of the smoke tests: the key, the check list, and safe output.

The key comes only from a regular 0600 file the person made, read here in this
process (`--key-file`). It is never taken from the command line, where other users
can read it, and never printed. Results are never printed either: only counts,
names, timings and pass or fail.
"""

from __future__ import annotations

import json
import os
import stat
import sys
from dataclasses import dataclass, field
from pathlib import Path

from kit.redact import Redactor
from kit.report import GuardTripped, guard

PASS, FAIL, WARN, SKIP = "PASS", "FAIL", "WARN", "SKIP"


@dataclass
class Checks:
    title: str
    rows: list[tuple[str, str, str]] = field(default_factory=list)
    red: Redactor = field(default_factory=Redactor)

    def add(self, check: str, result: str, note: str = "") -> None:
        self.rows.append((check, result, note))

    @property
    def ok(self) -> bool:
        return all(r != FAIL for _, r, _ in self.rows)

    def as_dict(self) -> dict:
        return {"title": self.title, "ok": self.ok,
                "checks": [{"check": c, "result": r, "note": n} for c, r, n in self.rows]}

    def text(self) -> str:
        width = max((len(c) for c, _, _ in self.rows), default=10)
        lines = [f"{'PASS' if self.ok else 'FAIL'}  {self.title}"]
        lines += [f"  {r:<4}  {c:<{width}}  {n}".rstrip() for c, r, n in self.rows]
        return "\n".join(lines) + "\n"


def load_key(key_file: str) -> tuple[str | None, str]:
    """(key, problem). The key is read here, in this process, from a file only, and stays in memory.

    The agent passes the path, never the value, and no key is ever put in an environment variable.
    The file must be a regular file (no link, no pipe), readable only by its owner.
    """
    p = Path(os.path.expanduser(key_file))
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        fd = os.open(p, flags)
    except OSError:
        return None, "the key file does not exist, or is a link"
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            return None, "the key file is not a regular file"
        if os.name == "posix" and st.st_mode & (stat.S_IRWXG | stat.S_IRWXO):
            return None, "the key file can be read by other users; run chmod 600 on it"
        if st.st_size > 64_000:
            return None, "the key file is too large to be one key"
        raw = os.read(fd, 64_000)
    except OSError:
        return None, "the key file could not be read"
    finally:
        os.close(fd)
    try:
        key = raw.decode("utf-8").strip()
    except UnicodeDecodeError:
        return None, "the key file is not text"
    if "\n" in key:
        return None, "the key file holds more than one line; it must hold one key only"
    return (key or None), ("" if key else "the key file is empty")


def load_plan(path: str) -> dict | None:
    """The 02-plan manifest (YAML, no aliases), or None."""
    from kit.core import FOUND, parse, read_text

    status, text = read_text(Path(os.path.expanduser(path)))
    if text is None:
        return None
    status, data = parse(text, "yaml")
    return data if status == FOUND and isinstance(data, dict) else None


def write_private_json(path: str, data) -> None:
    """Write JSON at mode 0600, never through a link."""
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(os.path.expanduser(path), flags, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        os.fchmod(handle.fileno(), 0o600)
        handle.write(json.dumps(data, indent=2) + "\n")


def emit(checks: Checks, as_json: bool, out=None) -> int:
    out = out or sys.stdout
    try:
        text = json.dumps(checks.as_dict(), indent=2) + "\n" if as_json else checks.text()
        out.write(guard(text))
    except GuardTripped as exc:
        sys.stderr.write(f"Stopped: output matched a key-shape rule ({exc}); nothing printed. Please report it.\n")
        return 3
    return 0 if checks.ok else 1


def parse_args_json(text: str | None) -> dict | None:
    if not text:
        return {}
    try:
        value = json.loads(text)
    except ValueError:
        return None
    return value if isinstance(value, dict) else None
