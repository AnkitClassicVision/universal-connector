"""A small MCP client over streamable HTTP, standard library only.

It never logs headers, keys or result bodies. Errors carry an HTTP status or a
fixed reason, never response text. The transport is swappable so tests run with
no network at all.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

PROTOCOL = "2025-06-18"
Transport = Callable[..., tuple[int, dict[str, str], bytes]]  # (url, headers, body, timeout, method="POST")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect is reported as its own status, never followed: some harnesses refuse redirects."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401
        return None


def make_opener() -> urllib.request.OpenerDirector:
    """No proxy, ever (HTTP_PROXY and friends are ignored, so a key never goes to a proxy), and no redirects."""
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect)


_OPENER = make_opener()


def urllib_transport(url: str, headers: dict[str, str], body: bytes | None, timeout: float,
                     method: str = "POST") -> tuple[int, dict[str, str], bytes]:
    req = urllib.request.Request(url, data=body if method == "POST" else None, headers=headers, method=method)
    try:
        with _OPENER.open(req, timeout=timeout) as resp:  # the URL is the person's own door
            rh = {k.lower(): v for k, v in resp.headers.items()}
            if method != "POST":  # a GET may open an endless event stream: headers only
                return resp.status, rh, b""
            return resp.status, rh, resp.read(10_000_000)
    except urllib.error.HTTPError as exc:
        return exc.code, {k.lower(): v for k, v in (exc.headers or {}).items()}, b""
    except (urllib.error.URLError, TimeoutError, OSError):
        return 0, {}, b""


@dataclass
class Reply:
    status: int
    result: Any = None
    error: str | None = None
    elapsed: float = 0.0


def _parse_body(raw: bytes, content_type: str, want_id: int) -> tuple[Any, str | None]:
    text = raw.decode("utf-8", "replace")
    messages: list[Any] = []
    if "text/event-stream" in content_type:
        data: list[str] = []
        for line in text.splitlines() + [""]:
            if line.startswith("data:"):
                data.append(line[5:].lstrip())
            elif not line.strip() and data:
                try:
                    messages.append(json.loads("\n".join(data)))
                except ValueError:
                    pass
                data = []
    else:
        try:
            parsed = json.loads(text) if text.strip() else None
        except ValueError:
            return None, "the reply was not JSON"
        messages = parsed if isinstance(parsed, list) else [parsed]
    for m in messages:
        if isinstance(m, dict) and m.get("id") == want_id:
            if "error" in m:
                code = m["error"].get("code") if isinstance(m["error"], dict) else None
                return None, f"JSON-RPC error {code}"
            return m.get("result"), None
    return None, "no reply with the request id"


class McpClient:
    def __init__(self, url: str, key: str | None = None, transport: Transport | None = None,
                 timeout: float = 60.0, extra_headers: dict[str, str] | None = None) -> None:
        self.url = url
        self._key = key
        self.transport = transport or urllib_transport
        self.timeout = timeout
        self.extra = dict(extra_headers or {})
        self.session: str | None = None
        self._id = 0
        self.first_list_elapsed = 0.0

    def _headers(self, with_key: bool = True) -> dict[str, str]:
        h = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
             "MCP-Protocol-Version": PROTOCOL}
        if self.session:
            h["Mcp-Session-Id"] = self.session
        if with_key and self._key:
            h["Authorization"] = f"Bearer {self._key}"
        h.update(self.extra)
        return h

    def get_probe(self) -> tuple[int, str, float]:
        """A GET on the MCP address: streamable HTTP answers 405 or opens an event stream. (status, type, secs)."""
        h = {k: v for k, v in self._headers().items() if k != "Content-Type"}
        h["Accept"] = "text/event-stream"
        start = time.monotonic()
        status, rh, _ = self.transport(self.url, h, None, min(self.timeout, 10.0), method="GET")
        return status, rh.get("content-type", ""), time.monotonic() - start

    def rpc(self, method: str, params: dict | None = None, with_key: bool = True,
            headers: dict[str, str] | None = None, notify: bool = False) -> Reply:
        self._id += 1
        msg: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if not notify:
            msg["id"] = self._id
        if params is not None:
            msg["params"] = params
        h = self._headers(with_key)
        if headers:
            h.update(headers)
        start = time.monotonic()
        status, rh, raw = self.transport(self.url, h, json.dumps(msg).encode(), self.timeout)
        elapsed = time.monotonic() - start
        if rh.get("mcp-session-id"):
            self.session = rh["mcp-session-id"]
        if notify or status >= 300 or status == 0:
            return Reply(status, None, None if status and status < 300 else f"HTTP {status or 'no answer'}", elapsed)
        result, err = _parse_body(raw, rh.get("content-type", ""), self._id)
        return Reply(status, result, err, elapsed)

    def initialize(self) -> Reply:
        r = self.rpc("initialize", {"protocolVersion": PROTOCOL, "capabilities": {},
                                    "clientInfo": {"name": "universal-connector-smoke", "version": "0.1.0"}})
        if r.status == 200 and r.error is None:
            self.rpc("notifications/initialized", notify=True)
        return r

    def list_tools(self, max_pages: int = 20) -> tuple[list[dict], int, bool, Reply]:
        """(tools, pages read, first page had a next cursor, last reply)."""
        tools: list[dict] = []
        cursor = None
        first_has_next = False
        pages = 0
        last = Reply(0)
        while pages < max_pages:
            last = self.rpc("tools/list", {"cursor": cursor} if cursor else {})
            if last.status != 200 or last.error or not isinstance(last.result, dict):
                break
            pages += 1
            tools += [t for t in last.result.get("tools", []) if isinstance(t, dict)]
            cursor = last.result.get("nextCursor")
            if pages == 1:
                first_has_next = bool(cursor)
                self.first_list_elapsed = last.elapsed
            if not cursor:
                break
        return tools, pages, first_has_next, last

    def call_tool(self, name: str, arguments: dict) -> Reply:
        return self.rpc("tools/call", {"name": name, "arguments": arguments})
