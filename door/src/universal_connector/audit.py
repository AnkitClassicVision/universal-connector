"""Audit log and pause flag. The log stores a hash of the arguments, never the arguments."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import sqlite3
from contextlib import closing
from pathlib import Path

from universal_connector.state import now_iso, open_state

PAUSED_FLAG = "paused"


SALT_FLAG = "audit_salt"
NAME_LIMIT = 128


def clean_name(value: object) -> str:
    """Cut to 128 characters and replace every character outside printable ASCII with `?`."""
    text = str(value)[:NAME_LIMIT]
    return "".join(ch if " " <= ch <= "~" else "?" for ch in text)


def _salt(db: sqlite3.Connection) -> bytes:
    """The salt of this state folder: 32 random bytes, made once and kept in `state.db`. Never printed."""
    db.execute(
        "INSERT OR IGNORE INTO flags (name, value) VALUES (?, ?)",
        (SALT_FLAG, secrets.token_hex(32)),
    )
    row = db.execute("SELECT value FROM flags WHERE name = ?", (SALT_FLAG,)).fetchone()
    return bytes.fromhex(row["value"])


def args_digest(salt: bytes, args: dict) -> str:
    """HMAC-SHA256 of the arguments. Without the salt a guessed argument cannot be confirmed."""
    body = json.dumps(args, sort_keys=True, default=str).encode("utf-8")
    return hmac.new(salt, body, hashlib.sha256).hexdigest()


def record(
    directory: Path,
    *,
    agent: str,
    connection: str,
    tool: str,
    tier: str,
    outcome: str,
    duration_ms: int,
    args: dict,
) -> None:
    with closing(open_state(directory)) as db, db:
        digest = args_digest(_salt(db), args)
        db.execute(
            "INSERT INTO audit (ts, agent, connection, tool, tier, outcome, duration_ms, args_sha256) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                now_iso(),
                agent,
                clean_name(connection),
                clean_name(tool),
                tier,
                outcome,
                int(duration_ms),
                digest,
            ),
        )


def tail(directory: Path, n: int = 50) -> list[dict]:
    """Return the newest `n` audit lines, newest first."""
    with closing(open_state(directory)) as db:
        rows = db.execute("SELECT * FROM audit ORDER BY id DESC LIMIT ?", (n,)).fetchall()
    return [dict(row) for row in rows]


def set_paused(directory: Path, paused: bool) -> None:
    with closing(open_state(directory)) as db, db:
        db.execute(
            "INSERT INTO flags (name, value) VALUES (?, ?) "
            "ON CONFLICT(name) DO UPDATE SET value = excluded.value",
            (PAUSED_FLAG, "1" if paused else "0"),
        )


def is_paused(directory: Path) -> bool:
    with closing(open_state(directory)) as db:
        row = db.execute("SELECT value FROM flags WHERE name = ?", (PAUSED_FLAG,)).fetchone()
    return row is not None and row["value"] == "1"


# -- reload requests ---------------------------------------------------------------------------
# `uconnector reload` works on every system, Windows included, where there is no SIGHUP. It adds
# one to a counter in the state folder's own `state.db` (owner-only, never a network listener).
# The running door reads the counter every few seconds; when it moved, the door reloads the
# manifest and writes the counter value and the outcome back, so the command can report it.

RELOAD_REQUEST_FLAG = "reload_request"
RELOAD_DONE_FLAG = "reload_done"
RELOAD_OUTCOME_FLAG = "reload_outcome"


def _flag_int(db: sqlite3.Connection, name: str) -> int:
    row = db.execute("SELECT value FROM flags WHERE name = ?", (name,)).fetchone()
    try:
        return int(row["value"]) if row is not None else 0
    except (TypeError, ValueError):
        return 0


def request_reload(directory: Path) -> int:
    """Ask the running door to reload. Return the request number to wait for."""
    with closing(open_state(directory)) as db:
        db.execute("BEGIN IMMEDIATE")
        with db:
            number = _flag_int(db, RELOAD_REQUEST_FLAG) + 1
            db.execute(
                "INSERT INTO flags (name, value) VALUES (?, ?) "
                "ON CONFLICT(name) DO UPDATE SET value = excluded.value",
                (RELOAD_REQUEST_FLAG, str(number)),
            )
    return number


def reload_requested(directory: Path) -> int:
    """The newest request number. 0 when none was ever made."""
    with closing(open_state(directory)) as db:
        return _flag_int(db, RELOAD_REQUEST_FLAG)


def mark_reloaded(directory: Path, number: int, ok: bool) -> None:
    """The door's answer: request `number` was handled, and whether the new manifest loaded."""
    with closing(open_state(directory)) as db, db:
        for name, value in ((RELOAD_DONE_FLAG, str(number)), (RELOAD_OUTCOME_FLAG, "ok" if ok else "failed")):
            db.execute(
                "INSERT INTO flags (name, value) VALUES (?, ?) "
                "ON CONFLICT(name) DO UPDATE SET value = excluded.value",
                (name, value),
            )


def reload_answer(directory: Path) -> tuple[int, str]:
    """(the last handled request number, `ok` or `failed`). (0, "") before any answer."""
    with closing(open_state(directory)) as db:
        row = db.execute("SELECT value FROM flags WHERE name = ?", (RELOAD_OUTCOME_FLAG,)).fetchone()
        return _flag_int(db, RELOAD_DONE_FLAG), (row["value"] if row is not None else "")
