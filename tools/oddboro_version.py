#!/usr/bin/env python3
"""Find the Oddboro version and say what it means for connecting the door.

  python tools/oddboro_version.py --version v0.0.9          # what the Setup window shows
  python tools/oddboro_version.py                           # ask the local office (v0.0.11 and later)
  python tools/oddboro_version.py --checkout <source folder>  # a source run: git describe --tags

Order of evidence: the Setup window's Updates section ("the version this is"), then
GET http://127.0.0.1:<ODDBORO_PORT or 4500>/api/health (field version, v0.0.11 and later;
the desktop app may refuse it without its app key; a source run says development),
then `git describe --tags` in a source checkout. Loopback only; it sends no key.
Exit codes: 0 supported, 1 not supported or unknown, 2 bad arguments.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from kit.oddboro import facts, parse  # noqa: E402
from kit.report import guard  # noqa: E402


def http_get(url: str, timeout: float = 5.0) -> tuple[int, bytes]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310 - loopback only
            return resp.status, resp.read(100_000)
    except urllib.error.HTTPError as exc:
        return exc.code, b""
    except (urllib.error.URLError, TimeoutError, OSError):
        return 0, b""


def git_describe(folder: str) -> str | None:
    try:
        done = subprocess.run(["git", "-C", folder, "describe", "--tags"], capture_output=True, text=True,
                              timeout=10, check=False, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def detect(version: str | None, port: int, checkout: str | None, getter=http_get, describe=git_describe) -> tuple[str, str | None]:
    """(how it was found, version text or None)."""
    if version:
        return "the Setup window (given)", version
    status, body = getter(f"http://127.0.0.1:{port}/api/health")
    if status == 200:
        try:
            v = json.loads(body).get("version")
        except (ValueError, AttributeError):
            v = None
        if isinstance(v, str) and v.strip().lower() == "development":
            if checkout:
                return "git describe --tags (source run)", describe(checkout)
            return "health says development: a source run; pass --checkout <folder>", None
        if isinstance(v, str):
            return "GET /api/health", v
    if status in (401, 403):
        return "the desktop app refused /api/health without its app key; read Setup > Updates and pass --version", None
    if checkout:
        return "git describe --tags", describe(checkout)
    return "no answer from /api/health (not running, or older than v0.0.11); read Setup > Updates and pass --version", None


def main(argv=None, getter=http_get, describe=git_describe, out=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", dest="given", help="the version the Setup window shows")
    ap.add_argument("--port", type=int, default=int(os.environ.get("ODDBORO_PORT", "4500")))
    ap.add_argument("--checkout", help="an Oddboro source checkout, for git describe --tags")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    out = out or sys.stdout
    how, text = detect(a.given, a.port, a.checkout, getter, describe)
    f = facts(parse(text))
    f["found_by"] = how
    if a.json:
        out.write(guard(json.dumps(f, indent=2) + "\n"))
    else:
        lines = [f"Oddboro {f['version']} (found by: {how})"]
        lines += [f"  {k}: {v}" for k, v in f.items() if k not in ("version", "found_by")]
        out.write(guard("\n".join(lines) + "\n"))
    return 0 if f.get("supported") else 1


if __name__ == "__main__":
    sys.exit(main())
