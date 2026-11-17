"""Oddboro version facts, version detection and the Oddboro-only smoke checks. No network."""

from __future__ import annotations

import io
import json

import oddboro_version
import smoke_harness
from fakedoor import FakeDoor
from kit.oddboro import address_problems, facts, keyring_preflight, parse, service_id
from test_smoke import KEY_ARGS, result_of

TAILNET = "https://door.tailnet-name.ts.net/mcp"


def test_version_facts():
    assert facts(parse("v0.0.5"))["supported"] is False
    six = facts(parse("0.0.6"))
    assert six["supported"] and six["calls"] == "direct from each runner" and six["new_door_tools"] == "remove and re-add the grant"
    nine = facts(parse("v0.0.9-3-gabc"))
    assert nine["calls"] == "office gateway" and not nine["health_endpoint"]
    eleven = facts(parse("v0.0.11"))
    assert eleven["new_door_tools"] == "refresh button" and eleven["health_endpoint"]
    assert facts(None)["supported"] is None


def test_address_rules():
    assert address_problems("http://d.example.com/mcp")[0]
    assert address_problems("https://d.example.com/mcp?x=1")[0]
    assert address_problems("https://d.example.com/mcp") == ([], [])
    assert address_problems("https://a-very-long-host-name.example.com/some/long/path")[1]


def run_detect(*argv, status=200, body=b"", described=None):
    out = io.StringIO()
    code = oddboro_version.main(["--json", *argv], getter=lambda url: (status, body),
                                describe=lambda folder: described, out=out)
    return code, json.loads(out.getvalue())


def test_detection_order():
    code, f = run_detect("--version", "v0.0.7", status=500)
    assert code == 0 and f["found_by"].startswith("the Setup window")
    code, f = run_detect(body=json.dumps({"version": "0.0.12"}).encode())
    assert code == 0 and f["version"] == "v0.0.12" and f["found_by"] == "GET /api/health"
    code, f = run_detect(body=json.dumps({"version": "development"}).encode(), described="v0.0.10-4-gdead")
    assert "development" in f["found_by"] and f["version"] == "unknown"
    code, f = run_detect("--checkout", "/src", body=json.dumps({"version": "development"}).encode(), described="v0.0.10-4-gdead")
    assert code == 0 and f["version"] == "v0.0.10" and f["found_by"].startswith("git describe")
    code, f = run_detect(status=401)
    assert code == 1 and "app key" in f["found_by"]
    code, f = run_detect(status=0)
    assert code == 1 and f["supported"] is None


def harness(door, url, *more):
    out = io.StringIO()
    code = smoke_harness.main(["--harness", "oddboro", "--url", url, "--server-name", "door", "--json", *KEY_ARGS, *more],
                              transport=door, out=out)
    return code, json.loads(out.getvalue())


def test_oddboro_version_gate_in_smoke():
    code, rep = harness(FakeDoor(), TAILNET, "--oddboro-version", "v0.0.4")
    assert code == 1 and result_of(rep, "Oddboro version") == "FAIL"
    code, rep = harness(FakeDoor(), TAILNET, "--oddboro-version", "v0.0.9")
    assert code == 0 and result_of(rep, "new door tools") == "WARN"
    code, rep = harness(FakeDoor(), TAILNET)
    assert code == 1 and result_of(rep, "Oddboro version") == "FAIL"
    code, rep = harness(FakeDoor(), TAILNET, "--oddboro-version", "latest")
    assert code == 1 and result_of(rep, "Oddboro version") == "FAIL"


def test_service_id_rule():
    assert service_id("https://Door.Tailnet-Name.ts.net:8443/mcp?x=1") == "door-tailnet-name-ts-net-mcp"
    assert service_id("https://door.localhost/") == "door-localhost"


def test_non_numeric_port_gives_a_fixed_message(monkeypatch, capsys):
    monkeypatch.setenv("ODDBORO_PORT", "not-a-port")
    code = oddboro_version.main(["--json"], getter=lambda url: (0, b""), describe=lambda f: None, out=io.StringIO())
    assert code == 2 and "ODDBORO_PORT" in capsys.readouterr().err


def test_keyring_preflight():
    which_none = lambda name: None  # noqa: E731
    which_all = lambda name: "/usr/bin/" + name  # noqa: E731
    assert keyring_preflight("darwin", which_none, None, {})[0]
    ok, why = keyring_preflight("linux", which_none, None, {})
    assert not ok and "secret-tool" in why
    ok, why = keyring_preflight("linux", which_all, lambda argv, env, t: ":1.2 org.freedesktop.portal\n", {})
    assert not ok and "keyring" in why
    assert keyring_preflight("linux", which_all, lambda argv, env, t: "org.freedesktop.secrets 1234 gnome-keyring-d\n", {})[0]


def test_version_tool_ignores_proxies():
    import urllib.request
    opener = oddboro_version.make_opener()
    assert not [h for h in opener.handlers if isinstance(h, urllib.request.ProxyHandler) and h.proxies]


def test_redirect_and_query_fail():
    code, rep = harness(FakeDoor(redirect=True), TAILNET, "--oddboro-version", "v0.0.12")
    assert code == 1 and "redirects" in next(c["note"] for c in rep["checks"] if c["check"] == "door answers with this key")
    code, rep = harness(FakeDoor(), TAILNET + "?x=1", "--oddboro-version", "v0.0.12")
    assert code == 1 and result_of(rep, "exact address") == "FAIL"
