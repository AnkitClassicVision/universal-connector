"""Four MCP SDK 1.26.0 facts the front door depends on, proven against a real server."""

from __future__ import annotations

import anyio
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from helpers.mcp_stub import make_stub_app, run_app

TOKENS = {"a-token": "a", "b-token": "b"}


def echo(text: str = "", caller: str | None = None) -> str:
    return f"caller={caller} text={text}"


def caller_app():
    return make_stub_app({"a_echo": echo, "b_echo": echo}, identify=TOKENS.get)


async def open_session_and(url: str, headers: dict[str, str], action):
    with anyio.fail_after(15):
        async with (
            httpx.AsyncClient(headers=headers, follow_redirects=True) as http,
            streamable_http_client(url, http_client=http) as (read, write, _),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            return await action(session)


async def tool_names(session: ClientSession) -> list[str]:
    result = await session.list_tools()
    return sorted(t.name for t in result.tools)


def find_status_error(exc: BaseException) -> httpx.HTTPStatusError | None:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc
    for inner in getattr(exc, "exceptions", ()):
        found = find_status_error(inner)
        if found is not None:
            return found
    return None


async def test_tool_list_differs_by_caller():
    with run_app(caller_app()) as base:
        a = await open_session_and(f"{base}/mcp", {"Authorization": "Bearer a-token"}, tool_names)
        b = await open_session_and(f"{base}/mcp", {"Authorization": "Bearer b-token"}, tool_names)
    assert a == ["a_echo"]
    assert b == ["b_echo"]


async def test_handler_knows_caller():
    async def call_a_echo(session: ClientSession):
        return await session.call_tool("a_echo", {"text": "hi"})

    with run_app(caller_app()) as base:
        own = await open_session_and(f"{base}/mcp", {"Authorization": "Bearer a-token"}, call_a_echo)
        other = await open_session_and(
            f"{base}/mcp", {"Authorization": "Bearer b-token"}, call_a_echo
        )
    assert own.isError is False
    assert "caller=a" in own.content[0].text
    assert other.isError is True


async def test_unknown_token_is_401():
    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "t", "version": "0"},
        },
    }
    headers = {
        "Authorization": "Bearer nope",
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    with run_app(caller_app()) as base:
        async with httpx.AsyncClient() as http:
            response = await http.post(f"{base}/mcp", json=body, headers=headers)
    assert response.status_code == 401
    assert "jsonrpc" not in response.text


async def test_client_sends_custom_header():
    app = make_stub_app({"echo": echo}, required_header=("x-test-key", "v1"))
    with run_app(app) as base:
        names = await open_session_and(f"{base}/mcp", {"x-test-key": "v1"}, tool_names)
        try:
            await open_session_and(f"{base}/mcp", {}, tool_names)
        except BaseException as exc:  # noqa: BLE001 - the SDK wraps errors in exception groups
            refused = find_status_error(exc)
        else:
            refused = None
    assert names == ["echo"]
    assert refused is not None and refused.response.status_code == 401
