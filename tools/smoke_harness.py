#!/usr/bin/env python3
"""Smoke test for ONE harness's door key: list tools, one call, refusals, revoke. Runs on its own.

  python tools/smoke_harness.py --harness codex --url http://127.0.0.1:8765/mcp \\
      --key-file <0600 file with THIS harness's door key> --server-name door --read-tool guide

  After you revoke a canary key with the door's own command:
  python tools/smoke_harness.py --harness codex --url ... --key-file <canary key file> --expect-revoked

The key is read from the file inside this process; pass the path, never the value.

Checks: https where the harness needs it (Oddboro: also the version, the exact address and the service
id it derives from the address); tools listed with the key, within 5 seconds; every full tool name within
the harness's limit; tools on the first page where the harness reads only that page; no outputSchema;
Oddboro's Read only reachability; with --plan, no offered tool the plan made red; with --baseline-tools,
no new tool that changes things; a GET answered with 405 or an event stream; one read-only call whose
content is an array, within the read limit; no key, a wrong key and a browser Origin are refused; a Host
the door does not list is refused; with --expect-revoked, the revoked key is refused.
Exit codes: 0 pass, 1 a check failed, 2 bad arguments, 3 the output guard stopped the output.
"""

from __future__ import annotations

import argparse
import json
import secrets
import sys
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))

from kit.gotchas import long_names, plan_tier, read_limit_ok, read_only_reachable, tool_marks, tools_diff  # noqa: E402
from kit.harnesses import HARNESSES  # noqa: E402
from kit.mcp_client import McpClient  # noqa: E402
from kit.oddboro import address_problems, service_id  # noqa: E402
from kit.oddboro import facts as oddboro_facts  # noqa: E402
from kit.oddboro import parse as oddboro_parse  # noqa: E402
from kit.smoke import FAIL, PASS, SKIP, WARN, Checks, emit, load_key, load_plan, parse_args_json, write_private_json  # noqa: E402

BAD_ORIGIN = "https://example.invalid"
BAD_HOST = "not-listed.invalid"
FAST = 5.0  # many HTTP clients give up after 5 seconds


def _refused(status: int) -> bool:
    return 400 <= status < 500


def _oddboro(a, checks: Checks) -> str:
    """Oddboro-only checks before any request. Returns the service id to judge names by."""
    fails, warns = address_problems(a.url)
    https = next((f for f in fails if "https" in f), None)
    checks.add("https address", FAIL if https else PASS, https or "")
    for f in (x for x in fails if "https" not in x):
        checks.add("exact address", FAIL, f)
    for w in warns:
        checks.add("short address", WARN, w)
    if not a.oddboro_version:
        checks.add("Oddboro version", FAIL, "unknown: read Setup > Updates or run tools/oddboro_version.py and pass --oddboro-version; "
                                            "v0.0.6 or later is needed, so update Oddboro first if it is older")
    else:
        f = oddboro_facts(oddboro_parse(a.oddboro_version))
        checks.add("Oddboro version", PASS if f.get("supported") else FAIL,
                   f"{f['version']}: {f['next']}" if f.get("supported") is not None else
                   "not a version number: update Oddboro to v0.0.6 or later and read it again from Setup > Updates")
        if f.get("supported") and f.get("new_door_tools") != "refresh button":
            checks.add("new door tools", WARN, "this version needs the Read grant removed and re-added after the door adds tools")
    sid = service_id(a.url)
    if a.server_name not in ("door", sid):
        checks.add("service id", WARN, f"Oddboro makes the id {checks.red.name(sid)} from this address; names are judged by it")
    return sid


def main(argv=None, transport=None, out=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--harness", required=True, choices=sorted(HARNESSES))
    ap.add_argument("--url", required=True, help="the door address exactly as this harness uses it")
    ap.add_argument("--key-file", required=True, help="a file (mode 600) holding this harness's door key")
    ap.add_argument("--server-name", default="door", help="the name this harness gives the door (Oddboro: derived from the address)")
    ap.add_argument("--read-tool", help="a read tool for the one call (default: the first read-only tool)")
    ap.add_argument("--args", default="{}", help="JSON object of arguments for the read tool")
    ap.add_argument("--read-timeout", type=float, default=60.0, help="this harness's read timeout in seconds")
    ap.add_argument("--plan", help="the manifest from 02-plan; no offered tool may be red in it")
    ap.add_argument("--save-tools", help="write the tool names and read-only marks to this file (0600), for the next run")
    ap.add_argument("--baseline-tools", help="a file from --save-tools on an earlier run: flag new tools that change things")
    ap.add_argument("--no-host-check", action="store_true", help="skip the wrong-Host refusal check")
    ap.add_argument("--expect-revoked", action="store_true", help="the key was revoked: expect a refusal")
    ap.add_argument("--oddboro-version", help="Oddboro only: the version from Setup > Updates or tools/oddboro_version.py")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    h = HARNESSES[a.harness]
    checks = Checks(f"harness {h.label} via {a.server_name}")
    arguments = parse_args_json(a.args)
    plan = load_plan(a.plan) if a.plan else None
    if arguments is None or (a.plan and plan is None):
        sys.stderr.write("error: --args must be a JSON object and --plan a manifest\n")
        return 2

    key, problem = load_key(a.key_file)
    if not key:
        checks.add("key present", FAIL, problem)
        return emit(checks, a.json, out)
    checks.add("key present", PASS, "read from the file; value not shown")

    if a.expect_revoked:
        r = McpClient(a.url, key=key, transport=transport, timeout=a.read_timeout).initialize()
        checks.add("revoked key refused", PASS if r.status == 401 else FAIL, f"HTTP {r.status}")
        return emit(checks, a.json, out)

    server = a.server_name
    if a.harness == "oddboro":
        server = _oddboro(a, checks)
    elif h.https_required.startswith("yes"):
        https = urlsplit(a.url).scheme == "https"
        checks.add("https address", PASS if https else FAIL, "" if https else f"{h.label} accepts only https:// addresses")

    client = McpClient(a.url, key=key, transport=transport, timeout=a.read_timeout)
    init = client.initialize()
    if 300 <= init.status < 400:
        checks.add("door answers with this key", FAIL, f"HTTP {init.status}: the address redirects; use the exact address with no redirect")
        return emit(checks, a.json, out)
    if init.status != 200 or init.error:
        checks.add("door answers with this key", FAIL, init.error or f"HTTP {init.status}")
        return emit(checks, a.json, out)
    checks.add("door answers with this key", PASS)
    checks.add("initialize under 5 s", PASS if init.elapsed < FAST else FAIL, f"{init.elapsed:.2f}s")
    if (urlsplit(a.url).hostname or "").lower() not in ("127.0.0.1", "localhost", "::1"):
        checks.add("route Host accepted", PASS, "the door lists this route's Host exactly")

    tools, pages, first_has_next, _ = client.list_tools()
    checks.add("list tools", PASS if tools else FAIL, f"{len(tools)} tool(s) on {pages} page(s)")
    checks.add("tools/list under 5 s", PASS if client.first_list_elapsed < FAST else FAIL, f"{client.first_list_elapsed:.2f}s")
    names = [str(t.get("name")) for t in tools]
    long = long_names(a.harness, server, names)
    if long:
        worst = max(long, key=lambda x: x[1])
        checks.add("tool names within limit", FAIL, f"{len(long)} over {h.name_limit}; longest {worst[1]}: {checks.red.text(worst[0], 200)}")
    else:
        checks.add("tool names within limit", PASS, f"limit {h.name_limit}, form {h.tool_name}, server {checks.red.name(server)}")
    if first_has_next:
        first_only = h.paging.startswith("first page")
        checks.add("all tools on the first page", FAIL if first_only else WARN,
                   f"{h.label} reads only the first page" if first_only else "tools span pages; check this harness reads them all")
    else:
        checks.add("all tools on the first page", PASS)
    typed = [n for n, t in zip(names, tools, strict=False) if "outputSchema" in t]
    checks.add("no outputSchema", FAIL if typed else PASS,
               f"{len(typed)} tool(s) declare outputSchema; some harnesses refuse them" if typed else "")

    reachable = [t for t in tools if read_only_reachable(t)[0]]
    if a.harness == "oddboro":
        checks.add("Read only grant reaches tools", PASS if reachable else FAIL,
                   f"{len(reachable)} of {len(tools)} reachable with a Read only grant")
    if plan is not None:
        red = [n for n in names if plan_tier(plan, n) not in (None, "green", "yellow")]
        own = [n for n, t in zip(names, tools, strict=False) if plan_tier(plan, n) is None and not read_only_reachable(t)[0]]
        checks.add("plan tiers of offered tools", FAIL if red else PASS,
                   f"{len(red)} offered tool(s) the plan made red: " + ", ".join(checks.red.name(n) for n in red[:5]) if red else "")
        if own:
            checks.add("door's own tools", WARN, f"{len(own)} door tool(s) not marked read-only; check the plan allows drafts")
    if a.baseline_tools:
        try:
            old = json.loads(Path(a.baseline_tools).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            old = None
        if not isinstance(old, list):
            checks.add("no new tools that change things", FAIL, "the baseline file is missing or not a saved tool list")
        else:
            d = tools_diff(old, tools)
            bad = d["added_not_read_only"]
            checks.add("no new tools that change things", FAIL if bad else PASS,
                       ("new tools that are not read-only: " + ", ".join(checks.red.name(n) for n in bad[:8])) if bad
                       else f"{len(d['added'])} new, {len(d['removed'])} removed")
    if a.save_tools:
        write_private_json(a.save_tools, tool_marks(tools))

    status, ctype, _ = client.get_probe()
    streams = status == 405 or (status == 200 and "text/event-stream" in ctype)
    checks.add("GET answered with 405 or a stream", PASS if streams else FAIL, f"HTTP {status} {ctype}".strip())

    read_tool = a.read_tool or (str(reachable[0].get("name")) if reachable else None)
    if read_tool is None:
        checks.add("one call", FAIL, "no read-only tool found; pass --read-tool")
    else:
        tool = next((t for t in tools if t.get("name") == read_tool), None)
        ok, why = read_only_reachable(tool) if tool else (False, "the tool is not listed")
        if ok and plan is not None and plan_tier(plan, read_tool) not in (None, "green"):
            ok, why = False, "the plan does not make it green"
        checks.add("read-only before calling", PASS if ok else FAIL, "" if ok else f"not called: {why}")
        if ok:
            r = client.call_tool(read_tool, arguments)
            good = r.status == 200 and not r.error and not (isinstance(r.result, dict) and r.result.get("isError"))
            checks.add("one call", PASS if good else FAIL,
                       f"{checks.red.name(read_tool)} in {r.elapsed:.2f}s" if good else (r.error or "the tool returned an error"))
            if good:
                array = isinstance(r.result, dict) and isinstance(r.result.get("content"), list)
                checks.add("result content is an array", PASS if array else FAIL, "" if array else "MCP results carry content as a list")
                checks.add("within read limit", PASS if read_limit_ok(r.elapsed, a.read_timeout) else FAIL,
                           f"{r.elapsed:.2f}s of {a.read_timeout:.0f}s; set {h.read_timeout}")

    no_key = McpClient(a.url, key=None, transport=transport, timeout=a.read_timeout).initialize()
    checks.add("no key refused", PASS if no_key.status == 401 else (WARN if _refused(no_key.status) else FAIL), f"HTTP {no_key.status}")
    wrong = McpClient(a.url, key=secrets.token_urlsafe(24), transport=transport, timeout=a.read_timeout).initialize()
    checks.add("wrong key refused", PASS if wrong.status == 401 else (WARN if _refused(wrong.status) else FAIL), f"HTTP {wrong.status}")
    origin = McpClient(a.url, key=key, transport=transport, timeout=a.read_timeout, extra_headers={"Origin": BAD_ORIGIN}).initialize()
    checks.add("browser Origin refused", PASS if _refused(origin.status) else FAIL, f"HTTP {origin.status}")
    if a.no_host_check:
        checks.add("unlisted Host refused", SKIP, "--no-host-check")
    else:
        host = McpClient(a.url, key=key, transport=transport, timeout=a.read_timeout, extra_headers={"Host": BAD_HOST}).initialize()
        checks.add("unlisted Host refused", PASS if _refused(host.status) else FAIL, f"HTTP {host.status}")
    checks.add("revoke", SKIP, "issue a canary key, revoke it with the door's own command, then run again with --expect-revoked")
    return emit(checks, a.json, out)


if __name__ == "__main__":
    sys.exit(main())
