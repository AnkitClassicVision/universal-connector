from __future__ import annotations

import asyncio

import httpx
import pytest

from helpers.reach import reaches_text
from universal_connector.models import Auth, Connection, Reach, Scope, Tier, ToolSpec
from universal_connector.upstreams.base import UpstreamAuthError, UpstreamError
from universal_connector.upstreams.multica_direct import MulticaUpstream
from universal_connector.vault import MemorySecretStore, SecretUnavailable

TOKEN = "fake-multica-token-0001"
BASE = "https://multica.example.invalid"


def conn() -> Connection:
    return Connection(
        name="multica",
        kind="multica",
        upstream=BASE,
        auth=Auth(type="bearer", secret="m/token"),
        scopes={Scope.work},
        reach=Reach.starter,
        tools=[ToolSpec(name="multica_list_issues", tier=Tier.green)],
    )


class Recorder:
    def __init__(self, handler=None) -> None:
        self.requests: list[httpx.Request] = []
        self.handler = handler or (lambda r: httpx.Response(200, json={"ok": True}))

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.handler(request)


def make(rec: Recorder, entry: str = TOKEN) -> MulticaUpstream:
    return MulticaUpstream(
        conn(), MemorySecretStore({"m/token": entry}), transport=httpx.MockTransport(rec)
    )


async def test_list_issues_sends_get_with_token():
    rec = Recorder()
    await make(rec).call_tool("multica_list_issues", {"status": "todo", "limit": 5})
    (req,) = rec.requests
    assert req.method == "GET"
    assert str(req.url).startswith(f"{BASE}/api/issues?")
    assert req.url.params["limit"] == "5" and req.url.params["status"] == "todo"
    assert req.headers["authorization"] == f"Bearer {TOKEN}"
    assert req.headers["accept"] == "application/json"
    assert "x-workspace-id" not in req.headers


async def test_limit_caps_at_50():
    rec = Recorder()
    await make(rec).call_tool("multica_list_issues", {"limit": 500})
    assert rec.requests[0].url.params["limit"] == "50"


async def test_401_is_auth_error():
    rec = Recorder(lambda r: httpx.Response(401))
    with pytest.raises(UpstreamAuthError) as err:
        await make(rec).call_tool("multica_list_issues", {})
    assert TOKEN not in str(err.value)


async def test_only_get_requests_made():
    rec = Recorder()
    up = make(rec)
    await up.call_tool("multica_list_issues", {})
    await up.call_tool("multica_get_issue", {"key": "ABC-1"})
    await up.probe()
    assert len(rec.requests) == 3
    assert {r.method for r in rec.requests} == {"GET"}


@pytest.mark.parametrize("key", ["", "a/b", "a b", "x" * 65, "../x", "a?b=1", "a\n"])
async def test_bad_key_sends_no_request(key):
    rec = Recorder()
    with pytest.raises(UpstreamError, match="bad-key"):
        await make(rec).call_tool("multica_get_issue", {"key": key})
    assert rec.requests == []


@pytest.mark.parametrize("status", ["", "TODO", "a b", "x" * 33, "todo&x=1", "a\n"])
async def test_bad_status_sends_no_request(status):
    rec = Recorder()
    with pytest.raises(UpstreamError, match="bad-status"):
        await make(rec).call_tool("multica_list_issues", {"status": status})
    assert rec.requests == []


async def test_get_404_is_not_found():
    rec = Recorder(lambda r: httpx.Response(404))
    with pytest.raises(UpstreamError, match="not-found"):
        await make(rec).call_tool("multica_get_issue", {"key": "ABC-1"})
    assert rec.requests[0].url.path == "/api/issues/ABC-1"


async def test_json_entry_sends_workspace_header():
    rec = Recorder()
    entry = '{"token": "' + TOKEN + '", "workspace_id": "ws-fake-1"}'
    up = make(rec, entry)
    await up.call_tool("multica_list_issues", {})
    req = rec.requests[0]
    assert req.headers["authorization"] == f"Bearer {TOKEN}"
    assert req.headers["x-workspace-id"] == "ws-fake-1"
    assert TOKEN in up.secret_values()


async def test_base_url_in_entry_is_ignored():
    rec = Recorder()
    entry = '{"token": "' + TOKEN + '", "base_url": "https://evil.example.invalid"}'
    await make(rec, entry).call_tool("multica_list_issues", {})
    assert rec.requests[0].url.host == "multica.example.invalid"


async def test_redirect_is_not_followed():
    rec = Recorder(
        lambda r: httpx.Response(302, headers={"location": "https://evil.example.invalid/x"})
    )
    with pytest.raises(UpstreamError):
        await make(rec).call_tool("multica_list_issues", {})
    assert len(rec.requests) == 1


async def test_error_text_has_no_secret():
    rec = Recorder(lambda r: httpx.Response(500, text=f"boom {TOKEN}"))
    with pytest.raises(UpstreamError) as err:
        await make(rec).call_tool("multica_list_issues", {})
    assert TOKEN not in str(err.value)
    echo = Recorder(lambda r: httpx.Response(200, text=f"you sent {TOKEN}"))
    out = await make(echo).call_tool("multica_list_issues", {})
    assert TOKEN not in out and "[redacted]" in out

    def fail(request):
        raise httpx.ConnectError(f"cannot reach with {TOKEN}")

    with pytest.raises(UpstreamError) as err2:
        await make(Recorder(fail)).call_tool("multica_list_issues", {})
    assert TOKEN not in str(err2.value)


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class CountingStore(MemorySecretStore):
    def __init__(self, values):
        super().__init__(values)
        self.reads = 0

    def get(self, name):
        self.reads += 1
        return super().get(name)


async def test_values_dropped_after_ttl():
    clock, store = Clock(), CountingStore({"m/token": TOKEN})
    up = MulticaUpstream(conn(), store, transport=httpx.MockTransport(Recorder()), clock=clock)
    await up.call_tool("multica_list_issues", {})
    assert up.secret_values() == [TOKEN]
    clock.now += 899
    assert up.secret_values() == [TOKEN]
    clock.now += 1
    assert up.secret_values() == []
    await up.call_tool("multica_list_issues", {})
    assert store.reads == 2


async def test_purge_counts_drops():
    clock = Clock()
    up = MulticaUpstream(
        conn(),
        MemorySecretStore({"m/token": TOKEN}),
        transport=httpx.MockTransport(Recorder()),
        clock=clock,
    )
    await up.call_tool("multica_list_issues", {})
    assert up.purge() == 0
    clock.now += 900
    assert up.purge() == 1
    assert up.purge() == 0


async def test_unexpected_error_holds_no_secret():
    key = "fake-key-é-0004"

    def fail(request):
        raise UnicodeEncodeError("ascii", f"Bearer {key}", 0, 1, "boom")

    up = MulticaUpstream(
        conn(), MemorySecretStore({"m/token": key}), transport=httpx.MockTransport(Recorder(fail))
    )
    with pytest.raises(UpstreamError) as err:
        await up.call_tool("multica_list_issues", {})
    exc = err.value
    for text in (str(exc), repr(exc), repr(exc.args)):
        assert key not in text
    assert exc.__context__ is None and exc.__cause__ is None
    result = await up.probe()
    assert result.ok is False and key not in result.detail


async def test_missing_entry_probe_is_not_in_vault():
    up = MulticaUpstream(
        conn(), MemorySecretStore({}), transport=httpx.MockTransport(Recorder())
    )
    assert (await up.probe()).status == "not-in-vault"


async def test_missing_entry_call_raises_secret_unavailable():
    rec = Recorder()
    up = MulticaUpstream(conn(), MemorySecretStore({}), transport=httpx.MockTransport(rec))
    with pytest.raises(SecretUnavailable):
        await up.call_tool("multica_list_issues", {})
    assert rec.requests == []


async def test_result_is_scrubbed():
    rec = Recorder(lambda r: httpx.Response(200, text=f"issue says {TOKEN}"))
    up = make(rec)
    for name, args in (
        ("multica_list_issues", {}),
        ("multica_get_issue", {"key": "ABC-1"}),
    ):
        out = await up.call_tool(name, args)
        assert TOKEN not in out and "[redacted]" in out


async def test_key_scrubbed_when_hold_drops_mid_call():
    """The Task 11 purge loop drops the hold while the call runs. The key must not come back."""
    clock, late, holder = Clock(), {"on": False}, {}
    entry = '{"token": "' + TOKEN + '"}'

    def handler(request):
        if late["on"]:
            clock.now += 900
            holder["up"].purge()
        return httpx.Response(200, text=f"echo {TOKEN} {entry}")

    up = MulticaUpstream(
        conn(), MemorySecretStore({"m/token": entry}), transport=httpx.MockTransport(handler),
        clock=clock,
    )
    holder["up"] = up
    await up.call_tool("multica_list_issues", {})  # hold exists when the next call starts
    late["on"] = True
    for _ in range(2):  # first from the hold, then from a fresh store read
        for name, args in (("multica_list_issues", {}), ("multica_get_issue", {"key": "ABC-1"})):
            out = await up.call_tool(name, args)
            assert TOKEN not in out and "[redacted]" in out
            assert up.secret_values() == []


async def test_probe_ok_needs_login_dead():
    assert (await make(Recorder()).probe()).status == "ok"
    rec = Recorder()
    await make(rec).probe()
    assert rec.requests[0].url.path == "/api/me"
    assert (await make(Recorder(lambda r: httpx.Response(401))).probe()).status == "needs-login"
    assert (await make(Recorder(lambda r: httpx.Response(500))).probe()).status == "dead"
    empty = MulticaUpstream(
        conn(), MemorySecretStore({}), transport=httpx.MockTransport(Recorder())
    )
    assert (await empty.probe()).status == "not-in-vault"


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


async def test_nothing_reachable_after_expiry():
    clock, store = _Clock(), MemorySecretStore({"m/token": TOKEN})
    # Not a Recorder: it keeps every request, and a request carries the key in its headers.
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"ok": True}))
    up = MulticaUpstream(conn(), store, transport=transport, clock=clock)
    await up.call_tool("multica_list_issues", {})
    assert reaches_text(up, TOKEN, skip=[store])  # the walk can see a live hold
    clock.now += 900
    assert up.purge() >= 1
    assert not reaches_text(up, TOKEN, skip=[store])


async def test_cancel_passes_through():
    started: list[int] = []

    async def slow(request):
        started.append(1)
        await asyncio.sleep(5)
        return httpx.Response(200, json={})

    up = MulticaUpstream(
        conn(), MemorySecretStore({"m/token": TOKEN}), transport=httpx.MockTransport(slow)
    )
    task = asyncio.ensure_future(up.call_tool("multica_list_issues", {}))
    await asyncio.sleep(0.2)
    assert started
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_status_error_keeps_no_upstream_text():
    body = "MARKER-not-a-key ghost@example.invalid"
    up = make(Recorder(lambda r: httpx.Response(500, text=body)))
    errors = []
    for action in (
        up.call_tool("multica_list_issues", {}),
        up.call_tool("multica_get_issue", {"key": "ABC-1"}),
    ):
        with pytest.raises(UpstreamError) as err:
            await action
        errors.append(err.value)
    detail = (await up.probe()).detail
    assert str(errors[0]) == "multica returned status 500"
    for exc in errors:
        for text in (str(exc), repr(exc), repr(exc.args)):
            assert "MARKER-not-a-key" not in text and "ghost@example.invalid" not in text
    assert "MARKER-not-a-key" not in detail and "ghost@example.invalid" not in detail


UPSTREAM_TEXT = "MARKER-not-a-key from ghost@example.invalid"


async def test_error_text_keeps_no_upstream_text():
    def broken(request):
        raise RuntimeError(UPSTREAM_TEXT)

    up = make(Recorder(broken))
    for action in (
        up.call_tool("multica_list_issues", {}),
        up.call_tool("multica_get_issue", {"key": "ABC-1"}),
    ):
        with pytest.raises(UpstreamError) as err:
            await action
        for text in (str(err.value), repr(err.value), repr(err.value.args)):
            assert "MARKER-not-a-key" not in text and "ghost@example.invalid" not in text
    result = await up.probe()
    assert result.status == "dead"
    assert "MARKER-not-a-key" not in result.detail and "ghost@example.invalid" not in result.detail
