from __future__ import annotations

import asyncio
import hashlib
import json
import re
from pathlib import Path

import pytest

from helpers.mcp_stub import make_stub_app, run_app
from universal_connector import audit
from universal_connector.manifest import load_manifest
from universal_connector.models import (
    AddOn,
    AgentGrant,
    Auth,
    Connection,
    Manifest,
    Reach,
    Scope,
    Tier,
    ToolSpec,
)
from universal_connector.router import (
    ODDBORO_CHANGE_WORDS,
    RED_TEXT,
    Router,
    change_words_in,
)
from universal_connector.upstreams.base import ToolInfo, UpstreamAuthError, UpstreamError
from universal_connector.upstreams.mcp_remote import McpRemoteUpstream
from universal_connector.vault import MemorySecretStore, SecretUnavailable

ROOT = Path(__file__).resolve().parents[1]
KEY = "fake-rtr-key-0001"

G, Y, R = Tier.green, Tier.yellow, Tier.red


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class FakeUpstream:
    def __init__(self, key: str = "", result: str = "result", script: list | None = None) -> None:
        self.key = key
        self.result = result
        self.script = list(script or [])
        self.calls: list[tuple[str, dict]] = []
        self.tools: list[ToolInfo] = []
        self.list_error: Exception | None = None

    async def list_tools(self) -> list[ToolInfo]:
        if self.list_error is not None:
            raise self.list_error
        return list(self.tools)

    async def call_tool(self, name: str, arguments: dict) -> str:
        self.calls.append((name, arguments))
        outcome = self.script.pop(0) if self.script else self.result
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    async def probe(self):  # pragma: no cover - not used by the router
        raise NotImplementedError

    def secret_values(self) -> list[str]:
        return [self.key] if self.key else []

    def purge(self) -> int:
        return 0


def conn(
    name: str,
    tools: dict[str, tuple[Tier, bool]],
    scopes: set[Scope] | None = None,
    timeout_s: float = 60,
) -> Connection:
    return Connection(
        name=name,
        kind="mcp-remote",
        upstream="https://up.example.invalid/mcp",
        auth=Auth(type="none"),
        scopes=scopes or {Scope.work},
        reach=Reach.starter,
        tools=[
            # model_copy skips checks on the updated field only: it is a strict int, and the slow
            # tests need sub-second timeouts. Every other field is validated.
            ToolSpec(name=t, tier=tier, pinned=pinned).model_copy(update={"timeout_s": timeout_s})
            for t, (tier, pinned) in tools.items()
        ],
    )


def agent(addons: set[AddOn] | None = None, scopes: set[Scope] | None = None) -> AgentGrant:
    return AgentGrant(
        name="alpha", scopes=scopes or {Scope.work}, reach=Reach.full_read, addons=addons or set()
    )


WORK = agent()
DRAFTS = agent({AddOn.drafts})


def make(
    tmp_path: Path,
    connections: list[Connection],
    upstreams: dict[str, FakeUpstream] | None = None,
    clock: Clock | None = None,
    **kwargs,
) -> Router:
    manifest = Manifest(version=1, connections=connections, agents=[WORK])
    ups = upstreams if upstreams is not None else {c.name: FakeUpstream() for c in connections}
    return Router(manifest, ups, tmp_path / "state", clock=clock or Clock(), **kwargs)


def one(tmp_path: Path, tools: dict[str, tuple[Tier, bool]], up: FakeUpstream | None = None, **kw):
    up = up or FakeUpstream()
    return make(tmp_path, [conn("a", tools)], {"a": up}, **kw), up


async def read(router: Router, who: AgentGrant, connection: str, tool: str, args: dict | None = None):
    return await router.call(
        who, "call_read_tool", {"connection": connection, "tool": tool, "arguments": args or {}}
    )


async def write(router: Router, who: AgentGrant, connection: str, tool: str, args: dict | None = None):
    return await router.call(
        who, "call_write_tool", {"connection": connection, "tool": tool, "arguments": args or {}}
    )


FIXED = [
    "connector_guide",
    "find_read_tools",
    "call_read_tool",
    "find_write_tools",
    "call_write_tool",
]


# -- what an agent sees ------------------------------------------------------------------------


def test_fixed_tools_first_and_cap(tmp_path):
    pinned = {f"tool{i}": (G, True) for i in range(8)}
    router = make(tmp_path, [conn("a", pinned), conn("b", pinned), conn("c", pinned)])
    names = [t.name for t in router.visible(WORK)]
    assert names[:5] == FIXED
    assert len(names) == 25
    assert names[5] == "a__tool0"


def test_fixed_tool_read_only_flags(tmp_path):
    router, _ = one(tmp_path, {})
    flags = {t.name: t.read_only for t in router.visible(WORK)}
    assert flags == {
        "connector_guide": True,
        "find_read_tools": True,
        "call_read_tool": True,
        "find_write_tools": False,
        "call_write_tool": False,
    }


async def test_same_tool_name_two_connections(tmp_path):
    ups = {"a": FakeUpstream(result="from a"), "b": FakeUpstream(result="from b")}
    router = make(
        tmp_path, [conn("a", {"search": (G, True)}), conn("b", {"search": (G, True)})], ups
    )
    names = [t.name for t in router.visible(WORK)]
    assert "a__search" in names and "b__search" in names
    out_a = await router.call(WORK, "a__search", {"q": 1})
    out_b = await router.call(WORK, "b__search", {"q": 2})
    assert out_a.text == "from a" and out_b.text == "from b"
    assert ups["a"].calls == [("search", {"q": 1})] and ups["b"].calls == [("search", {"q": 2})]


async def test_personal_connection_invisible_to_work_agent(tmp_path):
    personal = conn("mine", {"ping": (G, True)}, scopes={Scope.personal})
    router = make(tmp_path, [personal])
    assert all(not t.name.startswith("mine__") for t in router.visible(WORK))
    found = await router.call(WORK, "find_read_tools", {"query": ""})
    assert "mine" not in found.text and json.loads(found.text) == []
    refused = await read(router, WORK, "mine", "ping")
    assert refused.code == "denied:scope" and refused.ok is False


async def test_red_tool_refused_with_draft_message(tmp_path):
    router, up = one(tmp_path, {"capture": (R, True)})
    for result in (
        await read(router, DRAFTS, "a", "capture"),
        await write(router, DRAFTS, "a", "capture"),
        await router.call(DRAFTS, "a__capture", {}),
    ):
        assert result.code == "denied:tier-red" and result.text == RED_TEXT
    assert up.calls == []
    assert all(t.name != "a__capture" for t in router.visible(DRAFTS))


async def test_unlisted_tool_refused(tmp_path):
    router, up = one(tmp_path, {"ping": (G, False)})
    assert (await read(router, WORK, "a", "nope")).code == "denied:unlisted"
    assert (await read(router, WORK, "nope", "ping")).code == "denied:unlisted"
    assert up.calls == []


async def test_write_tool_through_read_door_refused(tmp_path):
    router, up = one(tmp_path, {"draft": (Y, False), "ping": (G, False)})
    assert (await read(router, DRAFTS, "a", "draft")).code == "denied:not-a-read-tool"
    assert (await write(router, DRAFTS, "a", "ping")).code == "denied:not-a-write-tool"
    assert up.calls == []


async def test_yellow_needs_drafts_addon(tmp_path):
    router, up = one(tmp_path, {"draft": (Y, True)})
    assert (await write(router, WORK, "a", "draft")).code == "denied:addon-drafts"
    assert (await router.call(WORK, "a__draft", {})).code == "denied:addon-drafts"
    assert (await read(router, WORK, "a", "draft")).code == "denied:addon-drafts"
    assert up.calls == []
    assert all(t.name != "a__draft" for t in router.visible(WORK))
    visible = {t.name: t.read_only for t in router.visible(DRAFTS)}
    assert visible["a__draft"] is False
    assert (await write(router, DRAFTS, "a", "draft")).code == "ok"
    assert len(up.calls) == 1


async def test_unknown_tool_names(tmp_path):
    other = conn("b", {"ping": (G, True)}, scopes={Scope.personal})
    router = make(tmp_path, [conn("a", {"ping": (G, True), "quiet": (G, False)}), other])
    for name in ("nothing", "a__nope", "a__quiet", "zzz__ping", "__ping", "a__"):
        assert (await router.call(WORK, name, {})).code == "unknown-tool"
    # a pinned name that policy refuses is a refusal, not an unknown tool
    assert (await router.call(WORK, "b__ping", {})).code == "denied:scope"


async def test_bad_arguments_are_refused(tmp_path):
    router, up = one(tmp_path, {"ping": (G, False)})
    assert (await router.call(WORK, "call_read_tool", {"connection": 1})).code == "denied:bad-arguments"
    assert (await router.call(WORK, "find_read_tools", {})).code == "denied:bad-arguments"
    assert (
        await router.call(
            WORK, "call_read_tool", {"connection": "a", "tool": "ping", "arguments": "x"}
        )
    ).code == "denied:bad-arguments"
    assert up.calls == []


async def test_find_tools_match_every_word_and_cap(tmp_path):
    tools = {f"read_item_{i}": (G, False) for i in range(12)}
    tools["list_notes"] = (G, False)
    tools["draft"] = (Y, False)
    router, up = one(tmp_path, tools)
    everything = json.loads((await router.call(WORK, "find_read_tools", {"query": ""})).text)
    assert len(everything) == 10
    notes = json.loads((await router.call(WORK, "find_read_tools", {"query": "NOTES list"})).text)
    assert [item["tool"] for item in notes] == ["list_notes"]
    assert set(notes[0]) == {"connection", "tool", "description", "input_schema"}
    assert json.loads((await router.call(WORK, "find_read_tools", {"query": "draft"})).text) == []
    # yellow tools appear for the write finder only when the add-on is granted
    assert json.loads((await router.call(WORK, "find_write_tools", {"query": ""})).text) == []
    found = json.loads((await router.call(DRAFTS, "find_write_tools", {"query": "draft"})).text)
    assert [item["tool"] for item in found] == ["draft"]
    assert up.calls == []


# -- read-only marking ---------------------------------------------------------------------------


def test_read_only_names_have_no_change_word(tmp_path):
    manifest = load_manifest(ROOT / "examples" / "manifest")
    router = Router(manifest, {}, tmp_path / "state")
    grants = [
        AgentGrant(name="g", scopes={Scope.work, Scope.personal}, reach=reach, addons=addons)
        for reach in Reach
        for addons in (set(), {AddOn.drafts})
    ]
    assert grants
    for grant in grants:
        for tool in router.visible(grant):
            if tool.read_only:
                assert change_words_in(tool.name) == set(), tool.name


def test_read_only_fixed_tools_have_no_change_word():
    for name in ("connector_guide", "find_read_tools", "call_read_tool"):
        assert change_words_in(name) == set()
    assert change_words_in("call_write_tool") == {"write"}
    assert len(ODDBORO_CHANGE_WORDS) == 42


def test_tool_with_change_word_is_not_marked_read_only(tmp_path):
    connections = [
        conn("a", {"capture_note": (G, True), "search": (G, True), "draft": (Y, True)}),
        conn("send_box", {"ping": (G, True)}),
    ]
    router = make(tmp_path, connections)
    flags = {t.name: t.read_only for t in router.visible(DRAFTS)}
    assert flags["a__capture_note"] is False
    assert flags["a__search"] is True
    assert flags["a__draft"] is False
    assert flags["send_box__ping"] is False


# -- catalog -------------------------------------------------------------------------------------


async def test_visible_without_catalog_uses_fallback(tmp_path):
    router, _ = one(tmp_path, {"ping": (G, True)})
    tool = next(t for t in router.visible(WORK) if t.name == "a__ping")
    assert tool.description == "a tool ping. Details are not loaded yet."
    assert tool.input_schema == {"type": "object"}


async def test_upstream_description_is_redacted(tmp_path):
    up = FakeUpstream(key=KEY)
    up.tools = [ToolInfo("ping", f"Pings with {KEY} inside.", {"type": "object"})]
    router, _ = one(tmp_path, {"ping": (G, True)}, up)
    assert await router.refresh() == {"a": "ok"}
    tool = next(t for t in router.visible(WORK) if t.name == "a__ping")
    assert KEY not in tool.description and "[redacted]" in tool.description
    found = await router.call(WORK, "find_read_tools", {"query": "pings"})
    assert KEY not in found.text and "[redacted]" in found.text


async def test_schema_strings_are_redacted(tmp_path):
    up = FakeUpstream(key=KEY)
    schema = {
        "type": "object",
        "properties": {
            f"p_{KEY}": {"description": f"use {KEY}", "enum": [KEY, "x"], "default": [[KEY]]},
        },
        "required": [],
    }
    up.tools = [ToolInfo("ping", "Pings.", schema)]
    router, _ = one(tmp_path, {"ping": (G, True)}, up)
    await router.refresh()
    shown = next(t for t in router.visible(WORK) if t.name == "a__ping")
    found = await router.call(WORK, "find_read_tools", {"query": "ping"})
    assert KEY not in json.dumps(shown.input_schema) and KEY not in found.text
    assert "[redacted]" in json.dumps(shown.input_schema)
    shown.input_schema["type"] = "changed"  # a caller cannot change the cache
    again = next(t for t in router.visible(WORK) if t.name == "a__ping")
    assert again.input_schema["type"] == "object"


async def test_refresh_drops_unlisted_upstream_tools(tmp_path):
    up = FakeUpstream()
    up.tools = [
        ToolInfo("ping", "Listed.", {"type": "object"}),
        ToolInfo("hidden_admin", "Not in the manifest.", {"type": "object"}),
    ]
    router, _ = one(tmp_path, {"ping": (G, True)}, up)
    await router.refresh()
    assert set(router._catalog["a"]) == {"ping"}
    assert "hidden_admin" not in json.dumps([t.__dict__ for t in router.visible(WORK)])


async def test_refresh_keeps_last_good_on_failure(tmp_path):
    up = FakeUpstream()
    up.tools = [ToolInfo("ping", "First description.", {"type": "object"})]
    router, _ = one(tmp_path, {"ping": (G, True)}, up)
    assert await router.refresh(["a"]) == {"a": "ok"}
    expected = {
        "needs-login": UpstreamAuthError("x"),
        "not-available": SecretUnavailable("x"),
        "upstream-error": UpstreamError("x"),
        "timeout": TimeoutError(),
    }
    for status, error in expected.items():
        up.list_error = error
        assert await router.refresh(["a"]) == {"a": status}
        tool = next(t for t in router.visible(WORK) if t.name == "a__ping")
        assert tool.description == "First description."
    up.list_error = None
    up.tools = [ToolInfo("ping", "Second description.", {"type": "object"})]
    assert await router.refresh() == {"a": "ok"}
    tool = next(t for t in router.visible(WORK) if t.name == "a__ping")
    assert tool.description == "Second description."


async def test_refresh_never_raises(tmp_path):
    bad = FakeUpstream()
    bad.list_error = RuntimeError("boom with ghost@example.invalid")
    fine = FakeUpstream()
    fine.tools = [ToolInfo("ping", "Fine.", {"type": "object"})]
    malformed = FakeUpstream()
    malformed.tools = [object()]  # type: ignore[list-item]
    router = make(
        tmp_path,
        [
            conn("bad", {"ping": (G, True)}),
            conn("fine", {"ping": (G, True)}),
            conn("malformed", {"ping": (G, True)}),
            conn("noup", {"ping": (G, True)}),
        ],
        {"bad": bad, "fine": fine, "malformed": malformed},
    )
    statuses = await router.refresh()
    assert statuses == {
        "bad": "upstream-error",
        "fine": "ok",
        "malformed": "upstream-error",
        "noup": "not-available",
    }
    assert await router.refresh(["ghost", "fine"]) == {"ghost": "not-available", "fine": "ok"}
    assert "ghost@example.invalid" not in json.dumps(statuses)


# -- calls ---------------------------------------------------------------------------------------


async def test_green_retries_once(tmp_path):
    for first in (UpstreamError("x"), TimeoutError()):
        router, up = one(tmp_path / str(type(first).__name__), {"ping": (G, False)})
        up.script = [first, "fine"]
        result = await read(router, WORK, "a", "ping")
        assert result.ok and result.text == "fine" and result.code == "ok"
        assert len(up.calls) == 2


async def test_green_gives_up_after_one_retry(tmp_path):
    router, up = one(tmp_path, {"ping": (G, False)})
    up.script = [UpstreamError("x"), UpstreamError("y"), "never reached"]
    result = await read(router, WORK, "a", "ping")
    assert result.code == "upstream-error" and len(up.calls) == 2
    up.script = [TimeoutError(), TimeoutError()]
    assert (await read(router, WORK, "a", "ping")).code == "timeout"


async def test_yellow_never_retries(tmp_path):
    router, up = one(tmp_path, {"draft": (Y, False)})
    up.script = [UpstreamError("x"), "fine"]
    result = await write(router, DRAFTS, "a", "draft")
    assert result.code == "upstream-error" and len(up.calls) == 1
    up.script = [TimeoutError(), "fine"]
    assert (await write(router, DRAFTS, "a", "draft")).code == "timeout"
    assert len(up.calls) == 2


async def test_error_text_holds_nothing_from_the_upstream(tmp_path):
    router, up = one(tmp_path, {"ping": (G, False)}, FakeUpstream(key=KEY))
    up.script = [UpstreamError(f"bad {KEY} MARKER"), UpstreamError(f"bad {KEY} MARKER")]
    result = await read(router, WORK, "a", "ping")
    assert "MARKER" not in result.text and KEY not in result.text


async def test_real_timeout_is_enforced(tmp_path):
    class Slow(FakeUpstream):
        async def call_tool(self, name, arguments):
            self.calls.append((name, arguments))
            await asyncio.sleep(5)
            return "late"

    up = Slow()
    router = make(tmp_path, [conn("a", {"draft": (Y, False)}, timeout_s=0.3)], {"a": up})
    result = await write(router, DRAFTS, "a", "draft")
    assert result.code == "timeout" and len(up.calls) == 1


async def test_secret_echo_is_redacted(tmp_path):
    router, _ = one(tmp_path, {"ping": (G, False)}, FakeUpstream(key=KEY, result=f"key is {KEY}!"))
    result = await read(router, WORK, "a", "ping")
    assert result.ok and "[redacted]" in result.text and KEY not in result.text


async def test_long_result_is_cut(tmp_path):
    router, _ = one(tmp_path, {"ping": (G, False)}, FakeUpstream(result="x" * 70_000))
    result = await read(router, WORK, "a", "ping")
    note = "[cut by connector: 10000 characters omitted]"
    assert result.text == "x" * 60_000 + note
    short, _ = one(tmp_path / "s", {"ping": (G, False)}, FakeUpstream(result="x" * 60_000))
    assert (await read(short, WORK, "a", "ping")).text == "x" * 60_000


async def test_cut_comes_after_redaction(tmp_path):
    result = "y" * 59_990 + KEY + "z" * 100
    router, _ = one(tmp_path, {"ping": (G, False)}, FakeUpstream(key=KEY, result=result))
    text = (await read(router, WORK, "a", "ping")).text
    assert KEY not in text and KEY[:6] not in text
    assert text.endswith("characters omitted]")


async def test_missing_vault_entry_is_not_available(tmp_path):
    router, up = one(tmp_path, {"ping": (G, False)})
    up.script = [SecretUnavailable("vault entry not available: x")]
    result = await read(router, WORK, "a", "ping")
    assert result.code == "not-available" and result.ok is False
    assert len(up.calls) == 1
    missing = make(tmp_path / "m", [conn("a", {"ping": (G, False)})], {})
    assert (await read(missing, WORK, "a", "ping")).code == "not-available"


async def test_auth_error_is_needs_login(tmp_path):
    router, up = one(tmp_path, {"ping": (G, False)})
    up.script = [UpstreamAuthError("needs-login")]
    result = await read(router, WORK, "a", "ping")
    assert result.code == "needs-login"
    assert result.text == "This connection needs a re-login by the owner."
    assert len(up.calls) == 1


async def test_paused(tmp_path):
    router, up = one(tmp_path, {"ping": (G, True)})
    audit.set_paused(tmp_path / "state", True)
    for name, args in (
        ("a__ping", {}),
        ("call_read_tool", {"connection": "a", "tool": "ping", "arguments": {}}),
        ("connector_guide", {}),
    ):
        assert (await router.call(WORK, name, args)).code == "paused"
    assert up.calls == []
    audit.set_paused(tmp_path / "state", False)
    assert (await router.call(WORK, "a__ping", {})).code == "ok"


async def test_pause_is_checked_before_the_rate_limit(tmp_path):
    router, _ = one(tmp_path, {"ping": (G, True)}, rate_per_minute=1)
    audit.set_paused(tmp_path / "state", True)
    for _ in range(3):
        assert (await router.call(WORK, "a__ping", {})).code == "paused"
    audit.set_paused(tmp_path / "state", False)
    assert (await router.call(WORK, "a__ping", {})).code == "ok"  # paused calls did not count


async def test_rate_limit(tmp_path):
    clock = Clock()
    router, up = one(tmp_path, {"ping": (G, True)}, clock=clock)
    for _ in range(120):
        assert (await router.call(WORK, "a__ping", {})).code == "ok"
    assert (await router.call(WORK, "a__ping", {})).code == "rate-limited"
    assert len(up.calls) == 120
    clock.now += 59
    assert (await router.call(WORK, "a__ping", {})).code == "rate-limited"
    clock.now += 1
    assert (await router.call(WORK, "a__ping", {})).code == "ok"


async def test_rate_limit_counts_per_agent_and_before_policy(tmp_path):
    router, up = one(tmp_path, {"ping": (G, True)}, rate_per_minute=2)
    other = AgentGrant(name="beta", scopes={Scope.work}, reach=Reach.full_read)
    assert (await router.call(WORK, "a__ping", {})).code == "ok"
    assert (await router.call(WORK, "a__nothing", {})).code == "unknown-tool"
    assert (await router.call(WORK, "a__ping", {})).code == "rate-limited"
    assert (await router.call(other, "a__ping", {})).code == "ok"
    assert len(up.calls) == 2


async def test_every_call_audited(tmp_path):
    router, _ = one(tmp_path, {"ping": (G, True), "capture": (R, False)})
    secret_arg = {"q": "private words"}
    codes = [
        (await router.call(WORK, "a__ping", secret_arg)).code,
        (await read(router, WORK, "a", "capture")).code,
        (await router.call(WORK, "nothing", {})).code,
    ]
    lines = list(reversed(audit.tail(tmp_path / "state", 10)))
    assert [line["outcome"] for line in lines] == codes == ["ok", "denied:tier-red", "unknown-tool"]
    assert [(line["connection"], line["tool"]) for line in lines] == [
        ("a", "ping"),
        ("a", "capture"),
        ("", "nothing"),
    ]
    assert [line["tier"] for line in lines] == ["green", "red", ""]
    assert all(line["agent"] == "alpha" for line in lines)
    assert "private words" not in json.dumps(lines)
    plain = hashlib.sha256(json.dumps(secret_arg, sort_keys=True).encode()).hexdigest()
    assert re.fullmatch(r"[0-9a-f]{64}", lines[0]["args_sha256"])
    assert lines[0]["args_sha256"] != plain  # salted: a guess cannot be checked without the salt


async def test_fixed_tools_without_upstream_calls(tmp_path):
    router, up = one(tmp_path, {"ping": (G, True)})
    guide = await router.call(WORK, "connector_guide", {})
    assert guide.ok and guide.text.startswith("# Connector guide")
    assert up.calls == []


# -- QA round 1 fixes ----------------------------------------------------------------------------

STUB_KEY = "fake-stub-key-0001"


class BlockingUpstream(FakeUpstream):
    async def call_tool(self, name: str, arguments: dict) -> str:
        self.calls.append((name, arguments))
        await asyncio.Event().wait()
        return "never"


async def wait_until(predicate, seconds: float = 5.0) -> None:
    for _ in range(int(seconds / 0.02)):
        if predicate():
            return
        await asyncio.sleep(0.02)
    raise AssertionError("condition not reached")


def stub_router(tmp_path: Path, base: str, timeout_s: float = 0.3):
    """A router over the real McpRemoteUpstream: a green tool `g` and a yellow tool `y` that sleep."""

    def spec(tier: Tier) -> Connection:
        return Connection(
            name="a" if tier == G else "b",
            kind="mcp-remote",
            upstream=f"{base}/mcp",
            auth=Auth(type="header", header="x-test-key", secret="stub/key"),
            scopes={Scope.work},
            reach=Reach.starter,
            tools=[ToolSpec(name="slow", tier=tier).model_copy(update={"timeout_s": timeout_s})],
        )

    conns = [spec(G), spec(Y)]
    ups = {
        c.name: McpRemoteUpstream(c, MemorySecretStore({"stub/key": STUB_KEY}), timeout_s=30)
        for c in conns
    }
    return make(tmp_path, conns, ups)  # type: ignore[arg-type]


def slow_app(started: list[int], sleep_s: float = 0.6):
    async def slow() -> str:
        started.append(1)
        await asyncio.sleep(sleep_s)
        return "late"

    return make_stub_app({"slow": slow}, required_header=("x-test-key", STUB_KEY))


async def test_real_adapter_timeout_is_timeout(tmp_path):
    started: list[int] = []
    # A 0.1 s tool timeout and a 0.3 s tool: the stub's shutdown waits out only the short sleep.
    with run_app(slow_app(started, sleep_s=0.3)) as base:
        router = stub_router(tmp_path, base, timeout_s=0.1)
        green = await read(router, DRAFTS, "a", "slow")
        assert green.code == "timeout" and len(started) == 2
        started.clear()
        yellow = await write(router, DRAFTS, "b", "slow")
        assert yellow.code == "timeout" and len(started) == 1


async def test_real_adapter_cancel_is_not_retried(tmp_path):
    started: list[int] = []
    with run_app(slow_app(started)) as base:
        router = stub_router(tmp_path, base)
        task = asyncio.create_task(read(router, DRAFTS, "a", "slow"))
        await wait_until(lambda: started)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await asyncio.sleep(0.3)
        assert len(started) == 1
    lines = audit.tail(tmp_path / "state", 10)
    assert [line["outcome"] for line in lines] == ["cancelled"]


async def test_cancelled_call_audited_once_and_not_retried(tmp_path):
    up = BlockingUpstream()
    router, _ = one(tmp_path, {"ping": (G, True)}, up)
    task = asyncio.create_task(router.call(WORK, "a__ping", {"q": 1}))
    await wait_until(lambda: up.calls)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await asyncio.sleep(0.1)
    assert len(up.calls) == 1
    lines = audit.tail(tmp_path / "state", 10)
    assert [(line["outcome"], line["tool"], line["tier"]) for line in lines] == [
        ("cancelled", "ping", "green")
    ]


async def test_green_does_not_retry_unexpected_errors(tmp_path):
    for index, error in enumerate((RuntimeError("x"), ValueError("y"), KeyError("z"))):
        router, up = one(tmp_path / str(index), {"ping": (G, False)})
        up.script = [error, "fine"]
        result = await read(router, WORK, "a", "ping")
        assert result.code == "upstream-error" and len(up.calls) == 1
        assert result.text == "The upstream call failed."  # no exception text is passed on


async def test_upstream_system_exit_is_contained(tmp_path):
    for index, error in enumerate((SystemExit("MRK-exit-text"), GeneratorExit("MRK-gen"))):
        router, up = one(tmp_path / str(index), {"ping": (G, False)})
        up.script = [error, "fine"]
        result = await read(router, WORK, "a", "ping")
        assert result.code == "upstream-error" and len(up.calls) == 1
        assert result.text == "The upstream call failed."
        assert "MRK" not in result.text


async def test_cancellation_still_propagates(tmp_path):
    router, up = one(tmp_path, {"ping": (G, False)})
    up.script = [asyncio.CancelledError()]
    with pytest.raises(asyncio.CancelledError):
        await read(router, WORK, "a", "ping")


class _BadStr:
    def __str__(self) -> str:
        raise RuntimeError("MRK-str-text")


async def test_result_conversion_failure_is_fixed_text(tmp_path):
    for index, outcome in enumerate((_BadStr(), _BadStr())):
        router, up = one(tmp_path / str(index), {"ping": (G, False)})
        up.script = [outcome]
        result = await read(router, WORK, "a", "ping")
        assert result.ok is False and result.code == "upstream-error"
        assert result.text == "The upstream call failed."
        assert len(up.calls) == 1


def oddboro_words(name: str) -> list[str]:
    """A literal port of the way Oddboro splits a tool name into words."""
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", name)
    return [part for part in re.split(r"[^a-z0-9]+", spaced.lower()) if part]


SPLIT_CORPUS = [
    "messages.send",
    "files/upload",
    "sendé",
    "gmailCreateDraft",
    "get__thought",
    "gm__messages.send",
    "gm__files/upload",
    "gm__sendé",
    "a b\tc",
    "getHTTPResponse",
    "x9Delete",
    "UPDATE_ALL",
    "create-issue",
    "search post",
    "ÉditÉ",
    "",
]


def test_splitter_covers_oddboro_words():
    from universal_connector.router import name_words

    for name in SPLIT_CORPUS:
        assert set(oddboro_words(name)) <= set(name_words(name)), name
    assert change_words_in("gm__messages.send") == {"send"}
    assert change_words_in("gm__files/upload") == {"upload"}
    assert change_words_in("gm__sendé") == {"send"}


async def test_split_names_are_not_marked_read_only(tmp_path):
    names = {"messages.send": (G, True), "files/upload": (G, True), "sendé": (G, True)}
    router, _ = one(tmp_path, {**names, "search": (G, True)})
    flags = {t.name: t.read_only for t in router.visible(WORK)}
    assert flags["a__search"] is True
    assert flags["a__messages.send"] is False
    assert flags["a__files/upload"] is False
    assert flags["a__sendé"] is False


async def test_pinned_call_beyond_cap_is_unknown_tool(tmp_path):
    router, up = one(tmp_path, {f"t{i:02d}": (G, True) for i in range(21)})
    names = [t.name for t in router.visible(WORK)]
    assert "a__t19" in names and "a__t20" not in names
    assert (await router.call(WORK, "a__t19", {})).code == "ok"
    assert (await router.call(WORK, "a__t20", {})).code == "unknown-tool"
    assert len(up.calls) == 1
    assert (await read(router, WORK, "a", "t20")).code == "ok"  # the finder door still reaches it


async def test_fixed_tools_are_rate_limited_and_paused(tmp_path):
    tools = {"ping": (G, False), "draft": (Y, False)}
    fixed_calls = {
        "connector_guide": {},
        "find_read_tools": {"query": ""},
        "call_read_tool": {"connection": "a", "tool": "ping", "arguments": {}},
        "find_write_tools": {"query": ""},
        "call_write_tool": {"connection": "a", "tool": "draft", "arguments": {}},
    }
    for name, args in fixed_calls.items():
        router, up = one(tmp_path / name, tools, rate_per_minute=2)
        assert (await router.call(DRAFTS, name, args)).code != "rate-limited"
        assert (await router.call(DRAFTS, name, args)).code != "rate-limited"
        limited = await router.call(DRAFTS, name, args)
        assert limited.code == "rate-limited", name
        calls_before = len(up.calls)
        audit.set_paused(tmp_path / name / "state", True)
        assert (await router.call(DRAFTS, name, args)).code == "paused", name
        assert len(up.calls) == calls_before


async def test_refresh_times_out_one_upstream(tmp_path, monkeypatch):
    class SlowList(FakeUpstream):
        async def list_tools(self):
            await asyncio.sleep(3)
            return []

    fine = FakeUpstream()
    fine.tools = [ToolInfo("ping", "Fine.", {"type": "object"})]
    monkeypatch.setattr("universal_connector.router.REFRESH_TIMEOUT_S", 0.2)
    router = make(
        tmp_path,
        [conn("slow", {"ping": (G, True)}), conn("fine", {"ping": (G, True)})],
        {"slow": SlowList(), "fine": fine},
    )
    assert await router.refresh() == {"slow": "timeout", "fine": "ok"}


def test_router_init_creates_state(tmp_path):
    state = tmp_path / "fresh" / "state"
    assert not state.exists()
    make_router = Router(Manifest(version=1, connections=[], agents=[]), {}, state)
    assert make_router is not None
    assert (state / "state.db").is_file()
    assert (state.stat().st_mode & 0o777) == 0o700
    assert ((state / "state.db").stat().st_mode & 0o777) == 0o600


async def test_connection_name_must_match_exactly(tmp_path):
    router, up = one(tmp_path, {"ping": (G, False)})
    for bad in ("A", " a", "a ", "a\n", "a" + chr(0x200B), chr(0xFF41)):
        assert (await read(router, WORK, bad, "ping")).code == "denied:unlisted", repr(bad)
    for bad_tool in ("PING", " ping", "ping "):
        assert (await read(router, WORK, "a", bad_tool)).code == "denied:unlisted", repr(bad_tool)
    assert up.calls == []
    assert (await read(router, WORK, "a", "ping")).code == "ok"


async def test_door_sends_inner_arguments_only(tmp_path):
    router, up = one(tmp_path, {"ping": (G, False), "draft": (Y, False)})
    await read(router, WORK, "a", "ping", {"q": 1})
    await write(router, DRAFTS, "a", "draft", {"to": "x"})
    assert up.calls == [("ping", {"q": 1}), ("draft", {"to": "x"})]


async def test_audit_names_are_bounded_from_router(tmp_path):
    router, _ = one(tmp_path, {"ping": (G, False)})
    await read(router, WORK, "x" * 50_000, "ping")
    await read(router, WORK, "a", "pé\n\x00ing")
    lines = audit.tail(tmp_path / "state", 10)
    assert lines[1]["connection"] == "x" * 128
    assert lines[0]["tool"] == "p???ing"
    assert all(len(line["connection"]) <= 128 and len(line["tool"]) <= 128 for line in lines)


# -- fixed tools only (Task B3) ----------------------------------------------------------------


def fixed_only(addons: set[AddOn] | None = None) -> AgentGrant:
    return AgentGrant(
        name="alpha",
        scopes={Scope.work},
        reach=Reach.full_read,
        addons=addons or set(),
        pinned_tools=False,
    )


def test_pinned_tools_defaults_to_true():
    assert WORK.pinned_tools is True


def test_fixed_only_agent_sees_only_the_five_fixed_tools(tmp_path):
    router, _ = one(tmp_path, {"ping": (G, True), "draft": (Y, True)})
    assert [t.name for t in router.visible(fixed_only({AddOn.drafts}))] == FIXED
    assert "a__ping" in [t.name for t in router.visible(WORK)]


async def test_fixed_only_agent_pinned_name_refused_like_a_hidden_tool(tmp_path):
    router, up = one(tmp_path, {"ping": (G, True)})
    who = fixed_only()
    result = await router.call(who, "a__ping", {})
    assert (result.ok, result.code, result.text) == (False, "unknown-tool", "No such tool.")
    assert up.calls == []
    # the refusal is the same one a name past the 25-tool cap gets
    many = {f"tool{i}": (G, True) for i in range(21)}
    capped, _ = one(tmp_path / "cap", many)
    past = await capped.call(WORK, "a__tool20", {})
    assert (past.ok, past.code, past.text) == (result.ok, result.code, result.text)


async def test_fixed_only_agent_keeps_read_and_write_doors(tmp_path):
    router, up = one(tmp_path, {"ping": (G, True), "draft": (Y, True)})
    who = fixed_only({AddOn.drafts})
    found = json.loads((await router.call(who, "find_read_tools", {"query": "ping"})).text)
    assert [i["tool"] for i in found] == ["ping"]
    assert (await read(router, who, "a", "ping")).code == "ok"
    found = json.loads((await router.call(who, "find_write_tools", {"query": "draft"})).text)
    assert [i["tool"] for i in found] == ["draft"]
    assert (await write(router, who, "a", "draft")).code == "ok"
    assert len(up.calls) == 2


async def test_fixed_only_agent_keeps_tier_and_scope_refusals(tmp_path):
    other = conn("b", {"ping": (G, True)}, scopes={Scope.personal})
    router = make(tmp_path, [conn("a", {"capture": (R, True), "draft": (Y, True)}), other])
    who = fixed_only()
    assert (await read(router, who, "a", "capture")).code == "denied:tier-red"
    assert (await write(router, who, "a", "draft")).code == "denied:addon-drafts"
    assert (await read(router, who, "b", "ping")).code == "denied:scope"
    assert (await router.call(who, "b__ping", {})).code == "denied:scope"
    assert (await router.call(who, "a__capture", {})).code == "denied:tier-red"
