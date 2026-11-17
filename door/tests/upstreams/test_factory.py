from __future__ import annotations

import pytest

from universal_connector.models import Auth, Connection, Manifest, Reach, Scope, Tier, ToolSpec
from universal_connector.upstreams.factory import build_upstreams
from universal_connector.upstreams.google_direct import GoogleUpstream
from universal_connector.upstreams.mcp_remote import McpRemoteUpstream
from universal_connector.upstreams.multica_direct import MulticaUpstream
from universal_connector.vault import MemorySecretStore


def conn(name: str, kind: str, auth: Auth) -> Connection:
    return Connection(
        name=name,
        kind=kind,
        upstream="http://127.0.0.1:1/mcp" if kind == "mcp-remote" else None,
        auth=auth,
        scopes={Scope.work},
        reach=Reach.starter,
        tools=[ToolSpec(name="t", tier=Tier.green)],
    )


def manifest(*conns: Connection) -> Manifest:
    return Manifest(version=1, connections=list(conns), agents=[])


def test_builds_by_kind():
    m = manifest(
        conn("a", "mcp-remote", Auth(type="none")),
        conn("b", "google", Auth(type="google-oauth", account="x", secret="s")),
        conn("c", "multica", Auth(type="bearer", secret="t")).model_copy(
            update={"upstream": "https://multica.example.invalid"}
        ),
    )
    built = build_upstreams(m, MemorySecretStore({}))
    assert isinstance(built["a"], McpRemoteUpstream)
    assert isinstance(built["b"], GoogleUpstream)
    assert isinstance(built["c"], MulticaUpstream)


def test_machine_address_reaches_google_upstream():
    m = manifest(conn("b", "google", Auth(type="google-oauth", account="x", secret="s")))
    machine = {"google_accounts": {"x": "box@example.invalid"}}
    built = build_upstreams(m, MemorySecretStore({}), machine)
    assert built["b"]._expected_address == "box@example.invalid"
    assert build_upstreams(m, MemorySecretStore({}))["b"]._expected_address is None


@pytest.mark.parametrize("kind", ["browser", "computer", "mcp-stdio"])
def test_plan_d_kinds_not_implemented(kind):
    m = manifest(conn("c", kind, Auth(type="none")))
    with pytest.raises(NotImplementedError, match="Plan D"):
        build_upstreams(m, MemorySecretStore({}))


def test_browser_kind_not_implemented():
    m = manifest(conn("c", "browser", Auth(type="none")))
    with pytest.raises(NotImplementedError, match="Plan D"):
        build_upstreams(m, MemorySecretStore({}))
