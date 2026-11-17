"""Connector keys. Only the SHA-256 hex of a key is stored. The key is shown once at mint."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from contextlib import closing
from pathlib import Path

from universal_connector.state import now_iso, open_state

KEY_PREFIX = "pc_"
KEY_LENGTH = len(KEY_PREFIX) + 43


class KeyExists(Exception):
    """The agent already holds an active key."""


class NoActiveKey(Exception):
    """Rotate needs an active key. A revoked or never-minted agent cannot be rotated back in."""


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _active(db, agent: str) -> bool:
    row = db.execute(
        "SELECT 1 FROM agent_keys WHERE agent = ? AND revoked_at IS NULL", (agent,)
    ).fetchone()
    return row is not None


def _mint(db, agent: str) -> str:
    if _active(db, agent):
        raise KeyExists(f"agent {agent} already has an active key")
    key = KEY_PREFIX + secrets.token_urlsafe(32)
    db.execute(
        "INSERT INTO agent_keys (agent, key_sha256, created_at, revoked_at) VALUES (?, ?, ?, NULL) "
        "ON CONFLICT(agent) DO UPDATE SET key_sha256 = excluded.key_sha256, "
        "created_at = excluded.created_at, revoked_at = NULL",
        (agent, _sha256(key), now_iso()),
    )
    return key


def _revoke(db, agent: str) -> bool:
    cur = db.execute(
        "UPDATE agent_keys SET revoked_at = ? WHERE agent = ? AND revoked_at IS NULL",
        (now_iso(), agent),
    )
    return cur.rowcount > 0


def mint(directory: Path, agent: str) -> str:
    """Create a key for `agent` and return it. Raise `KeyExists` if one is active.

    The check and the write share one `BEGIN IMMEDIATE` transaction, so two callers cannot both win.
    """
    with closing(open_state(directory)) as db:
        db.execute("BEGIN IMMEDIATE")
        with db:
            return _mint(db, agent)


def verify(directory: Path, presented: str) -> str | None:
    """Return the agent whose active key is `presented`, or None."""
    if not isinstance(presented, str) or len(presented) != KEY_LENGTH:
        return None
    if not presented.startswith(KEY_PREFIX):
        return None
    try:
        digest = _sha256(presented)
    except UnicodeEncodeError:
        return None
    with closing(open_state(directory)) as db:
        rows = db.execute(
            "SELECT agent, key_sha256 FROM agent_keys WHERE revoked_at IS NULL"
        ).fetchall()
    found: str | None = None
    for row in rows:
        if hmac.compare_digest(row["key_sha256"], digest):
            found = row["agent"]
    return found


def revoke(directory: Path, agent: str) -> bool:
    """Revoke the active key. Return False when there was none. Safe to repeat."""
    with closing(open_state(directory)) as db, db:
        return _revoke(db, agent)


def rotate(directory: Path, agent: str) -> str:
    """Revoke the current key and mint a new one in one transaction.

    Raise `NoActiveKey` when the agent has no active key, so rotate never restores access.
    """
    with closing(open_state(directory)) as db:
        db.execute("BEGIN IMMEDIATE")
        with db:
            if not _active(db, agent):
                raise NoActiveKey(f"agent {agent} has no active key")
            _revoke(db, agent)
            return _mint(db, agent)


def has_active_key(directory: Path, agent: str) -> bool:
    with closing(open_state(directory)) as db:
        return _active(db, agent)
