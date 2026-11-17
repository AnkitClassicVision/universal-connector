from __future__ import annotations

from universal_connector.guide import render_guide
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


def conn(name: str, scopes: set[Scope], tools: dict[str, Tier]) -> Connection:
    return Connection(
        name=name,
        kind="mcp-remote",
        upstream="https://up.example.invalid/mcp",
        auth=Auth(type="none"),
        scopes=scopes,
        reach=Reach.starter,
        tools=[ToolSpec(name=t, tier=tier) for t, tier in tools.items()],
    )


WORK = AgentGrant(name="alpha", scopes={Scope.work}, reach=Reach.full_read)
DRAFTS = AgentGrant(
    name="alpha", scopes={Scope.work}, reach=Reach.full_read, addons={AddOn.drafts}
)


def test_guide_lists_only_visible_connections():
    manifest = Manifest(
        version=1,
        connections=[
            conn("shown", {Scope.work}, {"a": Tier.green, "b": Tier.green, "d": Tier.yellow}),
            conn("private_one", {Scope.personal}, {"a": Tier.green}),
            conn("closed", {Scope.restricted}, {"a": Tier.green}),
        ],
        agents=[WORK],
    )
    text = render_guide(manifest, WORK)
    assert "- shown: 2 read tool(s)\n" in text + "\n"
    assert "private_one" not in text and "closed" not in text
    assert "draft tool(s)" not in text  # no drafts add-on, so the yellow tool is not offered
    assert "- shown: 2 read tool(s), 1 draft tool(s)" in render_guide(manifest, DRAFTS)
    for name in ("find_read_tools", "call_read_tool", "find_write_tools", "call_write_tool"):
        assert name in text


def test_guide_with_no_connection_says_none():
    manifest = Manifest(
        version=1, connections=[conn("mine", {Scope.personal}, {"a": Tier.green})], agents=[WORK]
    )
    assert "- none" in render_guide(manifest, WORK)


def test_guide_under_60_lines():
    few = Manifest(version=1, connections=[conn("one", {Scope.work}, {"a": Tier.green})], agents=[])
    assert len(render_guide(few, WORK).splitlines()) <= 60
    many = Manifest(
        version=1,
        connections=[conn(f"c{i}", {Scope.work}, {"a": Tier.green}) for i in range(200)],
        agents=[],
    )
    text = render_guide(many, WORK)
    assert len(text.splitlines()) <= 60
    assert "and 175 more" in text
