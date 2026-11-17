#!/usr/bin/env python3
"""Scan files for key-shaped strings. Prints file, line and rule name, never the text.

  python tools/keyshape.py .                 # every file under the folder, .git skipped
  python tools/keyshape.py out/ --quiet      # only the count

Run it over everything you are about to commit or share. Exit 1 when anything matches.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from kit.keyshape import line_hits  # noqa: E402

SKIP_DIRS = {".git", "__pycache__", ".venv", "node_modules", ".pytest_cache", ".ruff_cache"}
MAX_BYTES = 5_000_000


def files_under(paths: list[str]):
    for raw in paths:
        p = Path(raw)
        if p.is_file():
            yield p
            continue
        for dirpath, dirnames, filenames in os.walk(p, followlinks=False):
            dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
            for name in sorted(filenames):
                yield Path(dirpath) / name


def scan(paths: list[str]) -> list[tuple[str, int, str]]:
    hits = []
    for f in files_under(paths):
        try:
            if f.is_symlink() or f.stat().st_size > MAX_BYTES:
                continue
            text = f.read_bytes().decode("utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        hits += [(str(f), line, rule) for line, rule in line_hits(text)]
    return hits


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args(argv)
    hits = scan(a.paths)
    if not a.quiet:
        for path, line, rule in hits:
            sys.stdout.write(f"{path}:{line}: {rule}\n")
    sys.stdout.write(f"{len(hits)} key-shaped line(s)\n")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
