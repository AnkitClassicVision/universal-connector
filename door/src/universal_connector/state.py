"""Local state: one owner-only SQLite file for key hashes, the audit log and flags."""

from __future__ import annotations

import errno
import os
import sqlite3
import stat
from datetime import UTC, datetime
from pathlib import Path

from universal_connector import portable

DB_NAME = "state.db"
# The database's own side files. Exactly these names, nothing that merely starts with `state.db`.
SIDE_FILES = frozenset({"state.db-journal", "state.db-wal", "state.db-shm"})
# The key-change lock (`adapters.state_lock`). A known state file, but only as a regular file with one link.
LOCK_NAME = "connector.lock"
LOCK_REFUSED = "connector.lock must be a regular file with one link; not changed"
KNOWN_FILES = SIDE_FILES | {DB_NAME, LOCK_NAME}

SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_keys (
    agent TEXT PRIMARY KEY,
    key_sha256 TEXT NOT NULL,
    created_at TEXT NOT NULL,
    revoked_at TEXT
);
CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY,
    ts TEXT,
    agent TEXT,
    connection TEXT,
    tool TEXT,
    tier TEXT,
    outcome TEXT,
    duration_ms INTEGER,
    args_sha256 TEXT
);
CREATE TABLE IF NOT EXISTS flags (
    name TEXT PRIMARY KEY,
    value TEXT
);
"""


class StateDirError(Exception):
    """The state folder exists, holds other files and has no `state.db`. Nothing was changed."""


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


def open_state(directory: Path) -> sqlite3.Connection:
    """Open `directory/state.db`. Create the folder and file when missing. Always set 0700 and 0600."""
    directory = Path(directory)
    # A state folder that is itself a link is refused before anything is created or changed.
    try:
        folder = os.lstat(directory)
    except FileNotFoundError:
        folder = None
    if folder is not None and stat.S_ISLNK(folder.st_mode):
        raise StateDirError("state folder is a symbolic link; not changed")
    # exist_ok: several first callers can race to create the folder.
    directory.mkdir(parents=True, mode=0o700, exist_ok=True)
    path = directory / DB_NAME
    # Every check runs before any chmod or write. lstat, never exists(): a dangling link must not pass.
    for side in SIDE_FILES:
        try:
            side_stat = os.lstat(directory / side)
        except FileNotFoundError:
            continue
        if not stat.S_ISREG(side_stat.st_mode):
            raise StateDirError("a state.db side file is not a regular file; not changed")
    try:
        lock = os.lstat(directory / LOCK_NAME)
    except FileNotFoundError:
        lock = None
    if lock is not None and (not stat.S_ISREG(lock.st_mode) or lock.st_nlink != 1):
        raise StateDirError(LOCK_REFUSED)
    try:
        found = os.lstat(path)
    except FileNotFoundError:
        found = None
    if found is not None and not stat.S_ISREG(found.st_mode):
        raise StateDirError("state.db is not a regular file; not changed")
    if found is not None and found.st_nlink != 1:
        raise StateDirError("state.db has more than one hard link; not changed")
    if found is None and any(entry.name not in KNOWN_FILES for entry in directory.iterdir()):
        # `state.db` itself is allowed here: another first caller may have just created it.
        # `connector.lock` too: an older build made it before `state.db` on a new folder.
        raise StateDirError("state folder holds other files and no state.db; not changed")
    portable.owner_only_folder(directory)
    try:
        fd = portable.open_no_link(path, os.O_CREAT | os.O_RDWR, 0o600)
    except OSError as exc:
        # A link appeared after the check. Without O_NOFOLLOW (Windows) `LinkRefused` says so.
        if isinstance(exc, portable.LinkRefused) or exc.errno == getattr(errno, "ELOOP", None):
            raise StateDirError("state.db is not a regular file; not changed") from None
        raise
    try:
        portable.owner_only_file(fd)
        db = sqlite3.connect(path)
        # The descriptor stays open until here. The path must still name the file we opened.
        try:
            opened = os.fstat(fd)
            now = os.lstat(path)
        except OSError:
            db.close()
            raise StateDirError("state.db changed while opening; not used") from None
        if (
            (opened.st_dev, opened.st_ino) != (now.st_dev, now.st_ino)
            or not stat.S_ISREG(now.st_mode)
            or now.st_nlink != 1
        ):
            db.close()
            raise StateDirError("state.db changed while opening; not used")
    finally:
        os.close(fd)
    db.row_factory = sqlite3.Row
    db.executescript(SCHEMA)
    return db
