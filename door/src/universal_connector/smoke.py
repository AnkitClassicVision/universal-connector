"""`uconnector smoke oddboro`: talk to a running door the way Oddboro's MCP client does.

It posts MCP over streamable HTTP with protocol version 2025-11-25, no `Origin` header, and
`Accept: application/json, text/event-stream`, and never follows a redirect. Checks:

1. initialize: 200, no redirect, an answer within 5 seconds.
2. no key: 401.
3. GET: 405, or an event stream.
4. tools/list: one page with no `nextCursor`, within 5 seconds. Every tool has a snake_case
   name within 64 characters as `mcp__<service id>__<tool>` (a warning past 57), no
   `outputSchema`, and every tool marked read-only passes Oddboro's read-only rule.
5. tools/call once per read tool: a `content` array within 40 seconds.

Each check prints pass or fail with a short code or count. The key is never printed, and no
tool result text is shown.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import httpx

from universal_connector import adapters
from universal_connector.router import oddboro_reads_only

PROTOCOL = "2025-11-25"
FAST_S = 5.0
CALL_BUDGET_S = float(adapters.ODDBORO_CALL_TIMEOUT_S)
ACCEPT = "application/json, text/event-stream"
KEY_LENGTH = 46
_KEY_CHARS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-")
BAD_KEY_FILE = "the key file must hold one key (pc_ and 43 characters) and nothing else"
# Arguments for the fixed read tools; any other read tool gets `{}`. A refusal still has content.
_ARGUMENTS = {"find_read_tools": {"query": ""}}


@dataclass
class Check:
    name: str
    passed: bool
    detail: str


def read_key_file(path: Path) -> str:
    """The key, read inside this process. One line: the key, with at most one trailing newline."""
    try:
        text = Path(path).read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        raise ValueError(BAD_KEY_FILE) from None
    key = text.removesuffix("\n")
    if len(key) != KEY_LENGTH or not key.startswith("pc_") or not set(key) <= _KEY_CHARS:
        raise ValueError(BAD_KEY_FILE)
    return key


def _message(response: httpx.Response, wanted_id: int) -> dict | None:
    """The JSON-RPC answer with `wanted_id`, from a JSON body or an event stream."""
    kind = response.headers.get("content-type", "")
    bodies: list[str] = []
    if kind.startswith("text/event-stream"):
        for line in response.text.splitlines():
            if line.startswith("data:"):
                bodies.append(line[5:].strip())
    else:
        bodies.append(response.text)
    for body in bodies:
        try:
            parsed = json.loads(body)
        except ValueError:
            continue
        for item in parsed if isinstance(parsed, list) else [parsed]:
            if isinstance(item, dict) and item.get("id") == wanted_id:
                return item
    return None


class _Client:
    def __init__(self, http: httpx.AsyncClient, url: str, key: str) -> None:
        self.http = http
        self.url = url
        self._key = key
        self.extra: dict[str, str] = {}
        self._next_id = 0

    def headers(self, with_key: bool = True) -> dict[str, str]:
        out = {"Accept": ACCEPT, "Content-Type": "application/json", **self.extra}
        if with_key:
            out["Authorization"] = f"Bearer {self._key}"
        return out

    async def post(self, body: dict, with_key: bool = True) -> httpx.Response:
        return await self.http.post(self.url, json=body, headers=self.headers(with_key))

    async def request(self, method: str, params: dict) -> tuple[httpx.Response, dict | None]:
        self._next_id += 1
        body = {"jsonrpc": "2.0", "id": self._next_id, "method": method, "params": params}
        response = await self.post(body)
        return response, _message(response, self._next_id)


def _init_params() -> dict:
    return {
        "protocolVersion": PROTOCOL,
        "capabilities": {},
        "clientInfo": {"name": "uconnector-smoke", "version": "1"},
    }


async def _initialize(client: _Client, clock: Callable[[], float]) -> Check:
    start = clock()
    response, answer = await client.request("initialize", _init_params())
    took = clock() - start
    result = (answer or {}).get("result")
    if response.is_redirect or response.status_code != 200:
        return Check("initialize", False, f"status {response.status_code}")
    if not isinstance(result, dict) or not isinstance(result.get("protocolVersion"), str):
        return Check("initialize", False, "no initialize result")
    if took >= FAST_S:
        return Check("initialize", False, f"took {took:.1f} s")
    client.extra["mcp-protocol-version"] = result["protocolVersion"]
    session = response.headers.get("mcp-session-id")
    if session:
        client.extra["mcp-session-id"] = session
    note = await client.post({"jsonrpc": "2.0", "method": "notifications/initialized"})
    if note.status_code not in (200, 202):
        return Check("initialize", False, f"initialized notice status {note.status_code}")
    return Check("initialize", True, f"protocol {result['protocolVersion']}, {took:.1f} s")


async def _no_key(client: _Client) -> Check:
    body = {"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": _init_params()}
    response = await client.post(body, with_key=False)
    return Check("no key gives 401", response.status_code == 401, f"status {response.status_code}")


async def _get(client: _Client) -> Check:
    headers = {**client.headers(), "Accept": "text/event-stream"}
    async with client.http.stream("GET", client.url, headers=headers) as response:
        kind = response.headers.get("content-type", "")
        status = response.status_code
    ok = status == 405 or (status == 200 and kind.startswith("text/event-stream"))
    return Check("GET gives 405 or a stream", ok, f"status {status}")


def _tool_problems(service_id: str, tool: dict) -> tuple[list[str], int]:
    name = tool.get("name")
    if not isinstance(name, str):
        return ["a tool has no name"], 0
    problems: list[str] = []
    full = f"mcp__{service_id}__{name}"
    if not adapters.SNAKE_CASE.fullmatch(name):
        problems.append("a name is not snake_case")
    if len(full) > adapters.ODDBORO_NAME_LIMIT:
        problems.append("a name is over 64 characters")
    if "outputSchema" in tool:
        problems.append("a tool has an outputSchema")
    marks = tool.get("annotations") or {}
    read_marked = marks.get("readOnlyHint") is True
    if read_marked and (marks.get("destructiveHint") is not False or not oddboro_reads_only(name, marks)):
        problems.append("a read-only tool fails the read-only rule")
    return problems, len(full)


async def _list(client: _Client, service_id: str, clock) -> tuple[Check, Check, list[str]]:
    start = clock()
    response, answer = await client.request("tools/list", {})
    took = clock() - start
    result = (answer or {}).get("result")
    if response.status_code != 200 or not isinstance(result, dict):
        failed = Check("tools/list", False, f"status {response.status_code}")
        return failed, Check("tool shape", False, "no tool list"), []
    tools = result.get("tools")
    one_page = "nextCursor" not in result and isinstance(tools, list)
    listing = Check(
        "tools/list one page",
        one_page and took < FAST_S,
        f"{len(tools) if isinstance(tools, list) else 0} tools, {took:.1f} s"
        + ("" if one_page else ", has nextCursor or no list"),
    )
    problems: list[str] = []
    longest = 0
    reads: list[str] = []
    for tool in tools if isinstance(tools, list) else []:
        found, length = _tool_problems(service_id, tool if isinstance(tool, dict) else {})
        problems.extend(found)
        longest = max(longest, length)
        if not found and oddboro_reads_only(tool["name"], tool.get("annotations")):
            reads.append(tool["name"])
    detail = f"longest name {longest} of {adapters.ODDBORO_NAME_LIMIT}"
    if longest > adapters.ODDBORO_NAME_WARN:
        detail += f" (warning: past {adapters.ODDBORO_NAME_WARN})"
    if problems:
        detail += "; " + "; ".join(sorted(set(problems)))
    return listing, Check("tool shape", not problems and bool(tools), detail), reads


async def _calls(client: _Client, reads: list[str], clock) -> Check:
    if not reads:
        return Check("tools/call per read tool", False, "no read tools")
    bad = 0
    slowest = 0.0
    for name in reads:
        start = clock()
        failed = False
        try:
            response, answer = await client.request(
                "tools/call", {"name": name, "arguments": _ARGUMENTS.get(name, {})}
            )
        except httpx.HTTPError:  # a timeout or a dropped connection; no text is kept
            failed = True
        took = clock() - start
        slowest = max(slowest, took)
        if failed:
            bad += 1
            continue
        result = (answer or {}).get("result")
        content = result.get("content") if isinstance(result, dict) else None
        if response.status_code != 200 or not isinstance(content, list) or took > CALL_BUDGET_S:
            bad += 1
    return Check(
        "tools/call per read tool",
        bad == 0,
        f"{len(reads) - bad} of {len(reads)} answered with content, slowest {slowest:.1f} s",
    )


async def run_smoke(
    url: str,
    key: str,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> list[Check]:
    """Every check, in order. A failed initialize stops the rest after the no-key check."""
    service_id = adapters.oddboro_service_id(url)
    timeout = httpx.Timeout(CALL_BUDGET_S + 5.0)
    async with httpx.AsyncClient(
        transport=transport, follow_redirects=False, timeout=timeout
    ) as http:
        client = _Client(http, url, key)
        checks: list[Check] = []
        try:
            checks.append(await _initialize(client, clock))
            checks.append(await _no_key(client))
            if not checks[0].passed:
                return checks
            checks.append(await _get(client))
            listing, shape, reads = await _list(client, service_id, clock)
            checks.extend([listing, shape])
            checks.append(await _calls(client, reads, clock))
        except httpx.HTTPError as exc:  # the type name only: the text can quote the request
            checks.append(Check("connection", False, type(exc).__name__))
        return checks


def render(checks: list[Check]) -> str:
    lines = [f"{'pass' if c.passed else 'FAIL'} {c.name}: {c.detail}" for c in checks]
    failed = sum(1 for c in checks if not c.passed)
    lines.append(f"{len(checks)} checks, {failed} failed")
    return "\n".join(lines) + "\n"


def address_problem(url: str) -> str | None:
    return adapters.address_problem(url, "oddboro")


def exit_code(checks: list[Check]) -> int:
    return 0 if checks and all(c.passed for c in checks) else 1


