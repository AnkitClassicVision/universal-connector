"""Smoke tests against the in-memory fake door. A good door passes; each bad behaviour fails.

Keys only ever come from a 0600 file the tool reads in its own process; no key is put in an environment.
"""

from __future__ import annotations

import io
import json
import os
import tempfile
from pathlib import Path

import pytest
import smoke_connection
import smoke_harness
from conftest import assert_no_leak
from fakedoor import READ_TOOLS, FakeDoor

KEY = "Qz9FAKEdrv01x"
URL = "http://127.0.0.1:8765/mcp"
_KEYDIR = Path(tempfile.mkdtemp(prefix="uc-key-"))
KEYFILE = _KEYDIR / "door.key"
KEYFILE.write_text(KEY + "\n", encoding="utf-8")
KEYFILE.chmod(0o600)
KEY_ARGS = ["--key-file", str(KEYFILE)]


def conn(door, *more, key_args=KEY_ARGS, tool="tracker__list_projects"):
    out = io.StringIO()
    code = smoke_connection.main(["--url", URL, "--connection", "tracker", "--tool", tool, "--json", *key_args, *more],
                                 transport=door, out=out)
    return code, json.loads(out.getvalue()), out.getvalue()


def harness(door, name="claude-code", url=URL, *more, key_args=KEY_ARGS):
    out = io.StringIO()
    code = smoke_harness.main(["--harness", name, "--url", url, "--json", *key_args, *more], transport=door, out=out)
    return code, json.loads(out.getvalue()), out.getvalue()


def result_of(report, check):
    return next((c["result"] for c in report["checks"] if c["check"] == check), None)


def note_of(report, check):
    return next((c["note"] for c in report["checks"] if c["check"] == check), None)


def test_connection_passes_on_a_good_door(capsys):
    code, rep, text = conn(FakeDoor())
    assert code == 0 and rep["ok"], rep
    assert result_of(rep, "signed in") == "SKIP"
    assert_no_leak(text, capsys.readouterr().err, values={KEY})


def test_connection_over_sse_replies():
    code, rep, _ = conn(FakeDoor(sse=True))
    assert code == 0, rep


@pytest.mark.parametrize("door,check", [
    (FakeDoor(keys=("other",)), "door answers"),
    (FakeDoor(results={"tracker__list_projects": {"content": [], "nextPageToken": "abc"}}), "no paging cursor in result"),
    (FakeDoor(results={"tracker__list_projects": {"content": [{"type": "text", "text": json.dumps({"items": [], "nextCursor": "p2"})}]}}),
     "no paging cursor in result"),
    (FakeDoor(results={"tracker__list_projects": {"content": [{"type": "text", "text": "x"}], "isError": True}}), "one read call"),
    (FakeDoor(tools=[{"name": "guide", "annotations": {"readOnlyHint": True}}]), "tool listed"),
])
def test_connection_fails_on_a_bad_door(door, check):
    code, rep, _ = conn(door)
    assert code == 1
    assert result_of(rep, check) == "FAIL"


def test_connection_flags_key_shapes_in_results():
    shaped = "x" + "ox" + "b-" + "1234567890-abcdefghij"  # built at run time
    code, rep, text = conn(FakeDoor(results={"tracker__list_projects": {"content": [{"type": "text", "text": shaped}]}}))
    assert code == 1 and result_of(rep, "no key-shaped text in result") == "FAIL"
    assert shaped not in text


def test_connection_read_limit():
    code, rep, _ = conn(FakeDoor(delay=0.06), "--read-timeout", "0.05")
    assert code == 1 and result_of(rep, "within read limit") == "FAIL"


def test_connection_refuses_a_tool_that_is_not_read_only_before_calling_it():
    door = FakeDoor()
    code, rep, _ = conn(door, tool="tracker__create_issue")
    assert code == 1 and result_of(rep, "read-only before calling") == "FAIL"
    assert "tools/call" not in door.calls


def test_connection_plan_tiers(tmp_path):
    plan = tmp_path / "manifest.yaml"
    plan.write_text("connections:\n  - name: tracker\n    tools:\n      - {match: 'list_*', tier: green}\n      - {match: '*', tier: red}\n")
    code, rep, _ = conn(FakeDoor(), "--plan", str(plan))
    assert result_of(rep, "plan tiers of offered tools") == "FAIL"  # the door offers tracker__create_issue, red in the plan
    door = FakeDoor(tools=[t for t in READ_TOOLS if t["name"] != "tracker__create_issue"])
    code, rep, _ = conn(door, "--plan", str(plan))
    assert code == 0 and result_of(rep, "plan tiers of offered tools") == "PASS", rep
    plan.write_text("connections:\n  - name: tracker\n    tools:\n      - {match: '*', tier: red}\n")
    code, rep, _ = conn(door, "--plan", str(plan))
    assert result_of(rep, "read-only before calling") == "FAIL"


def test_connection_missing_or_loose_key_file_fails_without_calling(tmp_path):
    door = FakeDoor()
    code, rep, _ = conn(door, key_args=["--key-file", str(tmp_path / "none")])
    assert code == 1 and result_of(rep, "key present") == "FAIL" and door.calls == []
    loose = tmp_path / "loose.key"
    loose.write_text(KEY)
    loose.chmod(0o644)
    code, rep, _ = conn(door, key_args=["--key-file", str(loose)])
    assert code == 1 and "chmod 600" in note_of(rep, "key present")


def test_smoke_tools_take_no_key_from_the_environment(monkeypatch):
    monkeypatch.setenv("DOOR_KEY", KEY)
    with pytest.raises(SystemExit):
        smoke_connection.main(["--url", URL, "--connection", "c", "--tool", "t", "--key-env", "DOOR_KEY"], transport=FakeDoor(), out=io.StringIO())


@pytest.mark.parametrize("auth,expect", [("oauth", "WARN"), ("service-account", "WARN"), ("browser-session", "FAIL")])
def test_auth_kinds_without_whoami(auth, expect):
    _, rep, _ = conn(FakeDoor(), "--auth-kind", auth)
    assert result_of(rep, "signed in") == expect


def test_whoami_prints_the_account_name_only():
    door = FakeDoor(results={"whoami": {"content": [], "structuredContent": {"email": "demo@example.com"}}})
    code, rep, text = conn(door, "--auth-kind", "oauth", "--whoami-tool", "whoami")
    assert code == 0
    assert note_of(rep, "signed in") == "signed in as demo@example.com"
    assert_no_leak(text, values={KEY})


def test_harness_passes_on_a_good_door(capsys):
    code, rep, text = harness(FakeDoor())
    assert code == 0 and rep["ok"], rep
    for check in ("no key refused", "wrong key refused", "browser Origin refused", "unlisted Host refused",
                  "GET answered with 405 or a stream", "no outputSchema", "result content is an array",
                  "initialize under 5 s", "tools/list under 5 s"):
        assert result_of(rep, check) == "PASS", check
    assert result_of(rep, "revoke") == "SKIP"
    assert_no_leak(text, capsys.readouterr().err, values={KEY})


@pytest.mark.parametrize("door,check", [
    (FakeDoor(require_key=False), "no key refused"),
    (FakeDoor(refuse_origin=False), "browser Origin refused"),
    (FakeDoor(refuse_host=False), "unlisted Host refused"),
    (FakeDoor(get_mode="json"), "GET answered with 405 or a stream"),
    (FakeDoor(tools=READ_TOOLS + [{"name": "typed", "annotations": {"readOnlyHint": True}, "outputSchema": {"type": "object"}}]), "no outputSchema"),
    (FakeDoor(results={"guide": {"content": {"type": "text", "text": "x"}}}), "result content is an array"),
])
def test_harness_fails_on_a_bad_door(door, check):
    code, rep, _ = harness(door, "claude-code", URL, "--read-tool", "guide")
    assert code == 1 and result_of(rep, check) == "FAIL", rep


def test_harness_never_calls_a_tool_that_is_not_read_only():
    tools = [{"name": "mail__search", "annotations": {"readOnlyHint": True}},
             {"name": "mail__send_message", "annotations": {}},
             {"name": "crm__delete_contact", "annotations": {"readOnlyHint": True}}]
    door = FakeDoor(tools=tools)
    code, rep, _ = harness(door, "claude-code", URL, "--read-tool", "crm__delete_contact")
    assert code == 1 and result_of(rep, "read-only before calling") == "FAIL" and door.called == []
    door = FakeDoor(tools=tools)
    code, rep, _ = harness(door)
    assert door.called == ["mail__search"]


def test_harness_plan_flags_red_tools_and_saves_and_diffs_tools(tmp_path):
    plan = tmp_path / "m.yaml"
    plan.write_text("connections:\n  - name: tracker\n    tools:\n      - {match: 'list_*', tier: green}\n      - {match: '*', tier: red}\n")
    code, rep, _ = harness(FakeDoor(), "claude-code", URL, "--plan", str(plan))
    assert result_of(rep, "plan tiers of offered tools") == "FAIL"
    saved = tmp_path / "tools.json"
    code, rep, _ = harness(FakeDoor(tools=READ_TOOLS[:3]), "claude-code", URL, "--save-tools", str(saved))
    assert json.loads(saved.read_text())[0] == {"name": "tracker__list_projects", "annotations": {"readOnlyHint": True}}
    assert saved.stat().st_mode & 0o077 == 0
    code, rep, _ = harness(FakeDoor(), "claude-code", URL, "--baseline-tools", str(saved))
    assert result_of(rep, "no new tools that change things") == "FAIL" and "tracker__create_issue" in note_of(rep, "no new tools that change things")


def test_revoked_key_check():
    code, rep, _ = harness(FakeDoor(revoked=(KEY,)), "claude-code", URL, "--expect-revoked")
    assert code == 0 and result_of(rep, "revoked key refused") == "PASS"
    code, rep, _ = harness(FakeDoor(), "claude-code", URL, "--expect-revoked")
    assert code == 1


def test_oddboro_needs_https_short_names_one_page_and_read_hints():
    code, rep, _ = harness(FakeDoor(), "oddboro", URL, "--oddboro-version", "v0.0.12")
    assert result_of(rep, "https address") == "FAIL"
    tailnet = "https://door.tailnet-name.ts.net/mcp"
    code, rep, _ = harness(FakeDoor(), "oddboro", tailnet, "--oddboro-version", "v0.0.12")
    assert code == 0, rep
    assert result_of(rep, "route Host accepted") == "PASS"
    code, rep, _ = harness(FakeDoor(page_size=2), "oddboro", tailnet, "--oddboro-version", "v0.0.12")
    assert result_of(rep, "all tools on the first page") == "FAIL"
    code, rep, _ = harness(FakeDoor(page_size=2), "codex", URL)
    assert result_of(rep, "all tools on the first page") == "WARN"
    code, rep, _ = harness(FakeDoor(), "oddboro", tailnet, "--oddboro-version", "v0.0.12", "--read-tool", "tracker__create_issue")
    assert result_of(rep, "read-only before calling") == "FAIL"


def test_oddboro_service_id_comes_from_the_address():
    host = "a-very-long-workstation-name-for-the-office.tailnet-name.ts.net"
    tools = [{"name": "tracker__list_projects_for_workspace", "annotations": {"readOnlyHint": True}},
             {"name": "mail__search", "annotations": {"readOnlyHint": True, "destructiveHint": False}}]
    code, rep, _ = harness(FakeDoor(hosts=(host,), tools=tools), "oddboro", f"https://{host}/mcp", "--oddboro-version", "v0.0.12")
    assert result_of(rep, "tool names within limit") == "FAIL"
    assert "mcp__a-very-long-workstation-name-for-the-office-tailnet-name-ts-net-mcp__" in note_of(rep, "tool names within limit")
    assert result_of(rep, "Read only grant reaches tools") == "PASS" and "2 of 2" in note_of(rep, "Read only grant reaches tools")


def test_oddboro_with_no_version_fails_with_update_advice():
    code, rep, _ = harness(FakeDoor(), "oddboro", "https://door.tailnet-name.ts.net/mcp")
    assert code == 1 and result_of(rep, "Oddboro version") == "FAIL" and "update" in note_of(rep, "Oddboro version").lower()


def test_bad_args_json_is_refused():
    out = io.StringIO()
    assert smoke_connection.main(["--url", URL, "--connection", "c", "--tool", "t", "--args", "[1]", *KEY_ARGS],
                                 transport=FakeDoor(), out=out) == 2


def test_real_transport_ignores_proxy_settings(monkeypatch):
    import urllib.request

    from kit import mcp_client
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:9")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9")
    def proxied(op):
        return [h for h in op.handlers if isinstance(h, urllib.request.ProxyHandler) and h.proxies]

    assert proxied(urllib.request.build_opener()), "control: a default opener would use the proxy"
    opener = mcp_client.make_opener()
    assert proxied(opener) == []
    assert not any(isinstance(h, urllib.request.HTTPRedirectHandler) and not isinstance(h, mcp_client._NoRedirect) for h in opener.handlers)


def test_key_file_is_not_followed_through_a_link(tmp_path):
    link = tmp_path / "link.key"
    os.symlink(KEYFILE, link)
    code, rep, _ = conn(FakeDoor(), key_args=["--key-file", str(link)])
    assert code == 1 and result_of(rep, "key present") == "FAIL"
