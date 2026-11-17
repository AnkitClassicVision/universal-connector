import pytest
from pydantic import ValidationError

from universal_connector.models import AgentGrant, Auth, Connection, ToolSpec
from universal_connector.policy import connection_visible, decide


def conn(**kw):
    base = {"name": "c", "kind": "mcp-remote", "auth": Auth(type="none"), "scopes": {"work"},
                "reach": "starter", "tools": [ToolSpec(name="read", tier="green"),
                ToolSpec(name="draft", tier="yellow"), ToolSpec(name="send", tier="red"),
                ToolSpec(name="dump", tier="black")]}
    base.update(kw)
    return Connection(**base)

def agent(**kw):
    base = {"name": "a", "scopes": {"work"}, "reach": "starter"}
    base.update(kw)
    return AgentGrant(**base)

CASES = [
    (agent(), conn(), "read", True, "ok"),
    (agent(enabled=False), conn(), "read", False, "agent-disabled"),
    (agent(scopes={"work", "personal"}), conn(scopes={"work", "restricted"}), "read", False,
     "restricted-closed"),
    (agent(), conn(scopes={"personal"}), "read", False, "scope"),
    (agent(), conn(scopes={"work", "personal"}), "read", False, "scope"),
    (agent(), conn(kind="browser"), "read", False, "addon-browser"),
    (agent(), conn(kind="computer"), "read", False, "addon-computer"),
    (agent(), conn(reach="full-read"), "read", False, "reach"),
    (agent(reach="full-read"), conn(reach="full-read"), "read", True, "ok"),
    (agent(), conn(), "nope", False, "unlisted"),
    (agent(), conn(), "dump", False, "tier-black"),
    (agent(), conn(), "send", False, "tier-red"),
    (agent(addons={"drafts"}), conn(), "send", False, "tier-red"),
    (agent(), conn(), "draft", False, "addon-drafts"),
    (agent(addons={"drafts"}), conn(), "draft", True, "ok"),
    (agent(enabled=False), conn(reach="full-read"), "read", False, "agent-disabled"),
    (agent(enabled=False, scopes={"work", "personal"}), conn(scopes={"work", "restricted"}), "read",
     False, "agent-disabled"),
    (agent(), conn(kind="browser", scopes={"personal"}), "read", False, "scope"),
    (agent(), conn(kind="browser", reach="full-read"), "read", False, "addon-browser"),
    (agent(), conn(reach="full-read"), "nope", False, "reach"),
    (agent(), conn(scopes={"personal"}), "nope", False, "scope"),
    (agent(), conn(kind="computer", scopes={"personal"}), "read", False, "scope"),
    (agent(), conn(kind="computer", reach="full-read"), "read", False, "addon-computer"),
    (agent(scopes={"work", "personal"}), conn(kind="computer", scopes={"work", "restricted"}),
     "read", False, "restricted-closed"),
]

@pytest.mark.parametrize("a,c,tool,allowed,reason", CASES)
def test_decide(a, c, tool, allowed, reason):
    d = decide(a, c, tool)
    assert (d.allowed, d.reason) == (allowed, reason)

def test_visibility_follows_rules_one_to_five():
    assert connection_visible(agent(), conn()) is True
    assert connection_visible(agent(), conn(scopes={"personal"})) is False
    assert connection_visible(agent(), conn(reach="full-read")) is False


def test_empty_scopes_rejected_by_model():
    with pytest.raises(ValidationError):
        conn(scopes=set())
    with pytest.raises(ValidationError):
        agent(scopes=set())


def test_decide_fails_closed_on_empty_scopes():
    base_conn, base_agent = conn(), agent()
    empty_conn = Connection.model_construct(**{**dict(base_conn), "scopes": set()})
    empty_agent = AgentGrant.model_construct(**{**dict(base_agent), "scopes": set()})
    for a, c in ((agent(), empty_conn), (empty_agent, conn()), (empty_agent, empty_conn)):
        d = decide(a, c, "read")
        assert (d.allowed, d.reason) == (False, "scope")
