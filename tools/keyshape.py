#!/usr/bin/env python3
"""Scan files for key-shaped strings. Prints file, line and rule name, never the text.

  python tools/keyshape.py .                 # every file under the folder; .git is left out
  python tools/keyshape.py out/ --quiet      # only the count

Run it over everything you are about to commit or share. Exit 1 when anything matches, or when a
file could not be checked (a link, a file over 5 MB, an unreadable file); those are listed as skipped.
Tool folders it does not read (.venv, node_modules, __pycache__, .pytest_cache, .ruff_cache) are
listed as skipped too and also make the exit 1: scan a clean export (`git archive`) for a pass.
Text is read as UTF-8, UTF-16 (with a byte-order mark) or Latin-1.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from kit.keyshape import file_line_hits  # noqa: E402

QUIET_DIRS = {".git"}  # version-control internals: left out without a note
LISTED_DIRS = {"__pycache__", ".venv", "node_modules", ".pytest_cache", ".ruff_cache"}  # not read, and reported
MAX_BYTES = 5_000_000


def files_under(paths: list[str], skipped: list[tuple[str, str]] | None = None):
    for raw in paths:
        p = Path(raw)
        if p.is_file() or p.is_symlink():
            yield p
            continue
        for dirpath, dirnames, filenames in os.walk(p, followlinks=False):
            for d in sorted(dirnames):
                if d in LISTED_DIRS and skipped is not None:
                    skipped.append((str(Path(dirpath) / d), f"a {d} folder (not read)"))
            dirnames[:] = sorted(d for d in dirnames if d not in QUIET_DIRS | LISTED_DIRS)
            for name in sorted(filenames):
                yield Path(dirpath) / name


def decode(data: bytes) -> str:
    """UTF-8 first; UTF-16 when it carries a byte-order mark; else Latin-1, which reads any bytes."""
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            return data.decode("utf-16")
        except UnicodeDecodeError:
            pass
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def scan(paths: list[str]) -> tuple[list[tuple[str, int, str]], list[tuple[str, str]]]:
    """(hits, skipped). A file that cannot be checked is reported, never passed silently."""
    hits, skipped = [], []
    for f in files_under(paths, skipped):
        try:
            if f.is_symlink():
                skipped.append((str(f), "a link (not followed)"))
                continue
            if not f.is_file():
                skipped.append((str(f), "not a regular file"))
                continue
            if f.stat().st_size > MAX_BYTES:
                skipped.append((str(f), "over 5 MB"))
                continue
            text = decode(f.read_bytes())
        except OSError:
            skipped.append((str(f), "unreadable"))
            continue
        hits += [(str(f), line, rule) for line, rule in file_line_hits(f.name, text)]
    return hits, skipped


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args(argv)
    hits, skipped = scan(a.paths)
    if not a.quiet:
        for path, line, rule in hits:
            sys.stdout.write(f"{path}:{line}: {rule}\n")
        for path, why in skipped:
            sys.stdout.write(f"{path}: skipped, {why}\n")
    sys.stdout.write(f"{len(hits)} key-shaped line(s), {len(skipped)} file(s) skipped\n")
    return 1 if hits or skipped else 0


if __name__ == "__main__":
    sys.exit(main())
