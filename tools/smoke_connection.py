#!/usr/bin/env python3
"""Smoke test for ONE connection through the door: one read call. Runs on its own.

  DOOR_KEY is the environment variable that holds a door key (never pass a key as an argument).

  python tools/smoke_connection.py --url http://127.0.0.1:8765/mcp --key-env DOOR_KEY \\
      --connection tracker --tool tracker__list_projects --args '{"limit": 1}' --auth-kind api-key

  Add --whoami-tool <tool> where the service has a "who am I" read; it prints "signed in as <account>".
  A browser lane (--auth-kind browser-session) must pass --whoami-tool.

Checks: key present, door answers, tool listed, the call succeeds within the read limit,
the result is not empty, carries no paging cursor and no key-shaped string, and the
credential works for its auth kind. Prints pass or fail per check, never the key or the result.
Exit codes: 0 pass, 1 a check failed, 2 bad arguments, 3 the output guard stopped the output.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from kit.gotchas import cursor_paths, key_shapes_in, read_limit_ok  # noqa: E402
from kit.mcp_client import McpClient  # noqa: E402
from kit.smoke import FAIL, PASS, SKIP, WARN, Checks, emit, load_key, parse_args_json  # noqa: E402

AUTH_KINDS = ("api-key", "oauth", "service-account", "browser-session")
AUTH_FIX = {
    "api-key": "check the vault entry for this connection; store a fresh key yourself if it was revoked",
    "oauth": "sign in again yourself through the door's login flow; the agent never handles codes",
    "service-account": "check the key file path, its mode (600) and the account's role",
    "browser-session": "sign in again yourself in the browser lane's own profile",
}
ACCOUNT_KEYS = ("email", "login", "username", "user", "account", "name", "display_name", "displayName", "workspace")


def _account(result) -> str | None:
    if not isinstance(result, dict):
        return None
    for source in (result.get("structuredContent"), result):
        if isinstance(source, dict):
            for k in ACCOUNT_KEYS:
                v = source.get(k)
                if isinstance(v, str) and v.strip():
                    return v.strip()
                if isinstance(v, dict):
                    inner = _account({"structuredContent": v})
                    if inner:
                        return inner
    for item in result.get("content") or []:
        if isinstance(item, dict) and item.get("type") == "text" and str(item.get("text", "")).strip():
            return str(item["text"]).strip().splitlines()[0][:80]
    return None


def _has_content(result) -> bool:
    if not isinstance(result, dict):
        return False
    return bool(result.get("content") or result.get("structuredContent"))


def main(argv=None, transport=None, env=None, out=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", required=True, help="the door's MCP address")
    ap.add_argument("--key-env", default="DOOR_KEY", help="environment variable holding a door key (default DOOR_KEY)")
    ap.add_argument("--key-file", help="or a file (mode 600) holding the key")
    ap.add_argument("--connection", required=True, help="the connection's name in the manifest")
    ap.add_argument("--tool", required=True, help="the read tool to call")
    ap.add_argument("--args", default="{}", help="JSON object of arguments for the read tool")
    ap.add_argument("--auth-kind", choices=AUTH_KINDS, default="api-key")
    ap.add_argument("--whoami-tool", help="a read tool that returns the signed-in account")
    ap.add_argument("--read-timeout", type=float, default=60.0, help="the client's read timeout in seconds (default 60)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    env = os.environ if env is None else env

    checks = Checks(f"connection {a.connection} ({a.auth_kind})")
    arguments = parse_args_json(a.args)
    if arguments is None:
        sys.stderr.write("error: --args must be a JSON object\n")
        return 2
    key, problem = load_key(a.key_env if not a.key_file else None, a.key_file, env)
    if not key:
        checks.add("key present", FAIL, problem)
        return emit(checks, a.json, out)
    checks.add("key present", PASS, "value not shown")

    client = McpClient(a.url, key=key, transport=transport, timeout=a.read_timeout)
    init = client.initialize()
    if init.status != 200 or init.error:
        checks.add("door answers", FAIL, init.error or f"HTTP {init.status}")
        return emit(checks, a.json, out)
    checks.add("door answers", PASS)

    tools, pages, _, last = client.list_tools()
    names = {str(t.get("name")) for t in tools}
    if last.status != 200 and not tools:
        checks.add("tool listed", FAIL, last.error or f"HTTP {last.status}")
        return emit(checks, a.json, out)
    checks.add("tool listed", PASS if a.tool in names else FAIL,
               f"{len(tools)} tool(s) on {pages} page(s)" + ("" if a.tool in names else f"; {a.tool} is not one of them"))

    reply = client.call_tool(a.tool, arguments)
    failed = reply.status != 200 or reply.error or (isinstance(reply.result, dict) and reply.result.get("isError"))
    if failed:
        why = reply.error or ("the tool returned an error" if reply.status == 200 else f"HTTP {reply.status}")
        checks.add("one read call", FAIL, f"{why}: {AUTH_FIX[a.auth_kind]}")
    else:
        checks.add("one read call", PASS, f"{reply.elapsed:.2f}s")
        checks.add("result not empty", PASS if _has_content(reply.result) else WARN)
        cursors = cursor_paths(reply.result)
        checks.add("no paging cursor in result", FAIL if cursors else PASS,
                   f"{len(cursors)} cursor field(s); the door must drop them" if cursors else "")
        shapes = key_shapes_in(reply.result)
        checks.add("no key-shaped text in result", FAIL if shapes else PASS, ", ".join(shapes))
        checks.add("within read limit", PASS if read_limit_ok(reply.elapsed, a.read_timeout) else FAIL,
                   f"{reply.elapsed:.2f}s of {a.read_timeout:.0f}s")

    if a.whoami_tool:
        who = client.call_tool(a.whoami_tool, {})
        ok = who.status == 200 and not who.error and not (isinstance(who.result, dict) and who.result.get("isError"))
        account = _account(who.result) if ok else None
        checks.add("signed in", PASS if account else FAIL,
                   f"signed in as {checks.red.name(account)}" if account else AUTH_FIX[a.auth_kind])
    elif a.auth_kind == "browser-session":
        checks.add("signed in", FAIL, "a browser lane must prove its sign-in: pass --whoami-tool")
    elif a.auth_kind in ("oauth", "service-account"):
        checks.add("signed in", WARN, "add --whoami-tool to show the signed-in account")
    else:
        checks.add("signed in", SKIP, "the read call proves the key works")
    return emit(checks, a.json, out)


if __name__ == "__main__":
    sys.exit(main())
