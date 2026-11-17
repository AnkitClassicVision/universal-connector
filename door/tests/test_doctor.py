from __future__ import annotations

from pathlib import Path

import pytest

from universal_connector.cli import main
from universal_connector.doctor import PRECEDENCE, Row, exit_code, render_rows, run_doctor
from universal_connector.models import Auth, Connection, Manifest, Reach, Scope, Tier, ToolSpec
from universal_connector.scan import find_secrets
from universal_connector.upstreams.base import ProbeResult, ToolInfo, UpstreamAuthError
from universal_connector.vault import MemorySecretStore, SecretUnavailable

VALUE = "fake-doctor-value-0001"  # a stored value; it must never reach a row


class FakeUpstream:
    def __init__(self, tools=("search",), probe=None, probe_error=None, list_error=None) -> None:
        self.tools = list(tools)
        self._probe = probe or ProbeResult(True, "ok", "fine")
        self.probe_error = probe_error
        self.list_error = list_error
        self.calls: list[str] = []

    async def probe(self) -> ProbeResult:
        self.calls.append("probe")
        if self.probe_error:
            raise self.probe_error
        return self._probe

    async def list_tools(self) -> list[ToolInfo]:
        self.calls.append("list_tools")
        if self.list_error:
            raise self.list_error
        return [ToolInfo(t, "d", {"type": "object"}) for t in self.tools]

    async def call_tool(self, name: str, arguments: dict) -> str:  # pragma: no cover
        self.calls.append("call_tool")
        raise AssertionError("the doctor must not call a tool")

    def secret_values(self) -> list[str]:  # pragma: no cover
        self.calls.append("secret_values")
        return []

    def purge(self) -> int:  # pragma: no cover
        self.calls.append("purge")
        return 0


class SpyStore(MemorySecretStore):
    def __init__(self, values: dict[str, str]) -> None:
        super().__init__(values)
        self.calls: list[str] = []

    def exists(self, name: str) -> bool:
        self.calls.append("exists")
        return super().exists(name)

    def get(self, name: str) -> str:  # pragma: no cover
        self.calls.append("get")
        return super().get(name)


def conn(
    name="mail",
    *,
    secret: str | None = "mail/key",
    token_secret: str | None = None,
    tools=("search",),
    upstream="https://up.example.com/mcp",
    auth_type="bearer",
    kind="mcp-remote",
    account: str | None = None,
) -> Connection:
    return Connection(
        name=name,
        kind=kind,
        upstream=upstream,
        auth=Auth(type=auth_type, secret=secret, token_secret=token_secret, account=account),
        scopes={Scope.work},
        reach=Reach.starter,
        tools=[ToolSpec(name=t, tier=Tier.green) for t in tools],
    )


def manifest(*conns: Connection) -> Manifest:
    return Manifest(version=1, connections=list(conns), agents=[])


STORE = {"mail/key": VALUE}


async def one(c: Connection, up: FakeUpstream | None, values: dict | None = None) -> Row:
    store = SpyStore(STORE if values is None else values)
    rows = await run_doctor(manifest(c), {c.name: up} if up else {}, store)
    assert len(rows) == 1
    return rows[0]


async def test_ok():
    row = await one(conn(), FakeUpstream())
    assert row.status == "ok"


async def test_not_in_vault():
    row = await one(conn(), FakeUpstream(), values={})
    assert row.status == "not-in-vault"
    assert row.detail == "missing: mail/key"
    assert row.action == "Add the vault entry mail/key."


async def test_token_secret_is_checked_too():
    c = conn(secret="a/key", token_secret="a/token")
    row = await one(c, FakeUpstream(), values={"a/key": VALUE})
    assert row.status == "not-in-vault"
    assert row.action == "Add the vault entry a/token."


async def test_needs_login_google_action():
    c = conn(
        "gmail_work", secret="g/creds", token_secret="g/token", upstream=None, kind="google",
        auth_type="google-oauth", account="work",
    )
    up = FakeUpstream(probe=ProbeResult(False, "needs-login", "x"))
    row = await one(c, up, values={"g/creds": VALUE, "g/token": VALUE})
    assert row.status == "needs-login"
    assert row.action == "Owner: sign in again to work."


async def test_needs_login_from_auth_error():
    row = await one(conn(), FakeUpstream(probe_error=UpstreamAuthError("MRK-text")))
    assert row.status == "needs-login"
    assert "MRK" not in render_rows([row])


async def test_dead_probe():
    row = await one(conn(), FakeUpstream(probe=ProbeResult(False, "dead", "MRK-detail")))
    assert row.status == "dead"
    assert "MRK" not in render_rows([row])


async def test_dead_when_probe_raises():
    row = await one(conn(), FakeUpstream(probe_error=RuntimeError("MRK-boom")))
    assert row.status == "dead"
    assert "MRK" not in render_rows([row])


async def test_unlisted_tools_exit_0():
    row = await one(conn(), FakeUpstream(tools=("search", "brain_graph")))
    assert row.status == "unlisted-tools"
    assert row.detail == "brain_graph"
    assert exit_code([row]) == 0


async def test_missing_listed_tool_is_dead():
    row = await one(conn(tools=("search", "draft")), FakeUpstream(tools=("search",)))
    assert row.status == "dead"
    assert row.detail == "missing: draft"
    assert row.action == "Remove draft from the manifest, or check the upstream."
    assert exit_code([row]) == 1


async def test_exists_but_unreadable_row():
    up = FakeUpstream(probe_error=SecretUnavailable("MRK-denied"))
    row = await one(conn(), up)
    assert row.status == "not-in-vault"
    assert row.detail == "exists, not readable by this identity"
    assert row.action == "Give the front door's own identity read access to mail/key."
    row2 = await one(conn(), FakeUpstream(probe=ProbeResult(False, "not-in-vault", "x")))
    assert (row2.status, row2.detail) == (row.status, row.detail)


async def test_fixture_not_probed():
    c = conn("fx", secret=None, auth_type="none", upstream="https://up.example.invalid/mcp")
    up = FakeUpstream()
    row = await one(c, up)
    assert (row.status, row.detail) == ("ok", "fixture, not probed")
    assert up.calls == []


async def test_non_fixture_without_login_is_probed():
    c = conn("open", secret=None, auth_type="none", upstream="https://up.example.com/mcp")
    up = FakeUpstream()
    row = await one(c, up)
    assert row.status == "ok" and up.calls == ["probe", "list_tools"]


async def test_precedence():
    assert PRECEDENCE == ["not-in-vault", "needs-login", "dead", "unlisted-tools", "ok"]
    # not-in-vault beats a failing probe: the probe is not even tried
    up = FakeUpstream(probe=ProbeResult(False, "needs-login", "x"))
    row = await one(conn(), up, values={})
    assert row.status == "not-in-vault" and up.calls == []
    # needs-login beats a dead tool list: the list is not read
    up = FakeUpstream(probe=ProbeResult(False, "needs-login", "x"), list_error=RuntimeError("x"))
    row = await one(conn(), up)
    assert row.status == "needs-login" and up.calls == ["probe"]
    # dead (a listed tool missing) beats unlisted-tools when both apply
    row = await one(conn(tools=("search", "draft")), FakeUpstream(tools=("search", "extra")))
    assert row.status == "dead"
    # unlisted-tools beats ok
    row = await one(conn(), FakeUpstream(tools=("search", "extra")))
    assert row.status == "unlisted-tools"


async def test_doctor_makes_no_writes():
    c = conn(secret="a/key", token_secret="a/token")
    up = FakeUpstream()
    store = SpyStore({"a/key": VALUE, "a/token": VALUE})
    await run_doctor(manifest(c), {c.name: up}, store)
    assert up.calls == ["probe", "list_tools"]
    assert store.calls == ["exists", "exists"]  # never `get`: a value is never read here


async def test_no_upstream_built_is_dead():
    row = await one(conn(), None)
    assert row.status == "dead"


def test_exit_code():
    ok = Row("a", "ok", "ok", "None.")
    assert exit_code([ok]) == 0
    assert exit_code([ok, Row("b", "unlisted-tools", "x", "None.")]) == 0
    for bad in ("not-in-vault", "needs-login", "dead"):
        assert exit_code([ok, Row("b", bad, "x", "y")]) == 1
    assert exit_code([]) == 0


async def test_render_is_scan_clean():
    names = tuple(f"tool_{i}" for i in range(30))
    rows = await run_doctor(
        manifest(conn("a", tools=("search",)), conn("b", secret="b/key", tools=("x",))),
        {"a": FakeUpstream(tools=("search", *names)), "b": FakeUpstream(tools=("x",))},
        SpyStore({"mail/key": VALUE}),
    )
    text = render_rows(rows)
    assert find_secrets(text) == []
    assert VALUE not in text
    assert "+20 more" in text  # long tool lists are cut


async def test_odd_tool_names_cannot_smuggle_text():
    row = await one(conn(), FakeUpstream(tools=("search", "sk-" + "A" * 40)))
    assert row.status == "unlisted-tools"
    assert find_secrets(render_rows([row])) == []


LOOPBACK_NAMES = {"127.0.0.1", "localhost", "::1", None}


@pytest.fixture(autouse=True)
def _no_outside_lookup(monkeypatch):
    """Any non-loopback name lookup fails the test at once, instead of making a DNS query."""
    import socket

    real = socket.getaddrinfo

    def guard(host, *args, **kwargs):
        if host not in LOOPBACK_NAMES:
            raise AssertionError("a non-loopback name lookup was attempted")
        return real(host, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", guard)


def test_lookup_guard_trips_on_outside_names():
    import socket

    with pytest.raises(AssertionError, match="lookup"):
        socket.getaddrinfo("up.example.com", 443)


OPEN_CONNECTOR = (
    "version: 1\nconnections:\n"
    "  - name: open\n    kind: mcp-remote\n    upstream: https://up.example.com/mcp\n"
    "    auth: {type: none}\n    scopes: [work]\n    reach: starter\n"
    "    tools:\n      - {name: search, tier: green}\n"
)


def _cli_env(tmp_path: Path, monkeypatch, tools, profiles: list | None = None) -> Path:
    (tmp_path / "connector.yaml").write_text(OPEN_CONNECTOR)
    (tmp_path / "agents.yaml").write_text("version: 1\nagents: []\n")

    def store(machine):
        if profiles is not None:
            profiles.append(machine.get("vault", "keyring"))
        return MemorySecretStore({})

    monkeypatch.setattr("universal_connector.cli.store_for", store)
    monkeypatch.setattr(
        "universal_connector.upstreams.factory.build_upstreams",
        lambda manifest, store, machine=None: {"open": FakeUpstream(tools=tools)},
    )
    (tmp_path / "empty-machine.yaml").write_text("")  # an explicit machine file must exist
    monkeypatch.setenv("UCONNECTOR_MACHINE_FILE", str(tmp_path / "empty-machine.yaml"))
    return tmp_path


@pytest.mark.parametrize(
    ("tools", "code"),
    [(("search",), 0), (("search", "extra"), 0), (("other",), 1), ((), 1)],
)
def test_cli_exit_code_follows_rows(tmp_path, monkeypatch, capsys, tools, code):
    _cli_env(tmp_path, monkeypatch, tools)
    assert main(["doctor", "--manifest", str(tmp_path)]) == code
    out = capsys.readouterr().out
    assert out.splitlines()[-1] == f"1 connections, {code} need attention"


def test_cli_uses_the_machine_file_vault(tmp_path, monkeypatch, capsys):
    vaults: list = []
    _cli_env(tmp_path, monkeypatch, ("search",), vaults)
    assert main(["doctor", "--manifest", str(tmp_path)]) == 0
    machine = tmp_path / "m.yaml"
    machine.write_text("vault: memory\n")
    assert main(["doctor", "--manifest", str(tmp_path), "--machine-file", str(machine)]) == 0
    assert vaults == ["keyring", "memory"]  # no machine file: the keyring default
    capsys.readouterr()


def test_cli_doctor_bad_vault_setting_exits_2(tmp_path, monkeypatch, capsys):
    _cli_env(tmp_path, monkeypatch, ("search",))
    machine = tmp_path / "m.yaml"
    machine.write_text("vault: plaintext\n")
    assert main(["doctor", "--manifest", str(tmp_path), "--machine-file", str(machine)]) == 2
    assert capsys.readouterr().err == "bad vault setting: use keyring, aws or memory\n"


async def test_tool_name_with_newline_cannot_forge_a_row():
    forged = "x\nevil: ok. fine. None."
    row = await one(conn(), FakeUpstream(tools=("search", forged, "tail\n")))
    text = render_rows([row])
    assert row.status == "unlisted-tools"
    assert len(text.splitlines()) == 2  # the one row and the summary line, nothing forged
    assert not any(line.startswith("evil") for line in text.splitlines())


async def test_vault_unavailable_row():
    class Down(SpyStore):
        def exists(self, name: str) -> bool:
            raise SecretUnavailable("MRK-down")

    up = FakeUpstream()
    rows = await run_doctor(manifest(conn()), {"mail": up}, Down({}))
    assert (rows[0].status, rows[0].detail) == ("not-in-vault", "vault not available")
    assert up.calls == []
    assert "MRK" not in render_rows(rows)


def test_cli_doctor_uses_fakes(tmp_path: Path, monkeypatch, capsys):
    (tmp_path / "connector.yaml").write_text(
        "version: 1\nconnections:\n"
        "  - name: fx\n    kind: mcp-remote\n    upstream: https://up.example.invalid/mcp\n"
        "    auth: {type: none}\n    scopes: [work]\n    reach: starter\n"
        "    tools:\n      - {name: search, tier: green}\n"
    )
    (tmp_path / "agents.yaml").write_text("version: 1\nagents: []\n")
    monkeypatch.setattr("universal_connector.cli.store_for", lambda machine: MemorySecretStore({}))
    (tmp_path / "empty-machine.yaml").write_text("")  # an explicit machine file must exist
    monkeypatch.setenv("UCONNECTOR_MACHINE_FILE", str(tmp_path / "empty-machine.yaml"))
    assert main(["doctor", "--manifest", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "fx: ok. fixture, not probed." in out


def test_cli_doctor_bad_manifest_exits_1(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.setattr("universal_connector.cli.store_for", lambda machine: MemorySecretStore({}))
    assert main(["doctor", "--manifest", str(tmp_path)]) == 1
    assert "manifest:" in capsys.readouterr().err


@pytest.mark.parametrize("status", ["needs-login", "dead", "not-in-vault"])
def test_exit_1_for_each_fault(status):
    assert exit_code([Row("a", status, "d", "a")]) == 1
