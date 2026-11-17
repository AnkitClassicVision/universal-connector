"""Oddboro: service id, address rules, connect defaults, the name and call budgets, tool shape."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest
import yaml

from helpers.door import copy_examples, fake_builder, in_process, memory_store
from universal_connector import adapters, keys
from universal_connector.cli import main
from universal_connector.frontdoor import Holder, build_app
from universal_connector.models import (
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
    Router,
    name_words,
    oddboro_reads_only,
)
from universal_connector.upstreams.base import UpstreamError

# Oddboro's 42 change words, word for word.
PORTED_CHANGES = {
    "add", "append", "approve", "archive", "assign", "cancel", "capture", "clear", "close",
    "comment", "create", "delete", "destroy", "drop", "edit", "exec", "execute", "forward",
    "insert", "invite", "merge", "modify", "move", "patch", "post", "publish", "put", "remove",
    "rename", "reply", "reset", "run", "save", "send", "set", "share", "store", "submit",
    "update", "upload", "upsert", "write",
}  # fmt: skip

TAILNET_URL = "https://door.tailnet-name.ts.net:8449/mcp"


# -- the service id Oddboro gives a server named by its address ----------------------------------


@pytest.mark.parametrize(
    ("url", "service_id"),
    [
        (TAILNET_URL, "door-tailnet-name-ts-net-mcp"),  # the port is not part of it
        ("https://door.tailnet-name.ts.net/mcp", "door-tailnet-name-ts-net-mcp"),
        ("https://Door.Example.invalid/MCP/", "door-example-invalid-mcp"),  # lower case, trimmed
        ("https://door.localhost:8443", "door-localhost"),  # no path: "/" is trimmed away
        ("https://a.example.invalid/mcp?x=1#y", "a-example-invalid-mcp"),  # no query
        ("https://io.github.acme.example.invalid/x", "acme-example-invalid-x"),
        ("https://a.example.invalid//one__two..three/", "a-example-invalid-one-two-three"),
        ("https://127.0.0.1:8443/mcp", "127-0-0-1-mcp"),
    ],
)
def test_service_id_matches_oddboro(url, service_id):
    assert adapters.address_problem(url, "oddboro") is None
    assert adapters.oddboro_service_id(url) == service_id


@pytest.mark.parametrize(
    ("url", "problem"),
    [
        ("http://door.localhost/mcp", adapters.ODDBORO_HTTPS),
        ("https://[::1]:8443/mcp", adapters.ODDBORO_HOST),  # Oddboro rewrites IPv6 spellings
        ("https://0x7f.1/mcp", adapters.ODDBORO_HOST),  # and short IPv4 forms
        ("https://127.1/mcp", adapters.ODDBORO_HOST),
        ("https://door.ex%41mple.invalid/mcp", adapters.ODDBORO_HOST),
        ("https://dóor.example.invalid/mcp", adapters.ODDBORO_HOST),
        ("https://door.localhost/a/../mcp", adapters.ODDBORO_PATH),  # dot steps are resolved
        ("https://door.localhost/./mcp", adapters.ODDBORO_PATH),
        ("https://door.localhost/m%63p", adapters.ODDBORO_PATH),
        ("https://door.localhost/m{c}p", adapters.ODDBORO_PATH),
    ],
)
def test_addresses_oddboro_would_rewrite_are_refused(url, problem):
    assert adapters.address_problem(url, "oddboro") == problem


def test_longest_name_counts_the_full_oddboro_name():
    names = ["connector_guide", "find_write_tools"]
    assert adapters.oddboro_longest_name(TAILNET_URL, names) == len(
        "mcp__door-tailnet-name-ts-net-mcp__find_write_tools"
    )


# -- Oddboro's read-only rule, ported ------------------------------------------------------------


def test_change_words_are_oddboros_42():
    assert set(ODDBORO_CHANGE_WORDS) == PORTED_CHANGES
    assert len(PORTED_CHANGES) == 42


@pytest.mark.parametrize(
    ("name", "words"),
    [
        ("multica_create_issue", ["multica", "create", "issue"]),
        ("createIssue", ["create", "issue"]),
        ("create-issue", ["create", "issue"]),
        ("messages.send", ["messages", "send"]),
        ("getHTTPStatus", ["get", "httpstatus"]),
        ("a2B", ["a2", "b"]),
        ("__x__", ["x"]),
    ],
)
def test_name_words_split_like_oddboro(name, words):
    assert name_words(name) == words


def test_reads_only_needs_both_marks_and_no_change_word():
    read = {"readOnlyHint": True, "destructiveHint": False}
    assert oddboro_reads_only("search_notes", read)
    assert oddboro_reads_only("search_notes", {"readOnlyHint": True})  # not destructive: fine
    assert not oddboro_reads_only("search_notes", {"readOnlyHint": True, "destructiveHint": True})
    assert not oddboro_reads_only("search_notes", {"readOnlyHint": 1})  # exactly true only
    assert not oddboro_reads_only("search_notes", {})
    assert not oddboro_reads_only("search_notes", None)
    assert not oddboro_reads_only("get_post", read)  # the rule errs toward less
    assert not oddboro_reads_only("sendMail", read)


def _oddboro_agents() -> list[dict]:
    agents = []
    for pinned in (False, True):
        for reach in ("starter", "full-read"):
            for addons in ([], ["drafts"]):
                agents.append({
                    "name": f"odd-{'p' if pinned else 'f'}-{reach}-{len(addons)}",
                    "scopes": ["work"], "reach": reach, "addons": addons,
                    "pinned_tools": pinned, "call_timeout_s": 40,
                })  # fmt: skip
    return agents


async def test_every_tool_an_oddboro_agent_can_see_passes_the_ported_rule(tmp_path):
    manifest = copy_examples(tmp_path)
    agents = _oddboro_agents()
    (manifest / "agents.yaml").write_text(yaml.safe_dump({"version": 1, "agents": agents}))
    state = tmp_path / "state"
    holder = Holder(manifest, state, memory_store(), fake_builder)
    minted = {a["name"]: keys.mint(state, a["name"]) for a in agents}
    app = build_app(holder, state, door_hosts=["door.localhost"])
    app.state.set_port(8765)
    seen: set[str] = set()
    async with in_process(app) as http:
        for name, key in minted.items():
            reply = await http.post(
                "/mcp",
                json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
                headers={
                    "Authorization": f"Bearer {key}",
                    "Accept": "application/json, text/event-stream",
                    "mcp-protocol-version": "2025-11-25",
                },
            )
            assert reply.status_code == 200, name
            result = reply.json()["result"]
            assert "nextCursor" not in result  # one page
            for tool in result["tools"]:
                seen.add(tool["name"])
                marks = tool.get("annotations") or {}
                assert "outputSchema" not in tool
                assert adapters.SNAKE_CASE.fullmatch(tool["name"]), tool["name"]
                if marks.get("readOnlyHint") is True:
                    assert marks.get("destructiveHint") is False, tool["name"]
                    assert oddboro_reads_only(tool["name"], marks), tool["name"]
                else:  # a tool the door does not call a read never reads as one in Oddboro
                    assert not oddboro_reads_only(tool["name"], marks), tool["name"]
    fixed = {"connector_guide", "find_read_tools", "call_read_tool", "find_write_tools",
             "call_write_tool"}  # fmt: skip
    pinned = {"notes__search_notes", "google_mail_work__gmail_search",
              "google_calendar_work__calendar_list_events"}  # fmt: skip
    assert seen == fixed | pinned  # the walk really covered every tool the door can show


# -- connect --format oddboro ------------------------------------------------------------------


def _connect(tmp_path: Path, manifest: Path, url: str, *extra: str, name: str = "odd") -> int:
    key_file = tmp_path / f"{name}.cred"
    return main([
        "connect", name, "--manifest", str(manifest), "--state", str(tmp_path / "state"),
        "--reach", "full-read", "--scopes", "work", "--format", "oddboro", "--url", url,
        "--key-file", str(key_file), *extra,
    ])  # fmt: skip


def _agent(manifest: Path, name: str = "odd") -> dict:
    data = yaml.safe_load((manifest / "agents.yaml").read_text())
    return next(a for a in data["agents"] if a["name"] == name)


def test_oddboro_connect_defaults_to_fixed_tools_and_a_40_second_budget(tmp_path, capsys):
    manifest = copy_examples(tmp_path)
    assert _connect(tmp_path, manifest, TAILNET_URL) == 0
    agent = _agent(manifest)
    assert agent["pinned_tools"] is False
    assert agent["call_timeout_s"] == 40
    out = capsys.readouterr()
    assert "Header value: Bearer <key in file>" in out.out
    assert "warning" not in out.err


def test_oddboro_pinned_flag_shows_pinned_tools(tmp_path, capsys):
    manifest = copy_examples(tmp_path)
    assert _connect(tmp_path, manifest, "https://d.localhost/mcp", "--pinned") == 0
    agent = _agent(manifest)
    assert "pinned_tools" not in agent  # the default, true, is not written
    assert agent["call_timeout_s"] == 40
    # 5 + 15 + 2 + 42 = 64: at the limit, so allowed, with the margin warning.
    assert capsys.readouterr().err.startswith(
        "warning: Oddboro would name a tool with 64 characters; past 57"
    )


def test_generic_connect_keeps_pinned_tools_and_no_budget(tmp_path, capsys):
    manifest = copy_examples(tmp_path)
    code = main([
        "connect", "gen", "--manifest", str(manifest), "--state", str(tmp_path / "state"),
        "--reach", "starter", "--scopes", "work", "--key-file", str(tmp_path / "gen.cred"),
    ])  # fmt: skip
    assert code == 0
    agent = _agent(manifest, "gen")
    assert "pinned_tools" not in agent and "call_timeout_s" not in agent


def _unchanged(tmp_path: Path, manifest: Path, before: bytes) -> None:
    assert (manifest / "agents.yaml").read_bytes() == before
    assert not (tmp_path / "odd.cred").exists()
    state = tmp_path / "state"
    assert not (state / "state.db").exists() or not keys.has_active_key(state, "odd")


@pytest.mark.parametrize(
    ("url", "extra", "length"),
    [
        (TAILNET_URL, ("--pinned",), 77),  # 5 + 28 + 2 + 42
        ("https://abcdefghijklmnopqr.tailnet-name.ts.net/mcp", (), 65),  # fixed only: 5 + 42 + 18
    ],
)
def test_too_long_a_name_is_refused_with_the_computed_length(tmp_path, capsys, url, extra, length):
    manifest = copy_examples(tmp_path)
    before = (manifest / "agents.yaml").read_bytes()
    assert _connect(tmp_path, manifest, url, *extra) == 2
    err = capsys.readouterr().err
    assert err == (
        f"refused: Oddboro would name a tool with {length} characters, over its limit of 64; "
        "use a shorter address, or fixed tools only; nothing was changed\n"
    )
    assert "tailnet-name" not in err  # the address is never echoed
    _unchanged(tmp_path, manifest, before)


def test_name_past_57_warns_but_connects(tmp_path, capsys):
    manifest = copy_examples(tmp_path)
    url = "https://abcdefghijklm.tailnet-name.ts.net/mcp"  # 5 + 37 + 2 + 16 = 60
    assert _connect(tmp_path, manifest, url) == 0
    assert "warning: Oddboro would name a tool with 60 characters" in capsys.readouterr().err


def test_a_pinned_name_that_is_not_snake_case_is_refused(tmp_path, capsys):
    manifest = copy_examples(tmp_path)
    data = yaml.safe_load((manifest / "connector.yaml").read_text())
    data["connections"][0]["tools"].append({"name": "getNote", "tier": "green", "pinned": True})
    (manifest / "connector.yaml").write_text(yaml.safe_dump(data))
    before = (manifest / "agents.yaml").read_bytes()
    assert _connect(tmp_path, manifest, "https://d.localhost/mcp", "--pinned") == 2
    assert capsys.readouterr().err == adapters.ODDBORO_NOT_SNAKE + "\n"
    _unchanged(tmp_path, manifest, before)
    assert _connect(tmp_path, manifest, "https://d.localhost/mcp") == 0  # fixed only is fine


def test_pinned_and_fixed_only_flags_exclude_each_other(tmp_path, capsys):
    manifest = copy_examples(tmp_path)
    with pytest.raises(SystemExit):
        _connect(tmp_path, manifest, TAILNET_URL, "--pinned", "--fixed-tools-only")
    capsys.readouterr()


# -- the call budget ---------------------------------------------------------------------------


class SlowThenFast:
    def __init__(self, first: str, sleep_s: float = 0.0) -> None:
        self.first, self.sleep_s, self.calls = first, sleep_s, 0

    async def call_tool(self, name: str, arguments: dict) -> str:
        self.calls += 1
        if self.calls == 1 and self.first == "slow":
            await asyncio.sleep(self.sleep_s)
        if self.calls == 1 and self.first == "error":
            raise UpstreamError("transport")
        return "fine"

    def secret_values(self) -> list[str]:
        return []


def _router(tmp_path: Path, upstream) -> Router:
    conn = Connection(
        name="c", kind="mcp-remote", upstream="https://c.example.invalid/mcp",
        auth=Auth(type="none"), scopes={Scope.work}, reach=Reach.starter,
        tools=[ToolSpec(name="look", tier=Tier.green, pinned=True, timeout_s=60)],
    )  # fmt: skip
    return Router(Manifest(version=1, connections=[conn], agents=[]), {"c": upstream}, tmp_path / "s")


def _grant(budget: int | None) -> AgentGrant:
    return AgentGrant(name="odd", scopes={Scope.work}, reach=Reach.starter, call_timeout_s=budget)


async def test_budget_caps_the_whole_call_and_stops_the_retry(tmp_path):
    slow = SlowThenFast("slow", sleep_s=5)
    router = _router(tmp_path, slow)
    start = time.monotonic()
    result = await router.call(_grant(1), "c__look", {})
    took = time.monotonic() - start
    assert result.code == "timeout"
    assert slow.calls == 1  # no time left, so no retry
    assert took < 2.5


async def test_a_fast_failure_still_retries_inside_the_budget(tmp_path):
    flaky = SlowThenFast("error")
    result = await _router(tmp_path, flaky).call(_grant(40), "c__look", {})
    assert (result.ok, result.text, flaky.calls) == (True, "fine", 2)


async def test_without_a_budget_the_tool_timeout_rules(tmp_path):
    flaky = SlowThenFast("error")
    result = await _router(tmp_path, flaky).call(_grant(None), "c__look", {})
    assert result.ok and flaky.calls == 2
