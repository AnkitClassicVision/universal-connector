#!/usr/bin/env python3
"""Add the door entry to ONE harness config without opening it in an editor or printing it.

  python tools/add_entry.py --harness codex --config ~/.codex/config.toml \\
      --url http://127.0.0.1:8765/mcp --key-env CODEX_DOOR_KEY --backup-dir <run folder>/05c-connect-codex/backup

  python tools/add_entry.py --harness zed --config ~/.config/zed/settings.json --url https://... \\
      --key-file <0600 file with Zed's door key> --backup-dir <run folder>/05g-connect-zed/backup --allow-rewrite

Use the harness's own command where it has one (`claude mcp add-json`, `codex mcp add`). Use this tool
where it does not. It backs the config up into the run folder (0700 folder, 0600 file, never beside
the config), adds one entry, checks the result, and replaces the file atomically. Harnesses that keep
the door key in their own config (Zed, Goose, OpenMausBot, Cline, and Cursor or Windsurf without
${env:...}) take --key-file: the key is written into the entry here and never shown.
Exit codes: 0 added (or a dry run passed), 2 refused, nothing changed.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from kit.add_entry import FORMATS, Refused, run  # noqa: E402
from kit.report import GuardTripped, guard  # noqa: E402


class _Guarded:
    def __init__(self, out) -> None:
        self.out = out

    def write(self, text: str) -> None:
        self.out.write(guard(text))


def main(argv=None, out=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--harness", required=True, choices=sorted(FORMATS))
    ap.add_argument("--config", required=True, help="the harness's config file (it may not exist yet)")
    ap.add_argument("--url", required=True, help="the door address this harness uses")
    ap.add_argument("--backup-dir", required=True, help="a folder in the run folder, for the owner-only backup")
    ap.add_argument("--name", default="door", help="the entry name (short: it is part of every tool name)")
    ap.add_argument("--key-env", default="DOOR_KEY", help="the variable the harness reads the key from, where it can")
    ap.add_argument("--key-file", help="a 0600 file with this harness's door key, for harnesses that keep the key in their config")
    ap.add_argument("--bridge-command", help="Claude Desktop: the local bridge program that adds the header")
    ap.add_argument("--read-timeout", type=int, default=120, help="seconds, where the entry carries a timeout")
    ap.add_argument("--replace", action="store_true", help="replace an entry with the same name")
    ap.add_argument("--allow-rewrite", action="store_true", help="allow writing the file back whole (comments are lost)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    out = out or sys.stdout
    try:
        return run(a, _Guarded(out))
    except Refused as exc:
        out.write(f"refused: {exc}\n")
        return 2
    except GuardTripped:
        out.write("refused: the output matched a key-shape rule; please report this as a bug\n")
        return 2
    except OSError:
        out.write("refused: a file could not be read or written; nothing was changed\n")
        return 2


if __name__ == "__main__":
    sys.exit(main())
