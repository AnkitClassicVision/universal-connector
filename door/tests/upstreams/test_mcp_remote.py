from __future__ import annotations

import asyncio

import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse, PlainTextResponse, RedirectResponse
from starlette.routing import Route

from helpers.mcp_stub import make_stub_app, run_app
from helpers.reach import reaches_text
from universal_connector.models import Auth, Connection, Reach, Scope, Tier, ToolSpec
from universal_connector.upstreams.base import UpstreamAuthError, UpstreamError
from universal_connector.upstreams.mcp_remote import McpRemoteUpstream
from universal_connector.vault import MemorySecretStore, SecretUnavailable

GOOD = "fake-stub-key-0001"
BAD = "fake-stub-key-9999"


def echo(text: str) -> str:
    """Echo the text."""
    return f"echo:{text}"


def leak(text: str) -> str:
    """Return the key by mistake."""
    return GOOD


def boom(text: str) -> str:
    """Fail with a message that holds the key."""
    raise ValueError(f"bad call with {GOOD}")


def conn(url: str, secret: str = "stub/key") -> Connection:
    return Connection(
        name="stub",
        kind="mcp-remote",
        upstream=f"{url}/mcp",
        auth=Auth(type="header", header="x-test-key", secret=secret),
        scopes={Scope.work},
        reach=Reach.starter,
        tools=[ToolSpec(name="echo", tier=Tier.green)],
    )


def app():
    return make_stub_app(
        {"echo": echo, "leak": leak, "boom": boom}, required_header=("x-test-key", GOOD)
    )


async def test_lists_tools():
    with run_app(app()) as base:
        up = McpRemoteUpstream(conn(base), MemorySecretStore({"stub/key": GOOD}))
        tools = await up.list_tools()
    assert {t.name for t in tools} == {"echo", "leak", "boom"}


async def test_calls_tool():
    with run_app(app()) as base:
        up = McpRemoteUpstream(conn(base), MemorySecretStore({"stub/key": GOOD}))
        assert await up.call_tool("echo", {"text": "hi"}) == "echo:hi"
        assert GOOD in up.secret_values()


async def test_wrong_key_is_auth_error():
    with run_app(app()) as base:
        up = McpRemoteUpstream(conn(base), MemorySecretStore({"stub/key": BAD}))
        with pytest.raises(UpstreamAuthError):
            await up.call_tool("echo", {"text": "hi"})


async def test_error_text_has_no_secret():
    with run_app(app()) as base:
        up = McpRemoteUpstream(conn(base), MemorySecretStore({"stub/key": GOOD}))
        with pytest.raises(UpstreamError) as err:
            await up.call_tool("boom", {"text": "x"})
        assert GOOD not in str(err.value)
        assert await up.call_tool("leak", {"text": "x"}) == "[redacted]"
    with run_app(app()) as base:
        up = McpRemoteUpstream(conn(base), MemorySecretStore({"stub/key": BAD}))
        with pytest.raises(UpstreamAuthError) as err:
            await up.list_tools()
        assert BAD not in str(err.value)


async def test_probe_ok_and_dead():
    with run_app(app()) as base:
        good = McpRemoteUpstream(conn(base), MemorySecretStore({"stub/key": GOOD}))
        assert (await good.probe()).status == "ok"
        wrong = McpRemoteUpstream(conn(base), MemorySecretStore({"stub/key": BAD}))
        assert (await wrong.probe()).status == "needs-login"
        missing = McpRemoteUpstream(conn(base), MemorySecretStore({}))
        assert (await missing.probe()).status == "not-in-vault"
    dead = McpRemoteUpstream(conn("http://127.0.0.1:9"), MemorySecretStore({"stub/key": GOOD}))
    result = await dead.probe()
    assert result.ok is False and result.status == "dead"


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


async def test_redirect_is_not_followed():
    seen: list[str] = []

    async def landing(request):
        seen.append(request.headers.get("x-test-key", ""))
        return JSONResponse({"error": "should not be reached"})

    second = Starlette(routes=[Route("/mcp", landing, methods=["GET", "POST", "DELETE"])])
    with run_app(second) as other:

        async def hop(request):
            return RedirectResponse(f"{other}/mcp", status_code=307)

        first = Starlette(routes=[Route("/mcp", hop, methods=["GET", "POST", "DELETE"])])
        with run_app(first) as base:
            up = McpRemoteUpstream(conn(base), MemorySecretStore({"stub/key": GOOD}), timeout_s=5)
            with pytest.raises(UpstreamError) as err:
                await up.list_tools()
    assert seen == []
    assert str(err.value) == "redirect"
    assert GOOD not in str(err.value)


async def test_values_dropped_after_ttl():
    clock, store = Clock(), CountingStore({"stub/key": GOOD})
    with run_app(app()) as base:
        up = McpRemoteUpstream(conn(base), store, clock=clock)
        await up.call_tool("echo", {"text": "a"})
        assert up.secret_values() == [GOOD]
        clock.now += 899
        assert up.secret_values() == [GOOD]
        clock.now += 1
        assert up.secret_values() == []
        await up.call_tool("echo", {"text": "b"})
        assert store.reads == 2


async def test_purge_counts_drops():
    clock = Clock()
    with run_app(app()) as base:
        up = McpRemoteUpstream(conn(base), MemorySecretStore({"stub/key": GOOD}), clock=clock)
        await up.call_tool("echo", {"text": "a"})
        assert up.purge() == 0
        clock.now += 900
        assert up.purge() == 1
        assert up.purge() == 0


async def test_unexpected_error_holds_no_secret():
    key = "fake-key-é-0003"
    up = McpRemoteUpstream(conn("http://127.0.0.1:9"), MemorySecretStore({"stub/key": key}))
    with pytest.raises(UpstreamError) as err:
        await up.call_tool("echo", {"text": "a"})
    exc = err.value
    for text in (str(exc), repr(exc), repr(exc.args)):
        assert key not in text
    assert exc.__context__ is None and exc.__cause__ is None
    result = await up.probe()
    assert key not in result.detail


async def test_missing_entry_probe_is_not_in_vault():
    up = McpRemoteUpstream(conn("http://127.0.0.1:9"), MemorySecretStore({}))
    assert (await up.probe()).status == "not-in-vault"


async def test_missing_entry_call_raises_secret_unavailable():
    up = McpRemoteUpstream(conn("http://127.0.0.1:9"), MemorySecretStore({}))
    with pytest.raises(SecretUnavailable):
        await up.call_tool("echo", {"text": "a"})


async def test_result_is_scrubbed():
    with run_app(app()) as base:
        up = McpRemoteUpstream(conn(base), MemorySecretStore({"stub/key": GOOD}))
        out = await up.call_tool("leak", {"text": "x"})
    assert GOOD not in out and "[redacted]" in out


async def test_key_scrubbed_when_hold_drops_mid_call():
    """The Task 11 purge loop drops the hold while the call runs. The key must not come back."""
    clock, late, holder = Clock(), {"on": False}, {}

    def drop_now() -> None:
        if late["on"]:
            clock.now += 900
            holder["up"].purge()

    def late_leak(text: str) -> str:
        """Drop the hold, then return the key."""
        drop_now()
        return f"key {GOOD}"

    def late_boom(text: str) -> str:
        """Drop the hold, then fail with the key."""
        drop_now()
        raise ValueError(f"bad call with {GOOD}")

    stub = make_stub_app(
        {"late_leak": late_leak, "late_boom": late_boom}, required_header=("x-test-key", GOOD)
    )
    with run_app(stub) as base:
        up = McpRemoteUpstream(
            conn(base), MemorySecretStore({"stub/key": GOOD}), clock=clock, timeout_s=10
        )
        holder["up"] = up
        await up.call_tool("late_leak", {"text": "warm"})  # hold exists when the next call starts
        late["on"] = True
        for _ in range(2):  # first from the hold, then from a fresh store read
            out = await up.call_tool("late_leak", {"text": "x"})
            assert GOOD not in out and "[redacted]" in out
            assert up.secret_values() == []
            with pytest.raises(UpstreamError) as err:
                await up.call_tool("late_boom", {"text": "x"})
            assert GOOD not in str(err.value) and GOOD not in repr(err.value.args)


async def test_nothing_reachable_after_expiry():
    clock, store = Clock(), MemorySecretStore({"stub/key": GOOD})
    with run_app(app()) as base:
        up = McpRemoteUpstream(conn(base), store, clock=clock)
        await up.call_tool("echo", {"text": "a"})
        assert reaches_text(up, GOOD, skip=[store])  # the walk can see a live hold
        clock.now += 900
        assert up.purge() >= 1
        assert not reaches_text(up, GOOD, skip=[store])


def describe_key() -> str:
    return "x"


describe_key.__doc__ = f"This description holds the key {GOOD} by mistake."


async def test_list_tools_scrubbed_when_hold_drops_mid_call():
    """The purge loop drops the hold while list_tools runs. The key must not come back."""
    clock, late, holder = Clock(), {"on": False}, {}
    inner = make_stub_app(
        {"echo": echo, "describe_key": describe_key}, required_header=("x-test-key", GOOD)
    )

    async def wrapped(scope, receive, send):
        if scope["type"] == "http" and late["on"]:
            clock.now += 900
            holder["up"].purge()
        await inner(scope, receive, send)

    with run_app(wrapped) as base:
        up = McpRemoteUpstream(
            conn(base), MemorySecretStore({"stub/key": GOOD}), clock=clock, timeout_s=10
        )
        holder["up"] = up
        await up.call_tool("echo", {"text": "warm"})  # a hold exists when list_tools starts
        late["on"] = True
        tools = await up.list_tools()
    assert up.secret_values() == []
    described = next(t for t in tools if t.name == "describe_key")
    assert GOOD not in described.description and "[redacted]" in described.description
    assert GOOD not in repr(tools)


async def test_cancel_passes_through():
    """A cancel from outside (the router's timeout) must not become an UpstreamError."""
    started: list[int] = []

    async def slow() -> str:
        started.append(1)
        await asyncio.sleep(0.6)
        return "late"

    stub = make_stub_app({"slow": slow}, required_header=("x-test-key", GOOD))
    with run_app(stub) as base:
        up = McpRemoteUpstream(conn(base), MemorySecretStore({"stub/key": GOOD}), timeout_s=30)
        task = asyncio.ensure_future(up.call_tool("slow", {}))
        for _ in range(250):
            if started:
                break
            await asyncio.sleep(0.02)
        assert started
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


async def test_list_tools_schema_scrubbed_in_adapter():
    """The adapter scrubs schema strings itself, with no router in front of it."""
    key = "fakeStubKey0001"  # a legal parameter name, so it lands in the schema

    def lookup(fakeStubKey0001: str) -> str:
        """Look something up."""
        return "x"

    stub = make_stub_app({"lookup": lookup}, required_header=("x-test-key", key))
    with run_app(stub) as base:
        up = McpRemoteUpstream(conn(base), MemorySecretStore({"stub/key": key}))
        tools = await up.list_tools()
    (tool,) = tools
    assert key not in repr(tools)
    assert "[redacted]" in repr(tool.input_schema)


MARKER = "MARKER-not-a-key"


async def test_status_error_keeps_no_upstream_text():
    async def failing(request):
        return PlainTextResponse(f"{MARKER} ghost@example.invalid", status_code=500)

    app = Starlette(routes=[Route("/mcp/{rest:path}", failing, methods=["GET", "POST", "DELETE"])])
    with run_app(app) as base:
        # The marker is also in the URL, so an error text that keeps the exception shows it.
        up = McpRemoteUpstream(
            conn(f"{base}/mcp/{MARKER}"), MemorySecretStore({"stub/key": GOOD}), timeout_s=5
        )
        errors = []
        for action in (up.call_tool("echo", {"text": "a"}), up.list_tools()):
            with pytest.raises(UpstreamError) as err:
                await action
            errors.append(err.value)
        detail = (await up.probe()).detail
    assert str(errors[0]) == "upstream returned status 500"
    for exc in errors:
        for text in (str(exc), repr(exc), repr(exc.args)):
            assert MARKER not in text and "ghost@example.invalid" not in text
    assert MARKER not in detail and "ghost@example.invalid" not in detail


UPSTREAM_TEXT = "MARKER-not-a-key from ghost@example.invalid"


async def test_error_text_keeps_no_upstream_text(monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError(UPSTREAM_TEXT)

    monkeypatch.setattr("universal_connector.upstreams.mcp_remote.streamable_http_client", broken)
    up = McpRemoteUpstream(conn("http://127.0.0.1:9"), MemorySecretStore({"stub/key": GOOD}))
    for action in (up.call_tool("echo", {"text": "a"}), up.list_tools()):
        with pytest.raises(UpstreamError) as err:
            await action
        for text in (str(err.value), repr(err.value), repr(err.value.args)):
            assert "MARKER-not-a-key" not in text and "ghost@example.invalid" not in text
    result = await up.probe()
    assert result.status == "dead"
    assert "MARKER-not-a-key" not in result.detail and "ghost@example.invalid" not in result.detail
