"""Upstream over MCP streamable HTTP. Client calls are the MCP SDK 1.26.0 ones `tests/sdk` pins."""

from __future__ import annotations

import time
from collections.abc import Callable

import anyio
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from universal_connector.models import Connection
from universal_connector.upstreams.base import (
    DEFAULT_TTL_S,
    HoldBook,
    ProbeResult,
    ToolInfo,
    UpstreamAuthError,
    UpstreamError,
    clean_error,
    scrub,
)
from universal_connector.vault import SecretStore, SecretUnavailable

_DEFAULT_TIMEOUT_S = 60
_KIND = "mcp-remote"


def _leaves(exc: BaseException) -> list[BaseException]:
    if isinstance(exc, BaseExceptionGroup):
        found: list[BaseException] = []
        for inner in exc.exceptions:
            found.extend(_leaves(inner))
        return found
    return [exc]


def _scrub_deep(value, values: list[str]):  # type: ignore[no-untyped-def]
    """A copy of a JSON-like value with every secret value in any string or key replaced."""
    if isinstance(value, str):
        return scrub(value, values)
    if isinstance(value, dict):
        return {_scrub_deep(k, values): _scrub_deep(v, values) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_scrub_deep(v, values) for v in value]
    return value


def _status_of(exc: BaseException) -> int | None:
    for leaf in _leaves(exc):
        if isinstance(leaf, httpx.HTTPStatusError):
            return leaf.response.status_code
    return None


class McpRemoteUpstream:
    def __init__(
        self,
        conn: Connection,
        store: SecretStore,
        timeout_s: float = _DEFAULT_TIMEOUT_S,
        clock: Callable[[], float] = time.monotonic,
        ttl_s: int = DEFAULT_TTL_S,
    ) -> None:
        if not conn.upstream:
            raise ValueError(f"connection has no upstream url: {conn.name}")
        self.conn = conn
        self.store = store
        self.timeout_s = timeout_s
        self._holds = HoldBook(clock, ttl_s)

    def secret_values(self) -> list[str]:
        self._holds.drop_expired()
        return self._holds.values()

    def purge(self) -> int:
        return self._holds.drop_expired()

    def _headers(self, used: list[str]) -> dict[str, str]:
        held = self._holds.held("headers")
        if held is not None:
            headers, values = held
            used.extend(values)
            return headers
        auth = self.conn.auth
        if auth.type == "none":
            return {}
        if not auth.secret:
            raise UpstreamAuthError("needs-login")
        value = self.store.get(auth.secret)  # SecretUnavailable passes up
        used.append(value)
        if auth.type == "header":
            if not auth.header:
                raise UpstreamError("connection has no header name")
            headers = {auth.header: value}
        elif auth.type == "bearer":
            headers = {"Authorization": f"Bearer {value}"}
        else:
            raise UpstreamError(f"unsupported auth type: {auth.type}")
        self._holds.put("headers", headers, [value])
        return headers

    async def _run(self, action, used: list[str]):  # type: ignore[no-untyped-def]
        """`used` collects every value this call reads or uses, for the scrub at the end."""
        self._holds.drop_expired()
        headers = self._headers(used)
        failure: str | None = None
        auth_failed = False
        try:
            with anyio.fail_after(self.timeout_s):
                async with (
                    httpx.AsyncClient(headers=headers, follow_redirects=False) as http,
                    streamable_http_client(self.conn.upstream, http_client=http) as (
                        read,
                        write,
                        _,
                    ),
                    ClientSession(read, write) as session,
                ):
                    await session.initialize()
                    return await action(session)
        except TimeoutError:
            failure = "upstream timed out"
        except (UpstreamError, UpstreamAuthError, SecretUnavailable):
            raise
        except Exception as exc:  # noqa: BLE001 - mapped below, no original text kept
            # Not BaseException: a cancel (or a group holding one) must pass up unchanged.
            status = _status_of(exc)
            if status in (401, 403):
                auth_failed = True
            elif status is not None and 300 <= status < 400:
                failure = "redirect"
            elif status is not None:
                failure = f"upstream returned status {status}"
            else:
                leaf = _leaves(exc)[0]
                failure = f"{_KIND}: {type(leaf).__name__}"
        if auth_failed:
            raise UpstreamAuthError(f"upstream refused the login: {self.conn.name}")
        raise UpstreamError(failure or f"{_KIND}: failed")

    async def list_tools(self) -> list[ToolInfo]:
        used: list[str] = []
        tools = await self._list_tools(used)
        # Scrub with the values this call used, not only the holds left now: a hold can drop
        # (purge, ttl) while the call is in flight, and its value must still be scrubbed.
        values = used + self._holds.values()
        return [
            ToolInfo(
                scrub(t.name, values), scrub(t.description, values), _scrub_deep(t.input_schema, values)
            )
            for t in tools
        ]

    async def _list_tools(self, used: list[str]) -> list[ToolInfo]:
        async def action(session: ClientSession) -> list[ToolInfo]:
            result = await session.list_tools()
            return [
                ToolInfo(t.name, t.description or "", dict(t.inputSchema or {}))
                for t in result.tools
            ]

        return await self._run(action, used)

    async def call_tool(self, name: str, arguments: dict) -> str:
        async def action(session: ClientSession) -> tuple[bool, str]:
            result = await session.call_tool(name, arguments)
            text = "\n".join(c.text for c in result.content if getattr(c, "type", None) == "text")
            return bool(result.isError), text

        used: list[str] = []
        error: Exception | None = None
        is_error, text = False, ""
        try:
            is_error, text = await self._run(action, used)
        except SecretUnavailable:
            raise
        except (UpstreamAuthError, UpstreamError) as exc:
            error = clean_error(exc, used + self._holds.values())
        except Exception as exc:  # noqa: BLE001 - mapped, no original text kept
            error = UpstreamError(f"{_KIND}: {type(exc).__name__}")
        if error is not None:
            raise error
        # Scrub with the values this call used, not only the holds left now: a hold can drop
        # (purge, ttl) while the call is in flight, and its value must still be scrubbed.
        text = scrub(text, used + self._holds.values())
        if is_error:
            raise UpstreamError(text or "upstream tool error")
        return text

    async def probe(self) -> ProbeResult:
        used: list[str] = []
        status: str | None = None
        detail = ""
        try:
            await self._list_tools(used)
        except SecretUnavailable:
            status, detail = "not-in-vault", "vault entry not available"
        except UpstreamAuthError:
            status, detail = "needs-login", "login refused"
        except UpstreamError as exc:
            status, detail = "dead", str(exc)
        except Exception as exc:  # noqa: BLE001
            status, detail = "dead", f"{_KIND}: {type(exc).__name__}"
        if status is not None:
            return ProbeResult(False, status, scrub(detail, used + self._holds.values()))
        return ProbeResult(True, "ok", "tools listed")
