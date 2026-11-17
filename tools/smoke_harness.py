#!/usr/bin/env python3
"""Smoke test for ONE harness's door key: list tools, one call, refusals, revoke. Runs on its own.

  HARNESS_KEY below is the environment variable holding THIS harness's door key.

  python tools/smoke_harness.py --harness codex --url http://127.0.0.1:8765/mcp \\
      --key-env HARNESS_KEY --server-name door --read-tool door__guide --args '{}'

  After you revoke the harness's key with the door's own command:
  python tools/smoke_harness.py --harness codex --url ... --key-env HARNESS_KEY --expect-revoked

Checks: https where the harness needs it; tools listed with the key; every full tool
name within the harness's limit; tools on the first page where the harness reads only
that page; Read only reachability for Oddboro; one call within the read limit; no key,
a wrong key and a browser Origin are refused; a Host the door does not list is
refused; and, with --expect-revoked, the revoked key is refused.
Exit codes: 0 pass, 1 a check failed, 2 bad arguments, 3 the output guard stopped the output.
"""

from __future__ import annotations

import argparse
import os
import secrets
import sys
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))

from kit.gotchas import long_names, read_limit_ok, read_only_reachable  # noqa: E402
from kit.harnesses import HARNESSES  # noqa: E402
from kit.mcp_client import McpClient  # noqa: E402
from kit.oddboro import address_problems  # noqa: E402
from kit.oddboro import facts as oddboro_facts  # noqa: E402
from kit.oddboro import parse as oddboro_parse  # noqa: E402
from kit.smoke import FAIL, PASS, SKIP, WARN, Checks, emit, load_key, parse_args_json  # noqa: E402

BAD_ORIGIN = "https://example.invalid"
BAD_HOST = "not-listed.invalid"


def _refused(status: int) -> bool:
    return 400 <= status < 500


def main(argv=None, transport=None, env=None, out=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--harness", required=True, choices=sorted(HARNESSES))
    ap.add_argument("--url", required=True, help="the door address exactly as this harness uses it")
    ap.add_argument("--key-env", default="DOOR_KEY", help="environment variable holding this harness's door key")
    ap.add_argument("--key-file", help="or a file (mode 600) holding it")
    ap.add_argument("--server-name", default="door", help="the name or service id this harness gives the door")
    ap.add_argument("--read-tool", help="a read tool for the one call (default: the first read-only tool)")
    ap.add_argument("--args", default="{}", help="JSON object of arguments for the read tool")
    ap.add_argument("--read-timeout", type=float, default=60.0, help="this harness's read timeout in seconds")
    ap.add_argument("--no-host-check", action="store_true", help="skip the wrong-Host refusal check")
    ap.add_argument("--oddboro-version", help="Oddboro only: the version from Setup > Updates or tools/oddboro_version.py")
    ap.add_argument("--expect-revoked", action="store_true", help="the key was revoked: expect a refusal")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    env = os.environ if env is None else env
    h = HARNESSES[a.harness]
    checks = Checks(f"harness {h.label} via {a.server_name}")
    arguments = parse_args_json(a.args)
    if arguments is None:
        sys.stderr.write("error: --args must be a JSON object\n")
        return 2

    key, problem = load_key(a.key_env if not a.key_file else None, a.key_file, env)
    if not key:
        checks.add("key present", FAIL, problem)
        return emit(checks, a.json, out)
    checks.add("key present", PASS, "value not shown")

    if a.expect_revoked:
        r = McpClient(a.url, key=key, transport=transport, timeout=a.read_timeout).initialize()
        checks.add("revoked key refused", PASS if r.status == 401 else FAIL, f"HTTP {r.status}")
        return emit(checks, a.json, out)

    scheme = urlsplit(a.url).scheme
    if a.harness == "oddboro":
        fails, warns = address_problems(a.url)
        checks.add("https address", FAIL if any("https" in f for f in fails) else PASS,
                   next((f for f in fails if "https" in f), ""))
        for f in (x for x in fails if "https" not in x):
            checks.add("exact address", FAIL, f)
        for w in warns:
            checks.add("short address", WARN, w)
        if a.oddboro_version:
            f = oddboro_facts(oddboro_parse(a.oddboro_version))
            ok = f.get("supported")
            checks.add("Oddboro version", PASS if ok else FAIL, f"{f['version']}: {f['next']}")
            if ok and f.get("new_door_tools") != "refresh button":
                checks.add("new door tools", WARN, "this version needs the Read grant removed and re-added after the door adds tools")
        else:
            checks.add("Oddboro version", WARN, "pass --oddboro-version (Setup > Updates); v0.0.6 or later is needed")
    elif h.https_required.startswith("yes"):
        checks.add("https address", PASS if scheme == "https" else FAIL,
                   "" if scheme == "https" else f"{h.label} accepts only https:// addresses; use an https route to the door")

    client = McpClient(a.url, key=key, transport=transport, timeout=a.read_timeout)
    init = client.initialize()
    if 300 <= init.status < 400:
        checks.add("door answers with this key", FAIL, f"HTTP {init.status}: the address redirects; use the exact address with no redirect")
        return emit(checks, a.json, out)
    if init.status != 200 or init.error:
        checks.add("door answers with this key", FAIL, init.error or f"HTTP {init.status}")
        return emit(checks, a.json, out)
    checks.add("door answers with this key", PASS)
    route_host = (urlsplit(a.url).hostname or "").lower()
    if route_host not in ("127.0.0.1", "localhost", "::1"):
        checks.add("route Host accepted", PASS, "the door lists this route's Host exactly")

    tools, pages, first_has_next, last = client.list_tools()
    checks.add("list tools", PASS if tools else FAIL, f"{len(tools)} tool(s) on {pages} page(s)")
    names = [str(t.get("name")) for t in tools]
    long = long_names(a.harness, a.server_name, names)
    if long:
        worst = max(long, key=lambda x: x[1])
        checks.add("tool names within limit", FAIL,
                   f"{len(long)} over {h.name_limit}; longest {worst[1]}: {checks.red.name(worst[0])}")
    else:
        checks.add("tool names within limit", PASS, f"limit {h.name_limit}, form {h.tool_name}")
    if first_has_next:
        first_only = h.paging.startswith("first page")
        checks.add("all tools on the first page", FAIL if first_only else WARN,
                   f"{h.label} reads only the first page" if first_only else "tools span pages; check this harness reads them all")
    else:
        checks.add("all tools on the first page", PASS)

    reachable = [t for t in tools if read_only_reachable(t)[0]]
    if a.harness == "oddboro":
        checks.add("Read only grant reaches tools", PASS if reachable else FAIL,
                   f"{len(reachable)} of {len(tools)} reachable with a Read only grant")
    read_tool = a.read_tool or (str(reachable[0].get("name")) if reachable else None)
    if a.harness == "oddboro" and read_tool and a.read_tool:
        tool = next((t for t in tools if t.get("name") == read_tool), {})
        ok, why = read_only_reachable(tool) if tool else (False, "not listed")
        checks.add("read tool reachable read-only", PASS if ok else FAIL, why)

    if read_tool is None:
        checks.add("one call", FAIL, "no read-only tool found; pass --read-tool")
    else:
        r = client.call_tool(read_tool, arguments)
        good = r.status == 200 and not r.error and not (isinstance(r.result, dict) and r.result.get("isError"))
        checks.add("one call", PASS if good else FAIL, f"{checks.red.name(read_tool)} in {r.elapsed:.2f}s" if good else (r.error or "the tool returned an error"))
        if good:
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
    checks.add("revoke", SKIP, "revoke this harness's key with the door's own command, then run again with --expect-revoked")
    return emit(checks, a.json, out)


if __name__ == "__main__":
    sys.exit(main())
