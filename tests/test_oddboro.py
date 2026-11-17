"""Oddboro version facts, version detection and the Oddboro-only smoke checks. No network."""

from __future__ import annotations

import io
import json

import oddboro_version
import smoke_harness
from fakedoor import FakeDoor
from kit.oddboro import address_problems, facts, parse
from test_smoke import ENV, result_of

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
    code = smoke_harness.main(["--harness", "oddboro", "--url", url, "--server-name", "door", "--json", *more],
                              transport=door, env=ENV, out=out)
    return code, json.loads(out.getvalue())


def test_oddboro_version_gate_in_smoke():
    code, rep = harness(FakeDoor(), TAILNET, "--oddboro-version", "v0.0.4")
    assert code == 1 and result_of(rep, "Oddboro version") == "FAIL"
    code, rep = harness(FakeDoor(), TAILNET, "--oddboro-version", "v0.0.9")
    assert code == 0 and result_of(rep, "new door tools") == "WARN"
    code, rep = harness(FakeDoor(), TAILNET)
    assert result_of(rep, "Oddboro version") == "WARN"


def test_redirect_and_query_fail():
    code, rep = harness(FakeDoor(redirect=True), TAILNET, "--oddboro-version", "v0.0.12")
    assert code == 1 and "redirects" in next(c["note"] for c in rep["checks"] if c["check"] == "door answers with this key")
    code, rep = harness(FakeDoor(), TAILNET + "?x=1", "--oddboro-version", "v0.0.12")
    assert code == 1 and result_of(rep, "exact address") == "FAIL"
