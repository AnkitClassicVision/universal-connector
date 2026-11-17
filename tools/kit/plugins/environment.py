"""Environment variables, .env files and shell profiles. Variable names only."""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

from kit.classify import CRED_WORD, SERVICE_ACCOUNT, how_to_add, value_kind
from kit.core import FOUND, MISSING, Collector, Ctx, Finding, bounded_glob, read_text
from kit.plugins import Plugin, shown

NOT_SECRETS = re.compile(
    r"^(SSH_AUTH_SOCK|XAUTHORITY|DESKTOP_SESSION|SESSION_MANAGER|GNOME_DESKTOP_SESSION_ID|"
    r"XDG_.*|DBUS_.*|KDE_.*|GPG_AGENT_INFO|WINDOWID|.*_SOCK|.*_PID|SHLVL|TERM_SESSION_ID|"
    r"MCP_TIMEOUT|MCP_TOOL_TIMEOUT|.*_TIMEOUT)$"
)
SHELL_FILES = (".bashrc", ".bash_profile", ".profile", ".zshrc", ".zshenv", ".zprofile", ".config/fish/config.fish")
VAULT_SUBST = re.compile(r"(?i)\$\(\s*(op|bw|pass|gopass|vault|aws\s+secretsmanager|doppler|infisical)\b")
KEYRING_SUBST = re.compile(r"(?i)\$\(\s*(security|secret-tool|keyring)\b")
PAIR = re.compile(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$")
FISH = re.compile(r"^set\s+-[a-zA-Z]+\s+([A-Za-z_][A-Za-z0-9_]*)\s+(.*)$")
PS = re.compile(r"^\$env:([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$", re.I)


def pairs(text: str) -> Iterator[tuple[str, str]]:
    """(name, value) from .env, shell and PowerShell lines. Values stay in this process."""
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = PAIR.match(line) or FISH.match(line) or PS.match(line)
        if m:
            yield m.group(1), m.group(2).strip().strip("\"'")


def _where(name: str, value: str, default: str) -> list[str]:
    if VAULT_SUBST.search(value):
        return ["vault"]
    if KEYRING_SUBST.search(value):
        return ["keyring"]
    vk = value_kind(value, name)
    if vk in ("env-reference", "vault", "keyring", "prompt"):
        return [vk]
    if vk == "file" or SERVICE_ACCOUNT.search(name):
        return ["file"]
    return [default]


def _finding(ctx: Ctx, col: Collector, location: str, kind: str, name: str, where: list[str]) -> Finding:
    auth = "service-account" if SERVICE_ACCOUNT.search(name) else "api-key"
    f = Finding(col.source, location, kind, ctx.redactor.field(name), key_where=where, auth_kind=auth,
                plain_file="file" in where and kind != "env-var")
    f.how_to_add = how_to_add(f)
    return f


def env_file_findings(ctx: Ctx, col: Collector, path: Path, only_credish: bool = False) -> None:
    status, text = read_text(path)
    col.look(path, status)
    if text is None:
        return
    for name, value in pairs(text):
        if not value:
            continue
        if (only_credish or value_kind(value, name) is None) and not CRED_WORD.search(name):
            continue  # a plain setting such as LOG_LEVEL=info, not a credential
        col.add(_finding(ctx, col, shown(ctx, path), "env-file-var", name, _where(name, value, "file")))


def where_env(ctx: Ctx) -> list[str]:
    return ["the environment this scan runs in (credential-looking names only)"]


def scan_env(ctx: Ctx, col: Collector) -> None:
    col.look("process environment", FOUND)
    for name in sorted(ctx.env):
        if NOT_SECRETS.match(name) or not CRED_WORD.search(name):
            continue
        col.add(_finding(ctx, col, "process environment", "env-var", name, _where(name, ctx.env[name], "environment")))


def where_env_files(ctx: Ctx) -> list[str]:
    return [ctx.show(ctx.home / ".env"), "<each project>/.env and .env.* (all variable names)"]


def scan_env_files(ctx: Ctx, col: Collector) -> None:
    env_file_findings(ctx, col, ctx.home / ".env")
    for proj in ctx.projects:
        files = [p for p in bounded_glob(proj, ".env*", 50) if p.is_file()]
        col.look(proj / ".env*", FOUND if files else MISSING)
        for p in files:
            env_file_findings(ctx, col, p)


def _shell_files(ctx: Ctx) -> list[Path]:
    out = [ctx.home / rel for rel in SHELL_FILES]
    out += bounded_glob(ctx.xdg_config() / "environment.d", "*.conf", 50)
    docs = ctx.home / "Documents"
    out += [docs / "PowerShell" / "Microsoft.PowerShell_profile.ps1", docs / "WindowsPowerShell" / "Microsoft.PowerShell_profile.ps1"]
    return out


def scan_shell(ctx: Ctx, col: Collector) -> None:
    for p in _shell_files(ctx):
        status, text = read_text(p)
        if status == MISSING:
            col.look(p, status)
            continue
        col.look(p, status)
        if text is None:
            continue
        for name, value in pairs(text):
            if value and CRED_WORD.search(name) and not NOT_SECRETS.match(name):
                col.add(_finding(ctx, col, shown(ctx, p), "shell-profile-var", name, _where(name, value, "file")))


PLUGINS = [
    Plugin("env", "Environment variables", "environment", where_env, scan_env),
    Plugin("env-files", ".env files", "environment", where_env_files, scan_env_files),
    Plugin("shell-profiles", "Shell profiles (exported credential names)", "environment",
           lambda ctx: [ctx.show(p) for p in _shell_files(ctx)], scan_shell),
]
