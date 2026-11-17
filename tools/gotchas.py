#!/usr/bin/env python3
"""Offline gotcha checks on saved files. No network.

  python tools/gotchas.py names   --harness oddboro --server-name <service id> --tools tools.json
  python tools/gotchas.py cursors --result result.json
  python tools/gotchas.py host    --route-host <host the route sends> --door-hosts host1,host2
  python tools/gotchas.py timeout --door-worst-case 45 --read-timeout 60
  python tools/gotchas.py readonly --tools tools.json

`tools.json` is a saved tools/list result (an object with "tools", or a list of tools,
or a plain list of names). Prints pass or fail; never prints result content.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from kit.gotchas import cursor_paths, host_allowed, long_names, read_limit_ok, read_only_reachable  # noqa: E402
from kit.harnesses import HARNESSES  # noqa: E402
from kit.smoke import FAIL, PASS, Checks, emit  # noqa: E402


def _tools(path: str) -> list[dict]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("tools", [])
    return [t if isinstance(t, dict) else {"name": str(t)} for t in data]


def main(argv=None, out=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("names")
    p.add_argument("--harness", required=True, choices=sorted(HARNESSES))
    p.add_argument("--server-name", required=True)
    p.add_argument("--tools", required=True)
    p = sub.add_parser("cursors")
    p.add_argument("--result", required=True)
    p = sub.add_parser("host")
    p.add_argument("--route-host", required=True)
    p.add_argument("--door-hosts", required=True, help="comma list from the door's settings")
    p = sub.add_parser("timeout")
    p.add_argument("--door-worst-case", type=float, required=True, help="seconds")
    p.add_argument("--read-timeout", type=float, required=True, help="seconds")
    p = sub.add_parser("readonly")
    p.add_argument("--tools", required=True)
    for p in sub.choices.values():
        p.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    checks = Checks(f"gotcha {a.cmd}")
    try:
        if a.cmd == "names":
            names = [str(t.get("name")) for t in _tools(a.tools)]
            long = long_names(a.harness, a.server_name, names)
            checks.add("tool names within limit", FAIL if long else PASS,
                       f"{len(long)} of {len(names)} over {HARNESSES[a.harness].name_limit}" if long else f"{len(names)} checked")
            for full, n in sorted(long, key=lambda x: -x[1])[:10]:
                checks.add("too long", FAIL, f"{n}: {checks.red.name(full)}")
        elif a.cmd == "cursors":
            found = cursor_paths(json.loads(Path(a.result).read_text(encoding="utf-8")))
            checks.add("no paging cursor", FAIL if found else PASS, "; ".join(found[:10]))
        elif a.cmd == "host":
            ok = host_allowed(a.route_host, a.door_hosts.split(","))
            checks.add("route Host listed exactly", PASS if ok else FAIL,
                       "" if ok else "add the exact Host the route sends to the door's host list")
        elif a.cmd == "timeout":
            ok = read_limit_ok(a.door_worst_case, a.read_timeout)
            checks.add("read timeout above the door's slowest call", PASS if ok else FAIL,
                       f"door {a.door_worst_case:.0f}s, client {a.read_timeout:.0f}s")
        else:
            tools = _tools(a.tools)
            bad = [(t.get("name"), read_only_reachable(t)[1]) for t in tools if not read_only_reachable(t)[0]]
            checks.add("read tools reachable read-only", PASS if len(bad) < len(tools) else FAIL,
                       f"{len(tools) - len(bad)} of {len(tools)} reachable")
            for name, why in bad[:20]:
                checks.add("not reachable read-only", "INFO", f"{checks.red.name(name)}: {why}")
    except (OSError, ValueError):
        sys.stderr.write("error: the input file is missing or is not JSON\n")
        return 2
    return emit(checks, a.json, out)


if __name__ == "__main__":
    sys.exit(main())
