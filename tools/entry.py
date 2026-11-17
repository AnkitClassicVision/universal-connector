#!/usr/bin/env python3
"""Print the config entry one harness needs for the door. It never takes or prints a key.

  python tools/entry.py --harness codex --url http://127.0.0.1:8765/mcp --key-env CODEX_DOOR_KEY
  python tools/entry.py --list            # every harness, its stage and its config places
  python tools/entry.py --limits-table    # the known-limits table used in the options guide

Where a harness can read the key from an environment variable or its own secret store,
the entry points there. Where it cannot, the entry holds a placeholder that you replace
yourself, in the harness's own settings, after a backup.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from kit.harnesses import DEFAULT_NAME, DEFAULT_URL, HARNESSES, entry, entry_problem, limits_table  # noqa: E402
from kit.report import guard  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--harness", choices=sorted(HARNESSES))
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--key-env", default="DOOR_KEY", help="the environment variable name the harness reads")
    ap.add_argument("--name", default=DEFAULT_NAME, help="the server name inside the harness")
    ap.add_argument("--read-timeout", type=int, default=120, help="seconds")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--limits-table", action="store_true")
    a = ap.parse_args(argv)
    if a.limits_table:
        sys.stdout.write(guard(limits_table()))
        return 0
    if a.list or not a.harness:
        for h in HARNESSES.values():
            places = "; ".join(p for paths in h.config.values() for p in paths)
            sys.stdout.write(guard(f"{h.id:<15} {h.stage:<28} {places}\n"))
        return 0
    problem = entry_problem(a.url, a.key_env, a.name)
    if problem:
        sys.stderr.write(f"error: {problem}\n")
        return 2
    h = HARNESSES[a.harness]
    text = entry(a.harness, a.url, a.key_env, a.name, a.read_timeout)
    notes = "".join(f"# note: {n}\n" for n in h.notes)
    sys.stdout.write(guard(f"# {h.label}: paste into the place named in stage {h.stage}, after a backup.\n{notes}{text}"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
