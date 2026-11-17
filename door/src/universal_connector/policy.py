"""Policy: may this agent call this tool on this connection? First failing rule wins."""

from __future__ import annotations

from dataclasses import dataclass

from universal_connector.models import AddOn, AgentGrant, Connection, Reach, Scope, Tier


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str
    tier: Tier | None


def _connection_refusal(agent: AgentGrant, conn: Connection) -> str | None:
    """Rules 1 to 5. Return the reason for the first failing rule, or None."""
    if not agent.enabled:
        return "agent-disabled"
    if Scope.restricted in conn.scopes:
        return "restricted-closed"
    if not conn.scopes or not agent.scopes or not conn.scopes <= agent.scopes:
        return "scope"
    if conn.kind == "browser" and AddOn.browser not in agent.addons:
        return "addon-browser"
    if conn.kind == "computer" and AddOn.computer not in agent.addons:
        return "addon-computer"
    if conn.reach == Reach.full_read and agent.reach == Reach.starter:
        return "reach"
    return None


def connection_visible(agent: AgentGrant, conn: Connection) -> bool:
    """True when rules 1 to 5 pass."""
    return _connection_refusal(agent, conn) is None


def decide(agent: AgentGrant, conn: Connection, tool_name: str) -> Decision:
    tool = next((t for t in conn.tools if t.name == tool_name), None)
    tier = tool.tier if tool is not None else None
    refusal = _connection_refusal(agent, conn)
    if refusal is not None:
        return Decision(False, refusal, tier)
    if tool is None:
        return Decision(False, "unlisted", None)
    if tool.tier == Tier.black:
        return Decision(False, "tier-black", tier)
    if tool.tier == Tier.red:
        return Decision(False, "tier-red", tier)
    if tool.tier == Tier.yellow and AddOn.drafts not in agent.addons:
        return Decision(False, "addon-drafts", tier)
    return Decision(True, "ok", tier)
