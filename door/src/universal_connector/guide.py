"""The one instruction text every agent receives. Built from the manifest, 60 lines at most."""

from __future__ import annotations

from universal_connector.models import AgentGrant, Manifest, Tier
from universal_connector.policy import connection_visible, decide

MAX_LINES = 60
MAX_CONNECTION_LINES = 25

_HEAD = [
    "This connector gives you the owner's connections through one door.",
    "Every call is logged. The owner can pause or revoke you at any time.",
    "",
    "## Tiers",
    "- green: read only. Find a tool with find_read_tools, then run it with call_read_tool.",
    "- yellow: prepares drafts only. Needs the drafts add-on. Use find_write_tools and",
    "  call_write_tool. Nothing is sent: the owner sends every draft.",
    "- red and black: not available to agents. Prepare a draft for the owner instead.",
    "",
    "## Tools",
    "- connector_guide: this text.",
    "- find_read_tools(query): list green tools that match every word of the query.",
    "- call_read_tool(connection, tool, arguments): run a green tool.",
    "- find_write_tools(query): list yellow tools that match every word of the query.",
    "- call_write_tool(connection, tool, arguments): run a yellow tool.",
    "- <connection>__<tool>: a pinned tool, called by its own name.",
    "",
    "## Connections you can reach",
]

_TAIL = [
    "",
    "## More reach",
    "You cannot change your own scope, reach or add-ons. Ask the owner to widen them.",
]


def render_guide(manifest: Manifest, agent: AgentGrant) -> str:
    lines = [f"# Connector guide for {agent.name}", *_HEAD]
    shown = 0
    hidden = 0
    for conn in manifest.connections:
        if not connection_visible(agent, conn):
            continue
        green = yellow = 0
        for spec in conn.tools:
            decision = decide(agent, conn, spec.name)
            if not decision.allowed:
                continue
            if decision.tier == Tier.green:
                green += 1
            elif decision.tier == Tier.yellow:
                yellow += 1
        if shown >= MAX_CONNECTION_LINES:
            hidden += 1
            continue
        line = f"- {conn.name}: {green} read tool(s)"
        if yellow:
            line += f", {yellow} draft tool(s)"
        lines.append(line)
        shown += 1
    if shown == 0:
        lines.append("- none")
    if hidden:
        lines.append(f"- and {hidden} more. Use find_read_tools to search.")
    lines.extend(_TAIL)
    return "\n".join(lines[:MAX_LINES])
