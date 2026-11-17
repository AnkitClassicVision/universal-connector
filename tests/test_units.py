"""Unit tests: classifier, redactor, key-shape rules, gotchas, entry rendering, inventory diff."""

from __future__ import annotations

import json
import tomllib

import diff_inventory
import pytest
import yaml
from kit.classify import classify_entry
from kit.gotchas import cursor_paths, host_allowed, long_names, read_limit_ok, read_only_reachable
from kit.harnesses import HARNESSES, entry
from kit.keyshape import is_key_shaped, rule_hits
from kit.plugins.skills import classify as skill_class
from kit.redact import Redactor


def where(e):
    return classify_entry(e, Redactor())["key_where"]


@pytest.mark.parametrize("entry_,expect", [
    ({"url": "https://a.example.com/mcp", "headers": {"Authorization": "Bearer short1"}}, ["inline"]),
    ({"url": "https://a.example.com/mcp", "headers": {"Authorization": "Bearer ${TOKEN}"}}, ["env-reference"]),
    ({"url": "https://a.example.com/mcp", "headers": {"Authorization": "Bearer ${input:k}"}}, ["prompt"]),
    ({"url": "https://a.example.com/mcp", "headers": {"Accept": "application/json"}}, ["no-credential-found"]),
    ({"command": "tool", "env": {"LOG_LEVEL": "debug", "NODE_ENV": "production"}}, ["none"]),
    ({"command": "tool", "env": {"GOOGLE_APPLICATION_CREDENTIALS": "/keys/sa.json"}}, ["file"]),
    ({"command": "op", "args": ["run", "--", "x"]}, ["vault"]),
    ({"command": "npx", "args": ["mcp-remote", "https://a.example.com/mcp"]}, ["oauth"]),
    ({"command": "security", "args": ["find-generic-password", "-s", "x"]}, ["keyring"]),
    ({"command": "x", "args": ["--token=abc123"]}, ["inline"]),
    ({"command": "x", "args": ["--key-file", "~/.keys/k"]}, ["file"]),
    ({"url": "https://u:pw@a.example.com/mcp"}, ["inline"]),
    ({"type": "stdio", "command": "x", "env_keys": ["K"]}, ["keyring"]),
    ({"url": "https://a.example.com", "bearer_token_env_var": "K"}, ["env-reference"]),
    ({"url": "https://a.example.com", "auth": "oauth"}, ["oauth"]),
    # Any literal directly under env or headers is an inline secret unless it is plainly a setting.
    ({"command": "tool", "env": {"SERVICE_X": "abc123short"}}, ["inline"]),
    ({"command": "tool", "env": {"API_BASE": "https://api.example.com/v1", "DATA_DIR": "/srv/data"}}, ["none"]),
    ({"url": "https://a.example.com/mcp", "headers": {"X-Workspace": "acme"}}, ["inline"]),
    ({"command": "tool", "env": {"SMTP_PASS": "x"}}, ["inline"]),
    ({"command": "tool", "env": {"DB_PW": "secretish"}}, ["inline"]),
])
def test_classify_entry(entry_, expect):
    assert where(entry_) == expect


def test_classify_never_returns_values():
    secret = "plain-value-zz9"
    c = classify_entry({"url": f"https://a.example.com/mcp?token={secret}", "headers": {"X-Api-Key": secret},
                        "env": {"API_TOKEN": secret}, "args": ["--token", secret]}, Redactor())
    assert secret not in json.dumps(c)


def test_redactor_hides_key_shapes_and_keeps_names():
    r = Redactor()
    shaped = "AK" + "IA" + "B" * 16
    assert r.name("tracker") == "tracker"
    assert r.name("Work/GitHub read token") == "Work/GitHub read token"
    assert r.name(shaped).startswith("[hidden-")
    assert r.host("https://user:pw@api.example.com:8443/path?q=1") == "https://api.example.com:8443"
    assert r.host("https://" + "a1B2c3D4e5F6g7H8i9J0k" + ".example.com").startswith("[hidden-")
    assert r.name("1234567890" + "12-admin").startswith("[hidden-")  # an account-id shape, built at run time
    assert r.text("Use " + shaped + " here").startswith("[description hidden")


def test_key_shape_rules_hit_and_miss():
    assert rule_hits("gh" + "p_" + "a" * 36) == ["github-token"]
    assert is_key_shaped("token = " + "Ab1" * 10)
    assert not is_key_shaped("token = work/github/read-token")  # a vault entry name
    assert not is_key_shaped("Authorization: Bearer ${DOOR_KEY}")
    assert not is_key_shaped("https://demo:Qz9FAKE$x@host.example.com")


def test_skill_classes():
    assert skill_class({"name": "a", "description": "Summarise notes"}, False)[0] == "portable-instructions"
    assert skill_class({"name": "a", "description": "Query the Stripe API"}, True)[0] == "external-api"
    assert skill_class({"name": "a", "description": "x", "metadata": {"requires": {"env": ["X_API_KEY"]}}}, False)[0] == "external-api"
    assert skill_class({"name": "a", "description": "Edit Claude Code hooks"}, False)[0] == "harness-specific"


def test_gotchas():
    assert long_names("oddboro", "door", ["t"]) == []
    assert long_names("oddboro", "x" * 40, ["list_everything_in_the_world"])
    assert cursor_paths({"a": [{"nextPageToken": "x"}]}) == ["$.a[0].nextPageToken"]
    assert cursor_paths({"nextCursor": None}) == []
    assert read_limit_ok(1, 5) and not read_limit_ok(4.5, 5)
    assert host_allowed("Door.Example.com", ["door.example.com"]) and not host_allowed("x", [])

# Oddboro's own rule (packages/ledger/src/read-only.ts): readOnlyHint === true, destructiveHint !== true,
# and no change word among the name's words, split on camelCase and on any non-alphanumeric run.
@pytest.mark.parametrize("tool,reached", [
    ({"name": "list_items", "annotations": {"readOnlyHint": True}}, True),
    ({"name": "get", "annotations": {"readOnlyHint": True, "destructiveHint": False}}, True),
    ({"name": "get", "annotations": {"readOnlyHint": True, "destructiveHint": True}}, False),
    ({"name": "get"}, False),
    ({"name": "get", "annotations": {"readOnlyHint": "true"}}, False),
    ({"name": "delete_item", "annotations": {"readOnlyHint": True}}, False),
    ({"name": "createIssue", "annotations": {"readOnlyHint": True}}, False),
    ({"name": "multica.create-issue", "annotations": {"readOnlyHint": True}}, False),
    ({"name": "get_post", "annotations": {"readOnlyHint": True}}, False),
    ({"name": "runReport", "annotations": {"readOnlyHint": True}}, False),
    ({"name": "list_runs", "annotations": {"readOnlyHint": True}}, True),
    ({"name": "searchMessages", "annotations": {"readOnlyHint": True}}, True),
    ({"name": "storeFront_list", "annotations": {"readOnlyHint": True}}, False),
])
def test_read_only_rule_matches_oddboro(tool, reached):
    assert read_only_reachable(tool)[0] is reached


def test_change_words_are_oddboros_42():
    from kit.gotchas import CHANGES
    assert len(CHANGES) == 42 and {"add", "write", "upsert", "store", "run", "clear", "capture"} <= CHANGES


@pytest.mark.parametrize("hid", sorted(HARNESSES))
def test_entry_never_holds_a_key_and_parses(hid):
    text = entry(hid, url="https://door.example.com/mcp", key_env="DOOR_KEY")
    assert not rule_hits(text)
    body = text.split("\n\n#")[0]
    if body.lstrip().startswith("{"):
        json.loads(body.split("\n#")[0])
    if hid == "codex":
        assert tomllib.loads(text)["mcp_servers"]["door"]["bearer_token_env_var"] == "DOOR_KEY"
    if hid in ("goose", "hermes"):
        assert isinstance(yaml.safe_load(text), dict)


def _inv(findings, skills=()):
    return {"schema": "universal-connector/inventory@1", "findings": findings, "skills": list(skills),
            "sources": [{"id": "codex", "status": "found"}]}


def test_diff_inventory():
    a = {"id": "codex|x|mcp-server|db", "name": "db", "source": "codex", "kind": "mcp-server", "key_where": ["inline"],
         "auth_kind": "api-key", "transport": "stdio", "host": None, "plain_file": True, "key_fields": []}
    b = dict(a, key_where=["vault"], plain_file=False)
    c = dict(a, id="codex|x|mcp-server|new", name="new")
    d = diff_inventory.diff(_inv([a]), _inv([b, c]))
    assert [x["name"] for x in d["added"]] == ["new"]
    assert d["changed"][0]["changes"]["key_where"] == {"was": ["inline"], "now": ["vault"]}
    assert "added 1, removed 0, changed 1" in diff_inventory.text(d)
