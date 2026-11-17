"""The router: which tools an agent sees, and the policy, retry and redaction around every call.

Order inside `call`: pause, then rate limit, then policy. Every call writes one audit line.
"""

from __future__ import annotations

import asyncio
import copy
import json
import re
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from universal_connector.audit import is_paused, record
from universal_connector.guide import render_guide
from universal_connector.models import AgentGrant, Connection, Manifest, Tier
from universal_connector.policy import Decision, decide
from universal_connector.state import open_state
from universal_connector.upstreams.base import Upstream, UpstreamAuthError, UpstreamError, scrub
from universal_connector.vault import SecretUnavailable

# The 42 words that, anywhere in a tool's name, tell Oddboro the tool changes something. A tool
# whose name holds one loses Oddboro's Read only grant, so the router never marks it read-only.
ODDBORO_CHANGE_WORDS = frozenset(
    {
        "add", "append", "approve", "archive", "assign", "cancel", "capture", "clear", "close",
        "comment", "create", "delete", "destroy", "drop", "edit", "exec", "execute", "forward",
        "insert", "invite", "merge", "modify", "move", "patch", "post", "publish", "put", "remove",
        "rename", "reply", "reset", "run", "save", "send", "set", "share", "store", "submit",
        "update", "upload", "upsert", "write",
    }
)  # fmt: skip

MAX_PINNED_TOOLS = 20
FIND_LIMIT = 10
RATE_WINDOW_S = 60
REFRESH_TIMEOUT_S = 60

RED_TEXT = "This action is not available to agents. Prepare a draft for the owner instead."
LOGIN_TEXT = "This connection needs a re-login by the owner."
NOT_AVAILABLE_TEXT = "This connection is not available."
UPSTREAM_ERROR_TEXT = "The upstream call failed."
TIMEOUT_TEXT = "The upstream call timed out."
PAUSED_TEXT = "The connector is paused by the owner."
RATE_TEXT = "Too many calls. Wait a minute and try again."
UNKNOWN_TEXT = "No such tool."


def name_words(name: str) -> list[str]:
    """Split a tool name into words the way Oddboro does.

    Mark camel-case boundaries, lowercase, split on anything outside `a-z0-9`, drop empty parts.
    So `messages.send`, `files/upload` and `sendé` all yield their change word.
    """
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", name)
    return [part for part in re.split(r"[^a-z0-9]+", spaced.lower()) if part]


def change_words_in(name: str) -> set[str]:
    return set(name_words(name)) & ODDBORO_CHANGE_WORDS


def oddboro_reads_only(name: str, annotations: dict | None) -> bool:
    """Oddboro's read-only rule: whether its Read only grant reaches this tool.

    `readOnlyHint` must be exactly true, `destructiveHint` must not be true, and no word of the
    name may be a change word.
    """
    marks = annotations or {}
    return (
        marks.get("readOnlyHint") is True
        and marks.get("destructiveHint") is not True
        and not change_words_in(name)
    )


@dataclass
class VisibleTool:
    name: str
    description: str
    input_schema: dict
    read_only: bool


@dataclass
class CallResult:
    ok: bool
    text: str
    code: str


def _object(properties: dict[str, dict], required: list[str]) -> dict:
    return {"type": "object", "properties": properties, "required": required}


_QUERY = _object({"query": {"type": "string"}}, ["query"])
_DOOR = _object(
    {"connection": {"type": "string"}, "tool": {"type": "string"}, "arguments": {"type": "object"}},
    ["connection", "tool"],
)

# name, description, input schema, read-only. Always present, always in this order.
_FIXED: list[tuple[str, str, dict, bool]] = [
    ("connector_guide", "How this connector works and what you can reach.", _object({}, []), True),
    (
        "find_read_tools",
        "Find read-only tools by words in their name or description. Up to 10.",
        _QUERY,
        True,
    ),
    ("call_read_tool", "Run a read-only tool you found with find_read_tools.", _DOOR, True),
    (
        "find_write_tools",
        "Find tools that prepare drafts, by words in their name or description. Up to 10.",
        _QUERY,
        False,
    ),
    ("call_write_tool", "Run a draft tool you found with find_write_tools.", _DOOR, False),
]


FIXED_NAMES = tuple(name for name, _, _, _ in _FIXED)


def allowed_pinned(manifest: Manifest, agent: AgentGrant) -> list[tuple[Connection, str, Decision]]:
    """The pinned tools this agent sees: policy allows them, 20 at most. None when fixed-only."""
    found: list[tuple[Connection, str, Decision]] = []
    if not agent.pinned_tools:  # a fixed-tools-only agent sees none; `_pinned` then refuses them
        return found
    for conn in manifest.connections:
        for spec in conn.tools:
            if not spec.pinned:
                continue
            decision = decide(agent, conn, spec.name)
            if decision.allowed:
                found.append((conn, spec.name, decision))
    return found[:MAX_PINNED_TOOLS]


def visible_names(manifest: Manifest, agent: AgentGrant) -> list[str]:
    """Every tool name `Router.visible` would list for this agent, without any upstream."""
    return [*FIXED_NAMES, *(f"{c.name}__{t}" for c, t, _ in allowed_pinned(manifest, agent))]


def _scrub_deep(value: Any, values: list[str]) -> Any:
    """A copy of a JSON-like value with every secret value in any string or key replaced."""
    if isinstance(value, str):
        return scrub(value, values)
    if isinstance(value, dict):
        return {_scrub_deep(k, values): _scrub_deep(v, values) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_scrub_deep(v, values) for v in value]
    return value


class Router:
    def __init__(
        self,
        manifest: Manifest,
        upstreams: dict[str, Upstream],
        state_dir: Path,
        clock: Callable[[], float] = time.monotonic,
        rate_per_minute: int = 120,
        result_limit: int = 60000,
    ) -> None:
        self._manifest = manifest
        self._upstreams = upstreams
        self._state_dir = Path(state_dir)
        # Create the state folder now, so the first calls do not race to create it.
        open_state(self._state_dir).close()
        self._clock = clock
        self._rate = rate_per_minute
        self._limit = result_limit
        self._calls: dict[str, deque[float]] = {}
        # connection -> tool name -> (description, input schema), already redacted
        self._catalog: dict[str, dict[str, tuple[str, dict]]] = {}

    # -- catalog -------------------------------------------------------------------------------

    async def refresh(self, connections: list[str] | None = None) -> dict[str, str]:
        """Load tool descriptions from the upstreams. Returns a status per connection. Never raises."""
        names = (
            list(connections)
            if connections is not None
            else [c.name for c in self._manifest.connections]
        )
        statuses = await asyncio.gather(*(self._refresh_one(name) for name in names))
        return dict(zip(names, statuses, strict=True))

    async def _refresh_one(self, name: str) -> str:
        conn = self._manifest.connection(name)
        upstream = self._upstreams.get(name)
        if conn is None or upstream is None:
            return "not-available"
        try:
            tools = await asyncio.wait_for(upstream.list_tools(), timeout=REFRESH_TIMEOUT_S)
            values = upstream.secret_values()
            listed = {spec.name for spec in conn.tools}
            entries: dict[str, tuple[str, dict]] = {}
            for tool in tools:
                if tool.name in listed:
                    entries[tool.name] = (
                        scrub(str(tool.description or ""), values),
                        _scrub_deep(dict(tool.input_schema or {}), values),
                    )
        except SecretUnavailable:
            return "not-available"
        except UpstreamAuthError:
            return "needs-login"
        except TimeoutError:
            return "timeout"
        except Exception:  # noqa: BLE001 - the last good entries stay; no text is kept
            return "upstream-error"
        self._catalog[name] = entries
        return "ok"

    def _describe(self, connection: str, tool: str) -> tuple[str, dict]:
        entry = self._catalog.get(connection, {}).get(tool)
        if entry is None:
            return f"{connection} tool {tool}. Details are not loaded yet.", {"type": "object"}
        return entry[0], copy.deepcopy(entry[1])

    # -- what an agent sees --------------------------------------------------------------------

    def visible(self, agent: AgentGrant) -> list[VisibleTool]:
        tools = [VisibleTool(n, d, copy.deepcopy(s), ro) for n, d, s, ro in _FIXED]
        for conn, tool_name, decision in self._allowed_pinned(agent):
            name = f"{conn.name}__{tool_name}"
            description, schema = self._describe(conn.name, tool_name)
            read_only = decision.tier == Tier.green and not change_words_in(name)
            tools.append(VisibleTool(name, description, schema, read_only))
        return tools

    def _find(self, agent: AgentGrant, query: str, tier: Tier) -> str:
        words = query.lower().split()
        items: list[dict[str, Any]] = []
        for conn in self._manifest.connections:
            for spec in conn.tools:
                if len(items) >= FIND_LIMIT:
                    break
                decision = decide(agent, conn, spec.name)
                if not decision.allowed or decision.tier != tier:
                    continue
                cached = self._catalog.get(conn.name, {}).get(spec.name)
                haystack = f"{spec.name} {cached[0] if cached else ''}".lower()
                if not all(word in haystack for word in words):
                    continue
                description, schema = self._describe(conn.name, spec.name)
                items.append(
                    {
                        "connection": conn.name,
                        "tool": spec.name,
                        "description": description,
                        "input_schema": schema,
                    }
                )
        return json.dumps(items)

    # -- calls ---------------------------------------------------------------------------------

    async def call(self, agent: AgentGrant, name: str, arguments: dict) -> CallResult:
        start = self._clock()
        if not isinstance(arguments, dict):
            arguments = {}
        connection, tool = self._labels(name, arguments)
        ctx = {"tier": ""}
        outcome = "error"  # only an unexpected exception leaves this value
        try:
            result = await self._dispatch(agent, name, arguments, ctx)
            outcome = result.code
        except asyncio.CancelledError:
            outcome = "cancelled"  # an audit outcome only, never a CallResult code
            raise
        finally:
            record(
                self._state_dir,
                agent=agent.name,
                connection=connection,
                tool=tool,
                tier=ctx["tier"],
                outcome=outcome,
                duration_ms=int((self._clock() - start) * 1000),
                args=arguments,
            )
        return result

    @staticmethod
    def _labels(name: str, arguments: dict) -> tuple[str, str]:
        if name in ("call_read_tool", "call_write_tool"):
            conn, tool = arguments.get("connection"), arguments.get("tool")
            if isinstance(conn, str) and isinstance(tool, str):
                return conn, tool
            return "", name
        if "__" in name:
            conn, _, tool = name.partition("__")
            return conn, tool
        return "", name

    def _allow_rate(self, agent_name: str) -> bool:
        now = self._clock()
        window = self._calls.setdefault(agent_name, deque())
        while window and now - window[0] >= RATE_WINDOW_S:
            window.popleft()
        if len(window) >= self._rate:
            return False
        window.append(now)
        return True

    async def _dispatch(
        self, agent: AgentGrant, name: str, arguments: dict, ctx: dict[str, str]
    ) -> CallResult:
        """Pause, then rate limit, then policy. Every fixed tool obeys the first two."""
        if is_paused(self._state_dir):
            return CallResult(False, PAUSED_TEXT, "paused")
        if not self._allow_rate(agent.name):
            return CallResult(False, RATE_TEXT, "rate-limited")
        if name == "connector_guide":
            return CallResult(True, render_guide(self._manifest, agent), "ok")
        if name in ("find_read_tools", "find_write_tools"):
            query = arguments.get("query")
            if not isinstance(query, str):
                return _denied("bad-arguments")
            tier = Tier.green if name == "find_read_tools" else Tier.yellow
            return CallResult(True, self._find(agent, query, tier), "ok")
        if name in ("call_read_tool", "call_write_tool"):
            return await self._through_door(agent, name, arguments, ctx)
        return await self._pinned(agent, name, arguments, ctx)

    async def _through_door(
        self, agent: AgentGrant, name: str, arguments: dict, ctx: dict[str, str]
    ) -> CallResult:
        want, wrong = (
            (Tier.green, "not-a-read-tool")
            if name == "call_read_tool"
            else (Tier.yellow, "not-a-write-tool")
        )
        conn_name = arguments.get("connection")
        tool_name = arguments.get("tool")
        inner = arguments.get("arguments", {})
        if not (isinstance(conn_name, str) and isinstance(tool_name, str) and isinstance(inner, dict)):
            return _denied("bad-arguments")
        conn = self._manifest.connection(conn_name)  # exact match: no strip, no lower
        if conn is None:
            return _denied("unlisted")
        decision = decide(agent, conn, tool_name)
        ctx["tier"] = decision.tier.value if decision.tier else ""
        if not decision.allowed:
            return _refusal(decision)
        if decision.tier != want:
            return _denied(wrong)
        return await self._run(conn, tool_name, decision, inner, agent.call_timeout_s)

    def _allowed_pinned(self, agent: AgentGrant) -> list[tuple[Connection, str, Decision]]:
        """The pinned tools `visible` shows this agent: policy allows them, 20 at most."""
        return allowed_pinned(self._manifest, agent)

    async def _pinned(
        self, agent: AgentGrant, name: str, arguments: dict, ctx: dict[str, str]
    ) -> CallResult:
        conn_name, sep, tool_name = name.partition("__")
        conn = self._manifest.connection(conn_name) if sep else None
        spec = next((t for t in conn.tools if t.name == tool_name), None) if conn else None
        if conn is None or spec is None or not spec.pinned:
            return CallResult(False, UNKNOWN_TEXT, "unknown-tool")
        decision = decide(agent, conn, tool_name)
        ctx["tier"] = decision.tier.value if decision.tier else ""
        if not decision.allowed:
            return _refusal(decision)
        # Only a name that `visible` returns can be called: a pinned tool past the cap does not exist.
        if not any(c.name == conn.name and t == tool_name for c, t, _ in self._allowed_pinned(agent)):
            ctx["tier"] = ""
            return CallResult(False, UNKNOWN_TEXT, "unknown-tool")
        return await self._run(conn, tool_name, decision, arguments, agent.call_timeout_s)

    async def _run(
        self,
        conn: Connection,
        tool_name: str,
        decision: Decision,
        arguments: dict,
        budget_s: int | None = None,
    ) -> CallResult:
        """One upstream call. A green call retries once. `budget_s` caps both tries together."""
        upstream = self._upstreams.get(conn.name)
        spec = next(t for t in conn.tools if t.name == tool_name)
        if upstream is None:
            return CallResult(False, NOT_AVAILABLE_TEXT, "not-available")
        attempts = 2 if decision.tier == Tier.green else 1
        failure = CallResult(False, UPSTREAM_ERROR_TEXT, "upstream-error")
        deadline = None if budget_s is None else self._clock() + budget_s
        for _ in range(attempts):
            timeout: float = spec.timeout_s
            if deadline is not None:
                left = deadline - self._clock()
                if left <= 0:  # the budget is spent: no retry
                    break
                timeout = min(timeout, left)
            try:
                out = await asyncio.wait_for(
                    upstream.call_tool(tool_name, arguments), timeout=timeout
                )
            except SecretUnavailable:
                return CallResult(False, NOT_AVAILABLE_TEXT, "not-available")
            except UpstreamAuthError:
                return CallResult(False, LOGIN_TEXT, "needs-login")
            except TimeoutError:
                failure = CallResult(False, TIMEOUT_TEXT, "timeout")
            except UpstreamError:
                failure = CallResult(False, UPSTREAM_ERROR_TEXT, "upstream-error")
            except (asyncio.CancelledError, KeyboardInterrupt):
                raise
            except BaseException:  # noqa: BLE001 - incl. SystemExit: no retry, no text is kept
                return CallResult(False, UPSTREAM_ERROR_TEXT, "upstream-error")
            else:
                try:
                    return CallResult(True, self._finish(upstream, out), "ok")
                except BaseException:  # noqa: BLE001 - a result that cannot be converted
                    return CallResult(False, UPSTREAM_ERROR_TEXT, "upstream-error")
        return failure

    def _finish(self, upstream: Upstream, out: object) -> str:
        text = scrub(out if isinstance(out, str) else str(out), upstream.secret_values())
        if len(text) > self._limit:
            omitted = len(text) - self._limit
            text = f"{text[: self._limit]}[cut by connector: {omitted} characters omitted]"
        return text


def _denied(reason: str) -> CallResult:
    return CallResult(False, f"Refused: {reason}.", f"denied:{reason}")


def _refusal(decision: Decision) -> CallResult:
    if decision.reason == "tier-red":
        return CallResult(False, RED_TEXT, "denied:tier-red")
    return _denied(decision.reason)
