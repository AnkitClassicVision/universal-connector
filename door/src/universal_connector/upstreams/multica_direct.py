"""Multica, read only. GET requests only. The host comes from `conn.upstream` and nothing else."""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable

import httpx

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

LIST_CAP = 50
_KIND = "multica"
_KEY = re.compile(r"[A-Za-z0-9_-]{1,64}")
_STATUS = re.compile(r"[a-z_]{1,32}")

_TOOLS = [
    ToolInfo(
        "multica_list_issues",
        "List issues. Optional status filter and limit (at most 50).",
        {
            "type": "object",
            "properties": {"status": {"type": "string"}, "limit": {"type": "integer"}},
            "required": [],
        },
    ),
    ToolInfo(
        "multica_get_issue",
        "Get one issue by key.",
        {"type": "object", "properties": {"key": {"type": "string"}}, "required": ["key"]},
    ),
]


class MulticaUpstream:
    def __init__(
        self,
        conn: Connection,
        store: SecretStore,
        transport: httpx.AsyncBaseTransport | None = None,
        clock: Callable[[], float] = time.monotonic,
        ttl_s: int = DEFAULT_TTL_S,
    ) -> None:
        if not conn.upstream:
            raise ValueError(f"connection has no upstream url: {conn.name}")
        self.conn = conn
        self.store = store
        self._transport = transport
        self._base = conn.upstream.rstrip("/")
        self._holds = HoldBook(clock, ttl_s)

    def secret_values(self) -> list[str]:
        self._holds.drop_expired()
        return self._holds.values()

    def purge(self) -> int:
        return self._holds.drop_expired()

    def _credentials(self, used: list[str]) -> tuple[str, str | None]:
        held = self._holds.held("credentials")
        if held is not None:
            credentials, values = held
            used.extend(values)
            return credentials
        if not self.conn.auth.secret:
            raise UpstreamAuthError("needs-login")
        raw = self.store.get(self.conn.auth.secret)  # SecretUnavailable passes up
        used.append(raw)
        token, workspace = raw, None
        try:
            parsed = json.loads(raw)
        except ValueError:
            parsed = None
        if isinstance(parsed, dict):
            token = parsed.get("token") if isinstance(parsed.get("token"), str) else ""
            ws = parsed.get("workspace_id")
            workspace = ws if isinstance(ws, str) and ws else None
        if not token:
            self._holds.put("credentials-failed", None, [raw])
            raise UpstreamAuthError("needs-login")
        used.append(token)
        self._holds.put("credentials", (token, workspace), [raw, token])
        return token, workspace

    async def _get(
        self, path: str, used: list[str], params: dict[str, str | int] | None = None
    ) -> httpx.Response:
        """`used` collects every value this call reads or uses, for the scrub at the end."""
        self._holds.drop_expired()
        token, workspace = self._credentials(used)
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        if workspace:
            headers["X-Workspace-ID"] = workspace
        failure: str | None = None
        response: httpx.Response | None = None
        try:
            async with httpx.AsyncClient(
                transport=self._transport, follow_redirects=False, timeout=30
            ) as http:
                response = await http.get(f"{self._base}{path}", params=params, headers=headers)
        except Exception as exc:  # noqa: BLE001 - no original text is kept
            failure = f"{_KIND}: {type(exc).__name__}"
        if response is None:
            raise UpstreamError(failure or f"{_KIND}: failed")
        code = response.status_code
        if code in (401, 403):
            raise UpstreamAuthError(f"multica refused the login: {self.conn.name}")
        if 300 <= code < 400:
            raise UpstreamError("redirect")
        if code == 404:
            raise UpstreamError("not-found")
        if code >= 400:
            raise UpstreamError(f"multica returned status {code}")
        return response

    async def list_tools(self) -> list[ToolInfo]:
        self._holds.drop_expired()
        return list(_TOOLS)

    async def call_tool(self, name: str, arguments: dict) -> str:
        self._holds.drop_expired()
        used: list[str] = []
        error: Exception | None = None
        text = ""
        try:
            if name == "multica_list_issues":
                text = await self._list_issues(used, **_only(arguments, {"status", "limit"}))
            elif name == "multica_get_issue":
                text = await self._get_issue(used, _only(arguments, {"key"}).get("key", ""))
            else:
                raise UpstreamError(f"unknown tool: {name}")
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
        return scrub(text, used + self._holds.values())

    async def _list_issues(self, used: list[str], status: str | None = None, limit: int = 20) -> str:
        if status is not None and not (isinstance(status, str) and _STATUS.fullmatch(status)):
            raise UpstreamError("bad-status")
        try:
            count = max(1, min(int(limit), LIST_CAP))
        except (TypeError, ValueError):
            count = -1
        if count < 0:
            raise UpstreamError("bad-limit")
        params: dict[str, str | int] = {"limit": count}
        if status:
            params["status"] = status
        return (await self._get("/api/issues", used, params)).text

    async def _get_issue(self, used: list[str], key: str) -> str:
        if not (isinstance(key, str) and _KEY.fullmatch(key)):
            raise UpstreamError("bad-key")
        return (await self._get(f"/api/issues/{key}", used)).text

    async def probe(self) -> ProbeResult:
        used: list[str] = []
        status: str | None = None
        detail = ""
        try:
            await self._get("/api/me", used)
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
        return ProbeResult(True, "ok", "signed in")


def _only(arguments: dict, allowed: set[str]) -> dict:
    if set(arguments) - allowed:
        raise UpstreamError("bad arguments")
    return dict(arguments)
