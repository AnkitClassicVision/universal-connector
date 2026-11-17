"""Shared parts of the smoke tests: the key, the check list, and safe output.

The key comes from an environment variable or a 0600 file, never from the command
line (other users can read command lines). It is never printed. Results are
never printed either: only counts, names, timings and pass or fail.
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


def load_key(key_env: str | None, key_file: str | None, env: dict[str, str]) -> tuple[str | None, str]:
    """(key, problem). The key stays in memory."""
    if key_file:
        p = Path(os.path.expanduser(key_file))
        try:
            st = p.stat()
        except OSError:
            return None, "the key file does not exist"
        if os.name == "posix" and st.st_mode & (stat.S_IRWXG | stat.S_IRWXO):
            return None, "the key file can be read by other users; run chmod 600 on it"
        try:
            key = p.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeDecodeError):
            return None, "the key file could not be read"
        return (key or None), ("" if key else "the key file is empty")
    name = key_env or "DOOR_KEY"
    key = env.get(name, "").strip()
    return (key or None), ("" if key else f"environment variable {name} is not set")


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
