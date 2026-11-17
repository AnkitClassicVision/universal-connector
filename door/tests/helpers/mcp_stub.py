"""A small MCP server over streamable HTTP for tests.

Built on the MCP SDK 1.26.0 low-level server. `tests/sdk/test_sdk_facts.py` pins its behaviour.
The MCP endpoint is `<base>/mcp`.
"""

from __future__ import annotations

import contextlib
import inspect
import socket
import threading
import time
from collections.abc import AsyncIterator, Callable, Iterator
from typing import Any

import uvicorn
from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.types import ASGIApp, Receive, Scope, Send

_JSON_TYPES = {str: "string", int: "integer", float: "number", bool: "boolean", dict: "object"}


def _input_schema(fn: Callable[..., Any]) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    required: list[str] = []
    for name, param in inspect.signature(fn).parameters.items():
        if name == "caller":
            continue
        json_type = _JSON_TYPES.get(param.annotation) if isinstance(param.annotation, type) else None
        properties[name] = {"type": json_type} if json_type else {}
        if param.default is inspect.Parameter.empty:
            required.append(name)
    schema: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema


def _bearer(scope: Scope) -> str | None:
    for key, value in scope.get("headers", []):
        if key == b"authorization":
            scheme, _, token = value.decode("latin-1").strip().partition(" ")
            if scheme.lower() == "bearer" and token.strip():
                return token.strip()
            return None
    return None


def _header(scope: Scope, name: str) -> str | None:
    wanted = name.lower().encode("latin-1")
    for key, value in scope.get("headers", []):
        if key == wanted:
            return value.decode("latin-1")
    return None


class _Gate:
    """Checks the caller before any MCP handling, then hands the request to the SDK."""

    def __init__(
        self,
        manager: StreamableHTTPSessionManager,
        required_header: tuple[str, str] | None,
        identify: Callable[[str | None], str | None] | None,
    ) -> None:
        self.manager = manager
        self.required_header = required_header
        self.identify = identify

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        caller: str | None = None
        allowed = True
        if self.required_header is not None:
            name, value = self.required_header
            allowed = _header(scope, name) == value
        if allowed and self.identify is not None:
            caller = self.identify(_bearer(scope))
            allowed = caller is not None
        if not allowed:
            await JSONResponse({"error": "unauthorized"}, status_code=401)(scope, receive, send)
            return
        # Per-request state. The SDK passes this request into the handler's context.
        scope = {**scope, "state": {**scope.get("state", {}), "caller": caller}}
        await self.manager.handle_request(scope, receive, send)


def make_stub_app(
    tools: dict[str, Callable[..., Any]],
    required_header: tuple[str, str] | None = None,
    identify: Callable[[str | None], str | None] | None = None,
) -> ASGIApp:
    """Build an ASGI app serving `tools` over MCP streamable HTTP at `/mcp`.

    A tool callable that takes a `caller` parameter receives the caller name.
    When `identify` is given, a caller sees and calls only tools whose name starts
    with its caller name, and an unknown token gets HTTP 401.
    """
    server: Server = Server("mcp-stub")

    def current_caller() -> str | None:
        request = server.request_context.request
        return None if request is None else request.state.caller

    def visible(caller: str | None) -> list[str]:
        if identify is None:
            return list(tools)
        return [name for name in tools if caller is not None and name.startswith(caller)]

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name=name,
                description=inspect.getdoc(tools[name]) or "",
                inputSchema=_input_schema(tools[name]),
            )
            for name in visible(current_caller())
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
        caller = current_caller()
        if name not in visible(caller):
            raise ValueError(f"unknown tool: {name}")
        fn = tools[name]
        kwargs = dict(arguments)
        if "caller" in inspect.signature(fn).parameters:
            kwargs["caller"] = caller
        result = fn(**kwargs)
        if inspect.isawaitable(result):
            result = await result
        return [types.TextContent(type="text", text=str(result))]

    manager = StreamableHTTPSessionManager(app=server, json_response=True, stateless=True)

    @contextlib.asynccontextmanager
    async def lifespan(_: Starlette) -> AsyncIterator[None]:
        async with manager.run():
            yield

    gate = _Gate(manager, required_header, identify)
    return Starlette(routes=[Route("/mcp", endpoint=gate, methods=["GET", "POST", "DELETE"])],
                     lifespan=lifespan)


@contextlib.contextmanager
def run_app(app: ASGIApp) -> Iterator[str]:
    """Serve `app` on 127.0.0.1 with an OS-chosen port in a background thread."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    config = uvicorn.Config(app, log_level="warning", lifespan="on")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if not thread.is_alive() or time.monotonic() > deadline:
            raise RuntimeError("stub server did not start")
        time.sleep(0.01)
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        sock.close()
