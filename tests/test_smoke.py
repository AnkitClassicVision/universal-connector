"""Smoke tests against the in-memory fake door. A good door passes; each bad behaviour fails."""

from __future__ import annotations

import io
import json

import pytest
import smoke_connection
import smoke_harness
from conftest import assert_no_leak
from fakedoor import FakeDoor

KEY = "Qz9FAKEdrv01x"
URL = "http://127.0.0.1:8765/mcp"
ENV = {"DOOR_KEY": KEY}


def conn(door, *more, env=ENV):
    out = io.StringIO()
    code = smoke_connection.main(["--url", URL, "--connection", "tracker", "--tool", "tracker__list_projects",
                                  "--json", *more], transport=door, env=env, out=out)
    return code, json.loads(out.getvalue()), out.getvalue()


def harness(door, name="claude-code", url=URL, *more, env=ENV):
    out = io.StringIO()
    code = smoke_harness.main(["--harness", name, "--url", url, "--json", *more], transport=door, env=env, out=out)
    return code, json.loads(out.getvalue()), out.getvalue()


def result_of(report, check):
    return next(c["result"] for c in report["checks"] if c["check"] == check)


def test_connection_passes_on_a_good_door(capsys):
    code, rep, text = conn(FakeDoor())
    assert code == 0 and rep["ok"], rep
    assert result_of(rep, "signed in") == "SKIP"
    err = capsys.readouterr().err
    assert_no_leak(text, err, values={KEY})


def test_connection_over_sse_replies():
    code, rep, _ = conn(FakeDoor(sse=True))
    assert code == 0, rep


@pytest.mark.parametrize("door,check", [
    (FakeDoor(keys=("other",)), "door answers"),
    (FakeDoor(results={"tracker__list_projects": {"content": [], "nextPageToken": "abc"}}), "no paging cursor in result"),
    (FakeDoor(results={"tracker__list_projects": {"content": [{"type": "text", "text": json.dumps({"items": [], "nextCursor": "p2"})}]}}),
     "no paging cursor in result"),
    (FakeDoor(results={"tracker__list_projects": {"content": [{"type": "text", "text": "x"}], "isError": True}}), "one read call"),
    (FakeDoor(tools=[{"name": "guide"}]), "tool listed"),
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


def test_connection_missing_key_fails_without_calling():
    door = FakeDoor()
    code, rep, _ = conn(door, env={})
    assert code == 1 and result_of(rep, "key present") == "FAIL" and door.calls == []


@pytest.mark.parametrize("auth,expect", [("oauth", "WARN"), ("service-account", "WARN"), ("browser-session", "FAIL")])
def test_auth_kinds_without_whoami(auth, expect):
    _, rep, _ = conn(FakeDoor(), "--auth-kind", auth)
    assert result_of(rep, "signed in") == expect


def test_whoami_prints_the_account_name_only():
    door = FakeDoor(results={"whoami": {"content": [], "structuredContent": {"email": "demo@example.com"}}})
    code, rep, text = conn(door, "--auth-kind", "oauth", "--whoami-tool", "whoami")
    assert code == 0
    note = next(c["note"] for c in rep["checks"] if c["check"] == "signed in")
    assert note == "signed in as demo@example.com"
    assert_no_leak(text, values={KEY})


def test_key_file_must_be_private(tmp_path):
    f = tmp_path / "key"
    f.write_text(KEY)
    f.chmod(0o644)
    code, rep, _ = conn(FakeDoor(), "--key-file", str(f), env={})
    assert code == 1 and "chmod 600" in rep["checks"][0]["note"]
    f.chmod(0o600)
    code, rep, _ = conn(FakeDoor(), "--key-file", str(f), env={})
    assert code == 0, rep


def test_harness_passes_on_a_good_door(capsys):
    code, rep, text = harness(FakeDoor())
    assert code == 0 and rep["ok"], rep
    for check in ("no key refused", "wrong key refused", "browser Origin refused", "unlisted Host refused"):
        assert result_of(rep, check) == "PASS"
    assert result_of(rep, "revoke") == "SKIP"
    assert_no_leak(text, capsys.readouterr().err, values={KEY})


@pytest.mark.parametrize("door,check", [
    (FakeDoor(require_key=False), "no key refused"),
    (FakeDoor(refuse_origin=False), "browser Origin refused"),
    (FakeDoor(refuse_host=False), "unlisted Host refused"),
])
def test_harness_fails_on_a_bad_door(door, check):
    code, rep, _ = harness(door)
    assert code == 1 and result_of(rep, check) == "FAIL"


def test_revoked_key_check():
    code, rep, _ = harness(FakeDoor(revoked=(KEY,)), "claude-code", URL, "--expect-revoked")
    assert code == 0 and result_of(rep, "revoked key refused") == "PASS"
    code, rep, _ = harness(FakeDoor(), "claude-code", URL, "--expect-revoked")
    assert code == 1


def test_oddboro_needs_https_short_names_one_page_and_read_hints():
    door = FakeDoor()
    code, rep, _ = harness(door, "oddboro", URL, "--server-name", "door")
    assert result_of(rep, "https address") == "FAIL"
    tailnet = "https://door.tailnet-name.ts.net/mcp"
    code, rep, _ = harness(FakeDoor(), "oddboro", tailnet, "--server-name", "door")
    assert code == 0, rep
    assert result_of(rep, "route Host accepted") == "PASS"
    long_id = "door-on-a-very-long-machine-name-example"
    code, rep, _ = harness(FakeDoor(), "oddboro", tailnet, "--server-name", long_id)
    assert result_of(rep, "tool names within limit") == "FAIL"
    code, rep, _ = harness(FakeDoor(page_size=2), "oddboro", tailnet, "--server-name", "door")
    assert result_of(rep, "all tools on the first page") == "FAIL"
    code, rep, _ = harness(FakeDoor(page_size=2), "codex", URL)
    assert result_of(rep, "all tools on the first page") == "WARN"
    code, rep, _ = harness(FakeDoor(), "oddboro", tailnet, "--server-name", "door", "--read-tool", "tracker__create_issue")
    assert result_of(rep, "read tool reachable read-only") == "FAIL"


def test_bad_args_json_is_refused():
    out = io.StringIO()
    assert smoke_connection.main(["--url", URL, "--connection", "c", "--tool", "t", "--args", "[1]"],
                                 transport=FakeDoor(), env=ENV, out=out) == 2
