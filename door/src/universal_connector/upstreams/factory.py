"""Build one upstream per manifest connection."""

from __future__ import annotations

from universal_connector.models import Manifest
from universal_connector.upstreams.base import Upstream
from universal_connector.upstreams.google_direct import GoogleUpstream
from universal_connector.upstreams.mcp_remote import McpRemoteUpstream
from universal_connector.upstreams.multica_direct import MulticaUpstream
from universal_connector.vault import SecretStore


def build_upstreams(
    manifest: Manifest, store: SecretStore, machine: dict | None = None
) -> dict[str, Upstream]:
    accounts = (machine or {}).get("google_accounts") or {}
    built: dict[str, Upstream] = {}
    for conn in manifest.connections:
        if conn.kind == "mcp-remote":
            built[conn.name] = McpRemoteUpstream(conn, store)
        elif conn.kind == "google":
            address = accounts.get(conn.auth.account) if conn.auth.account else None
            built[conn.name] = GoogleUpstream(
                conn, store, expected_address=address if isinstance(address, str) else None
            )
        elif conn.kind == "multica":
            built[conn.name] = MulticaUpstream(conn, store)
        else:
            raise NotImplementedError(f"kind {conn.kind} arrives in Plan D: {conn.name}")
    return built
