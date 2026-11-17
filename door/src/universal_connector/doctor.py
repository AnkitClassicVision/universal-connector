"""The doctor: one read-only health row per connection. It starts no login and writes nothing.

Per connection the order is: `store.exists` for each named vault entry, then `probe`, then
`list_tools` compared with the manifest. Every text in a row is fixed or built from manifest
names, so a row never carries an upstream's error text or a secret value.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from universal_connector.models import Connection, Manifest
from universal_connector.scan import find_secrets
from universal_connector.upstreams.base import Upstream, UpstreamAuthError
from universal_connector.vault import SecretStore, SecretUnavailable

OK = "ok"
NOT_IN_VAULT = "not-in-vault"
NEEDS_LOGIN = "needs-login"
DEAD = "dead"
UNLISTED = "unlisted-tools"
HEALTHY = {OK, UNLISTED}  # unlisted tools are information, not a fault
PRECEDENCE = [NOT_IN_VAULT, NEEDS_LOGIN, DEAD, UNLISTED, OK]

CALL_TIMEOUT_S = 30
NAME_LIMIT = 10
SAFE_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}")


@dataclass
class Row:
    connection: str
    status: str  # one of: ok, not-in-vault, needs-login, dead, unlisted-tools
    detail: str
    action: str


def _is_fixture(conn: Connection) -> bool:
    if conn.auth.type != "none" or not conn.upstream:
        return False
    try:
        host = urlsplit(conn.upstream).hostname or ""
    except ValueError:
        return False
    return host.endswith(".invalid")


def _entries(conn: Connection) -> list[str]:
    return [e for e in (conn.auth.secret, conn.auth.token_secret) if e]


def _names(names: list[str]) -> str:
    """Names for a detail line: only name-shaped, at most NAME_LIMIT, so a row stays scan-clean."""
    shown = [
        n if SAFE_NAME.fullmatch(n) and not find_secrets(n) else "[odd name]"
        for n in sorted(names)[:NAME_LIMIT]
    ]
    more = len(names) - len(shown)
    return ", ".join(shown) + (f" (+{more} more)" if more > 0 else "")


def _login_action(conn: Connection) -> str:
    return f"Owner: sign in again to {conn.auth.account or conn.name}."


def _unreadable(conn: Connection, entries: list[str]) -> Row:
    return Row(
        conn.name,
        NOT_IN_VAULT,
        "exists, not readable by this identity",
        f"Give the front door's own identity read access to {', '.join(entries)}.",
    )


async def _check(conn: Connection, upstream: Upstream | None, store: SecretStore) -> Row:
    if _is_fixture(conn):
        return Row(conn.name, OK, "fixture, not probed", "None.")
    entries = _entries(conn)
    missing: list[str] = []
    for entry in entries:
        try:
            if not store.exists(entry):
                missing.append(entry)
        except SecretUnavailable:
            return Row(conn.name, NOT_IN_VAULT, "vault not available", "Check the vault connection.")
    if missing:
        return Row(
            conn.name,
            NOT_IN_VAULT,
            f"missing: {', '.join(missing)}",
            f"Add the vault entry {', '.join(missing)}.",
        )
    if upstream is None:
        return Row(conn.name, DEAD, "no upstream was built", "Check the manifest entry.")
    try:
        probe = await asyncio.wait_for(upstream.probe(), timeout=CALL_TIMEOUT_S)
    except SecretUnavailable:
        return _unreadable(conn, entries)
    except UpstreamAuthError:
        return Row(conn.name, NEEDS_LOGIN, "the upstream refused the login", _login_action(conn))
    except Exception:  # noqa: BLE001 - no upstream text is kept
        return Row(conn.name, DEAD, "the probe failed", f"Check the upstream for {conn.name}.")
    if probe.status == NOT_IN_VAULT:
        return _unreadable(conn, entries)
    if probe.status == NEEDS_LOGIN:
        return Row(conn.name, NEEDS_LOGIN, "login needed", _login_action(conn))
    if not probe.ok:
        return Row(conn.name, DEAD, "the probe failed", f"Check the upstream for {conn.name}.")
    try:
        offered = {t.name for t in await asyncio.wait_for(upstream.list_tools(), CALL_TIMEOUT_S)}
    except UpstreamAuthError:
        return Row(conn.name, NEEDS_LOGIN, "the upstream refused the login", _login_action(conn))
    except Exception:  # noqa: BLE001 - no upstream text is kept
        return Row(conn.name, DEAD, "the tool list failed", f"Check the upstream for {conn.name}.")
    listed = {t.name for t in conn.tools}
    absent = sorted(listed - offered)
    extra = sorted(offered - listed)
    if absent:  # dead outranks unlisted
        names = _names(absent)
        return Row(
            conn.name, DEAD, f"missing: {names}",
            f"Remove {names} from the manifest, or check the upstream.",
        )
    if extra:
        return Row(conn.name, UNLISTED, _names(extra), "None. These tools stay hidden from agents.")
    return Row(conn.name, OK, "ok", "None.")


async def run_doctor(
    manifest: Manifest, upstreams: dict[str, Upstream], store: SecretStore
) -> list[Row]:
    """One row per connection, in manifest order. Reads only: `exists`, `probe`, `list_tools`."""
    return [await _check(c, upstreams.get(c.name), store) for c in manifest.connections]


def exit_code(rows: list[Row]) -> int:
    return 0 if all(r.status in HEALTHY for r in rows) else 1


def render_rows(rows: list[Row]) -> str:
    lines = [f"{r.connection}: {r.status}. {r.detail}. {r.action}" for r in rows]
    bad = sum(1 for r in rows if r.status not in HEALTHY)
    lines.append(f"{len(rows)} connections, {bad} need attention")
    return "\n".join(lines) + "\n"
