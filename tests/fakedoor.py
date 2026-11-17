"""An in-memory stand-in for a door, used as the smoke tests' transport. No sockets.

It behaves the way a good door must: a key per harness, 401 without a valid key,
refusal of any Origin header and of a Host it does not list, revocation, and
read-only annotations on read tools. Each behaviour can be switched off to prove
the smoke tests catch a bad door.
"""

from __future__ import annotations

import json
import time
from urllib.parse import urlsplit

READ_TOOLS = [
    {"name": "tracker__list_projects", "annotations": {"readOnlyHint": True}},
    {"name": "guide", "annotations": {"readOnlyHint": True}},
    {"name": "whoami", "annotations": {"readOnlyHint": True}},
    {"name": "tracker__create_issue", "annotations": {"readOnlyHint": False, "destructiveHint": False}},
]


class FakeDoor:
    def __init__(self, keys=("Qz9FAKEdrv01x",), hosts=("127.0.0.1:8765", "door.tailnet-name.ts.net"), tools=None,
                 page_size=None, delay=0.0, results=None, sse=False, refuse_origin=True, refuse_host=True,
                 require_key=True, revoked=(), redirect=False, get_mode="405"):
        self.redirect, self.get_mode = redirect, get_mode
        self.keys, self.hosts = set(keys), set(hosts)
        self.tools = list(tools if tools is not None else READ_TOOLS)
        self.page_size, self.delay, self.sse = page_size, delay, sse
        self.results = dict(results or {})
        self.refuse_origin, self.refuse_host, self.require_key = refuse_origin, refuse_host, require_key
        self.revoked = set(revoked)
        self.calls: list[str] = []
        self.called: list[str] = []

    def __call__(self, url, headers, body, timeout, method="POST"):
        h = {k.lower(): v for k, v in headers.items()}
        if self.redirect:
            return 308, {"location": url + "/"}, b""
        if self.refuse_origin and "origin" in h:
            return 403, {}, b""
        host = h.get("host") or urlsplit(url).netloc
        if self.refuse_host and host not in self.hosts:
            return 421, {}, b""
        auth = h.get("authorization", "")
        key = auth[7:] if auth.startswith("Bearer ") else None
        if self.require_key and (key not in self.keys or key in self.revoked):
            return 401, {}, b""
        if method == "GET":
            if self.get_mode == "stream":
                return 200, {"content-type": "text/event-stream"}, b""
            if self.get_mode == "json":
                return 200, {"content-type": "application/json"}, b"{}"
            return 405, {}, b""
        msg = json.loads(body)
        if "id" not in msg:
            return 202, {}, b""
        self.calls.append(msg["method"])
        if msg["method"] == "tools/call":
            self.called.append((msg.get("params") or {}).get("name"))
        result = self._result(msg)
        if isinstance(result, tuple):
            payload = {"jsonrpc": "2.0", "id": msg["id"], "error": {"code": result[0], "message": "no"}}
        else:
            payload = {"jsonrpc": "2.0", "id": msg["id"], "result": result}
        data = json.dumps(payload)
        if self.sse:
            return 200, {"content-type": "text/event-stream", "mcp-session-id": "s1"}, f"event: message\ndata: {data}\n\n".encode()
        return 200, {"content-type": "application/json", "mcp-session-id": "s1"}, data.encode()

    def _result(self, msg):
        method, params = msg["method"], msg.get("params") or {}
        if method == "initialize":
            return {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}}, "serverInfo": {"name": "fake-door"}}
        if method == "tools/list":
            if not self.page_size:
                return {"tools": self.tools}
            start = int(params.get("cursor") or 0)
            page = self.tools[start:start + self.page_size]
            nxt = start + self.page_size
            return {"tools": page, **({"nextCursor": str(nxt)} if nxt < len(self.tools) else {})}
        if method == "tools/call":
            name = params.get("name")
            if name not in {t["name"] for t in self.tools}:
                return (-32602,)
            if self.delay:
                time.sleep(self.delay)
            return self.results.get(name, {"content": [{"type": "text", "text": "ok: 3 projects"}]})
        return (-32601,)
