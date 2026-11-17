#!/usr/bin/env python3
"""Move ONE value from a config file into a vault, in one process, without showing it. The person runs this.

  python tools/move_field.py --file ~/.claude.json --field mcpServers.tracker.headers.Authorization \\
      --strip-bearer --to secret-service --entry work/tracker/read-key
  python tools/move_field.py --file .env --field API_KEY --to pass --entry work/api-key --dry-run

It reads the named field here, checks it is one text value, and pipes it on standard input to the
vault's own store command. It never prints, logs or writes the value anywhere else, and it never puts
a value on a command line. A whole file is never stored: prefer a fresh, narrower key from the vendor;
use this only when the old key must move. After the smoke tests pass, remove the old copy yourself.

Fields: a dot path into JSON, JSON with comments, TOML or YAML (`--field-json '["a.b", "c"]'` for keys
with dots), `SECTION.KEY` in an INI file, or `NAME` in a .env or shell file.
Stores that read standard input: secret-service (secret-tool), pass, gopass, hashicorp-vault (`vault kv put <entry> value=-`).
Exit codes: 0 stored (or a dry run found one value), 2 refused, nothing stored.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from kit.core import FOUND, parse, read_text  # noqa: E402
from kit.plugins.environment import pairs  # noqa: E402
from kit.report import GuardTripped, guard  # noqa: E402

STDIN_STORES = {
    "secret-service": lambda e: ["secret-tool", "store", f"--label={e}", "service", "universal-connector", "account", e],
    "pass": lambda e: ["pass", "insert", "--multiline", e],
    "gopass": lambda e: ["gopass", "insert", e],
    "hashicorp-vault": lambda e: ["vault", "kv", "put", e, "value=-"],
}
APP_STORES = {
    "keychain": "macOS Keychain: use the Keychain Access app (its command line takes the value as an argument)",
    "1password": "1Password: create the item in the 1Password app and paste the value there",
    "bitwarden": "Bitwarden: create the item in the Bitwarden app",
    "windows-credentials": "Windows Credential Manager: use the Credential Manager window",
    "aws-secrets-manager": "AWS Secrets Manager: use the console's Store a new secret page",
}
ENTRY_RULE = re.compile(r"[A-Za-z0-9_./-]{1,120}")


class Refused(Exception):
    pass


def find(path: Path, field: list[str]) -> str:
    status, text = read_text(path)
    if text is None:
        raise Refused("the file is missing or not a readable text file")
    suffix = path.suffix.lower()
    name = path.name.lower()
    if name.startswith(".env") or suffix in (".sh", ".bashrc", ".zshrc") or name in (".bashrc", ".zshrc", ".profile"):
        values = [v for k, v in pairs(text) if k == ".".join(field)]
        if len(values) != 1 or not values[0]:
            raise Refused("no such field, or it appears more than once")
        return values[0]
    fmt = {".toml": "toml", ".yaml": "yaml", ".yml": "yaml", ".ini": "ini", ".cfg": "ini", ".conf": "ini"}.get(suffix, "jsonc")
    status, data = parse(text, fmt)
    if status != FOUND:
        raise Refused("the file does not parse")
    if fmt == "ini":
        if len(field) != 2 or not data.has_option(field[0], field[1]):
            raise Refused("no such field (use SECTION.KEY)")
        return data.get(field[0], field[1])
    node = data
    for part in field:
        if isinstance(node, dict) and part in node:
            node = node[part]
        elif isinstance(node, list) and part.isdigit() and int(part) < len(node):
            node = node[int(part)]
        else:
            raise Refused("no such field")
    if not isinstance(node, str) or not node.strip():
        raise Refused("the field is not one text value; only a single value may be moved")
    return node


def main(argv=None, env=None, out=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--file", required=True)
    ap.add_argument("--field", help="a dot path, SECTION.KEY or NAME")
    ap.add_argument("--field-json", help="the path as a JSON list, for keys that hold dots")
    ap.add_argument("--strip-bearer", action="store_true", help="drop a leading 'Bearer ' from the value")
    ap.add_argument("--to", required=True, choices=sorted(STDIN_STORES) + sorted(APP_STORES))
    ap.add_argument("--entry", required=True, help="the vault entry name from the plan, such as work/tracker/read-key")
    ap.add_argument("--dry-run", action="store_true", help="check the field holds one value; store nothing")
    a = ap.parse_args(argv)
    out = out or sys.stdout
    env = dict(os.environ) if env is None else env
    try:
        if a.to in APP_STORES:
            raise Refused(APP_STORES[a.to] + ". This tool never puts a value on a command line")
        if not ENTRY_RULE.fullmatch(a.entry):
            raise Refused("the entry name may hold letters, digits and . _ / - only")
        field = json.loads(a.field_json) if a.field_json else (a.field or "").split(".")
        if not field or not all(isinstance(p, str) and p for p in field):
            raise Refused("give --field or --field-json")
        value = find(Path(a.file).expanduser(), field)
        if a.strip_bearer:
            value = re.sub(r"(?i)^\s*bearer\s+", "", value)
        value = value.strip()
        if "\n" in value or not value:
            raise Refused("the value is empty or spans lines")
        if a.dry_run:
            out.write(guard(f"dry run: found one text value at the field; it would go to {a.to} as {a.entry}. Nothing stored.\n"))
            return 0
        argv_store = STDIN_STORES[a.to](a.entry)
        exe = shutil.which(argv_store[0], path=env.get("PATH", ""))
        if not exe:
            raise Refused(f"{argv_store[0]} is not on PATH")
        done = subprocess.run([exe, *argv_store[1:]], input=value.encode(), env=env, stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, timeout=60, check=False)
        del value
        if done.returncode != 0:
            raise Refused(f"{argv_store[0]} did not store it (it may already exist, or the store is locked)")
        out.write(guard(f"stored one value in {a.to} as {a.entry}. Remove the old copy from the file yourself after the smoke tests pass.\n"))
        return 0
    except Refused as exc:
        out.write(guard(f"refused: {exc}. Nothing was stored.\n"))
        return 2
    except (ValueError, OSError, subprocess.SubprocessError, GuardTripped):
        out.write("refused: the field or the store could not be used. Nothing was stored.\n")
        return 2


if __name__ == "__main__":
    sys.exit(main())
