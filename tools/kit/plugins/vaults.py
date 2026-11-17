"""Password managers and OS keyrings. Entry names only, and only with --include-vaults.

Without the opt-in, these plug-ins only say whether the tool is present. With it,
they run each tool's own listing command. The kit never signs in, never unlocks,
and never runs a command that decrypts an entry or returns one. Bitwarden's CLI
has no names-only listing (`bw list items` returns whole items), so for Bitwarden
the kit reports presence and lock state only.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from kit.core import FOUND, MISSING, OPT_IN, SKIPPED, UNAVAILABLE, Collector, Ctx, Finding, bounded_glob
from kit.plugins import Plugin

TIMEOUT = 15.0
MAX_ENTRIES = 1000
HOW = "Already in a vault: point the door's manifest at this entry name."


def _which(ctx: Ctx, name: str) -> str | None:
    return shutil.which(name, path=ctx.env.get("PATH", ""))


def _entry(ctx: Ctx, col: Collector, location: str, name: str) -> None:
    col.add(Finding(col.source, location, "vault-entry", ctx.redactor.name(name), key_where=["vault"],
                    auth_kind="stored-secret", how_to_add=HOW))


def _cli(ctx: Ctx, col: Collector, exe: str) -> str | None:
    """Path of the CLI, or None. Records presence and the opt-in state."""
    path = _which(ctx, exe)
    if path is None:
        col.look(f"{exe} on PATH", MISSING)
        return None
    if not ctx.include_vaults:
        col.look(f"{exe} on PATH", OPT_IN)
        return None
    col.look(f"{exe} on PATH", FOUND)
    return path


def scan_onepassword(ctx: Ctx, col: Collector) -> None:
    exe = _cli(ctx, col, "op")
    if not exe:
        return
    out = ctx.runner([exe, "item", "list", "--format", "json"], ctx.env, TIMEOUT)
    try:
        items = json.loads(out) if out else None
    except ValueError:
        items = None
    if not isinstance(items, list):
        col.look("op item list", UNAVAILABLE)
        col.notes.append("1Password CLI is not signed in, or listing failed. Sign in yourself and run the scan again if you want these names.")
        return
    col.look("op item list", FOUND)
    for it in items[:MAX_ENTRIES]:
        if isinstance(it, dict):
            vault = it.get("vault", {}).get("name", "vault") if isinstance(it.get("vault"), dict) else "vault"
            _entry(ctx, col, "1Password", f"{vault}/{it.get('title', 'item')}")


def scan_bitwarden(ctx: Ctx, col: Collector) -> None:
    exe = _cli(ctx, col, "bw")
    if not exe:
        return
    status = ctx.runner([exe, "status"], ctx.env, TIMEOUT)
    try:
        state = json.loads(status).get("status") if status else None
    except (ValueError, AttributeError):
        state = None
    if state != "unlocked":
        col.look("bw status", UNAVAILABLE)
        col.notes.append("Bitwarden CLI is locked or signed out. Unlock it yourself and run the scan again if you want these names.")
        return
    # `bw list items` returns whole items, passwords included. The kit never runs it, and the
    # Bitwarden CLI has no names-only listing, so entry names are left to the person.
    col.look("bw list items", SKIPPED)
    col.notes.append("Bitwarden CLI has no names-only listing, so the kit does not list its entries. "
                     "If the plan needs them, read the entry names yourself in the Bitwarden app.")


def _pass_dir(ctx: Ctx) -> Path:
    return ctx.env_path("PASSWORD_STORE_DIR") or ctx.home / ".password-store"


def scan_pass(ctx: Ctx, col: Collector) -> None:
    d = _pass_dir(ctx)
    if not d.is_dir():
        col.look(d, MISSING)
        return
    if not ctx.include_vaults:
        col.look(d, OPT_IN)
        return
    col.look(d, FOUND)
    for p in bounded_glob(d, "**/*.gpg", MAX_ENTRIES):
        _entry(ctx, col, ctx.show(d), str(p.relative_to(d).with_suffix("")))


def scan_gopass(ctx: Ctx, col: Collector) -> None:
    exe = _cli(ctx, col, "gopass")
    if not exe:
        return
    out = ctx.runner([exe, "ls", "--flat"], ctx.env, TIMEOUT)
    if out is None:
        col.look("gopass ls --flat", UNAVAILABLE)
        return
    for line in out.splitlines()[:MAX_ENTRIES]:
        if line.strip():
            _entry(ctx, col, "gopass", line.strip())


SVC = re.compile(r'^\s*"(svce|srvr|labl)"<blob>="(.*)"\s*$')


def scan_keychain(ctx: Ctx, col: Collector) -> None:
    if ctx.platform != "darwin":
        col.look("macOS keychain", "skipped")
        return
    exe = _cli(ctx, col, "security")
    if not exe:
        return
    out = ctx.runner([exe, "dump-keychain"], ctx.env, TIMEOUT)  # no -d: attributes only, nothing decrypted
    if out is None:
        col.look("security dump-keychain", UNAVAILABLE)
        return
    seen: set[str] = set()
    for line in out.splitlines():
        m = SVC.match(line)
        if m and m.group(2) and m.group(2) not in seen:
            seen.add(m.group(2))
            if len(seen) > MAX_ENTRIES:
                break
            _entry(ctx, col, "macOS keychain", m.group(2))


def scan_cmdkey(ctx: Ctx, col: Collector) -> None:
    if ctx.platform != "windows":
        col.look("Windows Credential Manager", "skipped")
        return
    exe = _cli(ctx, col, "cmdkey")
    if not exe:
        return
    out = ctx.runner([exe, "/list"], ctx.env, TIMEOUT)
    if out is None:
        col.look("cmdkey /list", UNAVAILABLE)
        return
    for line in out.splitlines()[:MAX_ENTRIES * 4]:
        m = re.match(r"^\s*Target:\s*(.+?)\s*$", line)
        if m:
            _entry(ctx, col, "Windows Credential Manager", m.group(1))


OBJ = re.compile(r'"(/org/freedesktop/secrets/[^"]+)"')
LABEL = re.compile(r'^s\s+"(.*)"\s*$')


def scan_secret_service(ctx: Ctx, col: Collector) -> None:
    if ctx.platform != "linux":
        col.look("Secret Service (GNOME Keyring, KWallet)", "skipped")
        return
    exe = _cli(ctx, col, "busctl")
    if not exe:
        return
    base = [exe, "--user"]
    out = ctx.runner(base + ["call", "org.freedesktop.secrets", "/org/freedesktop/secrets",
                             "org.freedesktop.Secret.Service", "SearchItems", "a{ss}", "0"], ctx.env, TIMEOUT)
    if out is None:
        col.look("Secret Service SearchItems", UNAVAILABLE)
        return
    for path in OBJ.findall(out)[:MAX_ENTRIES]:
        label = ctx.runner(base + ["get-property", "org.freedesktop.secrets", path,
                                   "org.freedesktop.Secret.Item", "Label"], ctx.env, TIMEOUT)
        m = LABEL.match((label or "").strip())
        if m and m.group(1):
            _entry(ctx, col, "Secret Service", m.group(1))


PLUGINS = [
    Plugin("1password", "1Password CLI (op item list: titles only)", "vault", lambda ctx: ["op on PATH; op item list --format json"], scan_onepassword, opt_in=True),
    Plugin("bitwarden", "Bitwarden CLI (presence and lock state only; it has no names-only listing)", "vault",
           lambda ctx: ["bw on PATH; bw status"], scan_bitwarden, opt_in=True),
    Plugin("pass", "pass password store (file names only, nothing decrypted)", "vault", lambda ctx: [ctx.show(_pass_dir(ctx)) + "/**/*.gpg"], scan_pass, opt_in=True),
    Plugin("gopass", "gopass (gopass ls --flat)", "vault", lambda ctx: ["gopass on PATH; gopass ls --flat"], scan_gopass, opt_in=True),
    Plugin("keychain", "macOS keychain (attribute names, never decrypted)", "vault", lambda ctx: ["security dump-keychain (no -d)"], scan_keychain, opt_in=True),
    Plugin("windows-credentials", "Windows Credential Manager (target names)", "vault", lambda ctx: ["cmdkey /list"], scan_cmdkey, opt_in=True),
    Plugin("secret-service", "Linux Secret Service (item labels)", "vault", lambda ctx: ["busctl --user: SearchItems, then each item's Label"], scan_secret_service, opt_in=True),
]
