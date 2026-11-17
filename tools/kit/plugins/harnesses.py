"""Agent harness configs: the MCP servers each one already has, names only."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from kit.classify import CRED_WORD, PLAIN, how_to_add, value_kind
from kit.core import FOUND, MISSING, Collector, Ctx, Finding, bounded_glob, load
from kit.plugins import Plugin, add_servers, shown

VSCODE_VARIANTS = ("Code", "Code - Insiders", "VSCodium")


def _projects(ctx: Ctx) -> list[Path]:
    seen, out = set(), []
    for p in ctx.projects:
        if str(p) not in seen:
            seen.add(str(p))
            out.append(p)
    return out


def _project_files(ctx: Ctx, col: Collector, rel: str, fmt: str, key: str, extra: list[Path] = ()) -> None:
    """A per-project file. Listed projects are always reported; followed ones only when present."""
    for proj in _projects(ctx) + [p for p in extra if str(p) not in {str(x) for x in ctx.projects}]:
        path = proj / rel
        if proj not in ctx.projects and not path.is_file():
            continue
        data = load(col, path, fmt)
        if isinstance(data, dict):
            add_servers(ctx, col, data.get(key), shown(ctx, path))


def _settings_env(ctx: Ctx, col: Collector, data: Any, location: str) -> None:
    """Names of credential-looking variables in a settings `env` block, plus an API key helper."""
    if not isinstance(data, dict):
        return
    env = data.get("env")
    if isinstance(env, dict):
        for name, value in env.items():
            vk = value_kind(value, str(name))
            if vk is None and not CRED_WORD.search(str(name)):
                continue
            where = [vk or "inline"]
            f = Finding(col.source, location, "settings-env", ctx.redactor.field(name), key_where=where,
                        auth_kind="api-key", plain_file=bool(set(where) & PLAIN))
            f.how_to_add = how_to_add(Finding(col.source, location, "env-var", f.name, key_where=where))
            col.add(f)
    if isinstance(data.get("apiKeyHelper"), str):
        col.add(Finding(col.source, location, "cli-login", "apiKeyHelper", command=ctx.redactor.command(data["apiKeyHelper"].split()[0] if data["apiKeyHelper"].split() else "helper"),
                        key_where=["helper"], auth_kind="api-key", how_to_add="A helper program supplies this key; leave it with the harness."))


# ------------------------------------------------------------------ Claude Code


def _cc_main(ctx: Ctx) -> tuple[Path, Path]:
    base = ctx.env_path("CLAUDE_CONFIG_DIR")
    return ((base / ".claude.json") if base else ctx.home / ".claude.json"), (base or ctx.home / ".claude")


def _managed(ctx: Ctx) -> Path:
    if ctx.platform == "darwin":
        return ctx.sys_path("/Library/Application Support/ClaudeCode/managed-mcp.json")
    if ctx.platform == "windows":
        return (ctx.env_path("PROGRAMDATA") or ctx.sys_path("/ProgramData")) / "ClaudeCode" / "managed-mcp.json"
    return ctx.sys_path("/etc/claude-code/managed-mcp.json")


def where_claude_code(ctx: Ctx) -> list[str]:
    main, cdir = _cc_main(ctx)
    return [ctx.show(main) + " (mcpServers, projects.*.mcpServers)", "<each project>/.mcp.json",
            ctx.show(cdir / "settings.json") + " (env names, apiKeyHelper)", "<each project>/.claude/settings*.json (env names)",
            ctx.show(cdir / "plugins") + "/**/.mcp.json", ctx.show(cdir / ".credentials.json") + " (names of servers with an OAuth sign-in)",
            ctx.show(_managed(ctx))]


def scan_claude_code(ctx: Ctx, col: Collector) -> None:
    main, cdir = _cc_main(ctx)
    follow: list[Path] = []
    data = load(col, main, "json")
    if isinstance(data, dict):
        add_servers(ctx, col, data.get("mcpServers"), shown(ctx, main) + " mcpServers")
        projects = data.get("projects")
        if isinstance(projects, dict):
            for ppath, pdata in sorted(projects.items()):
                if isinstance(pdata, dict):
                    add_servers(ctx, col, pdata.get("mcpServers"), shown(ctx, main) + f" projects[{shown(ctx, Path(ppath))}]")
                absolute = isinstance(ppath, str) and (ppath.startswith(("/", "~")) or (len(ppath) > 2 and ppath[1] == ":"))
                if ctx.follow_projects and absolute:
                    follow.append(ctx.home / ppath[2:] if ppath.startswith("~/") else Path(ppath))
    _project_files(ctx, col, ".mcp.json", "json", "mcpServers", follow)
    _settings_env(ctx, col, load(col, cdir / "settings.json", "json"), shown(ctx, cdir / "settings.json"))
    for proj in _projects(ctx):
        for rel in (".claude/settings.json", ".claude/settings.local.json"):
            p = proj / rel
            if p.is_file():
                _settings_env(ctx, col, load(col, p, "json"), shown(ctx, p))
    plugin_files = bounded_glob(cdir / "plugins", "**/.mcp.json", 100)
    col.look(cdir / "plugins", FOUND if plugin_files else MISSING)
    for p in plugin_files:
        pdata = load(col, p, "json")
        if isinstance(pdata, dict):
            add_servers(ctx, col, pdata.get("mcpServers", pdata), shown(ctx, p))
    creds = load(col, cdir / ".credentials.json", "json")
    if isinstance(creds, dict) and isinstance(creds.get("mcpOAuth"), dict):
        for key in sorted(creds["mcpOAuth"]):
            name = str(key).split("|")[0]
            col.add(Finding(col.source, shown(ctx, cdir / ".credentials.json"), "oauth-sign-in", ctx.redactor.name(name),
                            key_where=["file", "oauth"], auth_kind="oauth", plain_file=True,
                            how_to_add="This harness holds its own OAuth sign-in for this server. Leave it; the door gets its own sign-in."))
    managed = load(col, _managed(ctx), "json")
    if isinstance(managed, dict):
        add_servers(ctx, col, managed.get("mcpServers"), shown(ctx, _managed(ctx)))


# --------------------------------------------------------------- Claude Desktop


def _desktop_dir(ctx: Ctx) -> Path:
    return ctx.app_support() / "Claude"


def where_claude_desktop(ctx: Ctx) -> list[str]:
    d = _desktop_dir(ctx)
    return [ctx.show(d / "claude_desktop_config.json"), ctx.show(d / "Claude Extensions") + "/* (extension names)",
            ctx.show(d / "Claude Extensions Settings") + "/*.json (whether a key is stored)"]


def scan_claude_desktop(ctx: Ctx, col: Collector) -> None:
    d = _desktop_dir(ctx)
    data = load(col, d / "claude_desktop_config.json", "json")
    if isinstance(data, dict):
        add_servers(ctx, col, data.get("mcpServers"), shown(ctx, d / "claude_desktop_config.json"))
    ext = d / "Claude Extensions"
    col.look(ext, FOUND if ext.is_dir() else MISSING)
    if ext.is_dir():
        settings = d / "Claude Extensions Settings"
        for folder in sorted(p for p in ext.iterdir() if p.is_dir())[:200]:
            where = ["unknown"]
            sfile = settings / f"{folder.name}.json"
            if sfile.is_file():
                sdata = load(col, sfile, "json")
                found: set[str] = set()
                _walk_settings(sdata, found)
                where = sorted(found) or ["none"]
            f = Finding(col.source, shown(ctx, ext), "desktop-extension", ctx.redactor.name(folder.name), transport="stdio",
                        key_where=where, auth_kind="api-key" if set(where) & {"inline", "file", "env-reference"} else "none-found",
                        plain_file=bool(set(where) & PLAIN))
            f.how_to_add = "Desktop extension: check what it connects to; if it holds a key, move that connection behind the door."
            col.add(f)


def _walk_settings(value: Any, found: set[str], key: str = "") -> None:
    if isinstance(value, dict):
        for k, v in value.items():
            _walk_settings(v, found, str(k))
    elif isinstance(value, list):
        for v in value:
            _walk_settings(v, found, key)
    else:
        vk = value_kind(value, key)
        if vk:
            found.add("file" if vk == "inline" else vk)


# ------------------------------------------------------------------------ Codex


def _codex_home(ctx: Ctx) -> Path:
    return ctx.env_path("CODEX_HOME") or ctx.home / ".codex"


def where_codex(ctx: Ctx) -> list[str]:
    h = _codex_home(ctx)
    return [ctx.show(h / "config.toml") + " (mcp_servers)", "<each project>/.codex/config.toml",
            ctx.show(h / "auth.json") + " (sign-in kind only)"]


def codex_auth(ctx: Ctx, col: Collector, path: Path) -> None:
    data = load(col, path, "json")
    if not isinstance(data, dict):
        return
    has_key = bool(data.get("OPENAI_API_KEY"))
    has_tokens = isinstance(data.get("tokens"), dict) and bool(data["tokens"])
    if has_key or has_tokens:
        col.add(Finding(col.source, shown(ctx, path), "cli-login", "codex sign-in", key_where=["file"],
                        auth_kind="api-key" if has_key else "oauth", plain_file=True,
                        how_to_add="The harness's own sign-in. Leave it in place; it is not a door connection."))


def codex_config(ctx: Ctx, col: Collector, path: Path) -> None:
    data = load(col, path, "toml")
    if isinstance(data, dict):
        add_servers(ctx, col, data.get("mcp_servers"), shown(ctx, path))


def scan_codex(ctx: Ctx, col: Collector) -> None:
    h = _codex_home(ctx)
    codex_config(ctx, col, h / "config.toml")
    _project_files(ctx, col, ".codex/config.toml", "toml", "mcp_servers")
    codex_auth(ctx, col, h / "auth.json")


# -------------------------------------------------------------- Cursor, Windsurf


def where_cursor(ctx: Ctx) -> list[str]:
    return [ctx.show(ctx.home / ".cursor" / "mcp.json"), "<each project>/.cursor/mcp.json"]


def scan_cursor(ctx: Ctx, col: Collector) -> None:
    p = ctx.home / ".cursor" / "mcp.json"
    data = load(col, p, "json")
    if isinstance(data, dict):
        add_servers(ctx, col, data.get("mcpServers"), shown(ctx, p))
    _project_files(ctx, col, ".cursor/mcp.json", "json", "mcpServers")


def _windsurf_paths(ctx: Ctx) -> list[Path]:
    base = ctx.home / ".codeium"
    return [base / "windsurf" / "mcp_config.json", base / "windsurf-next" / "mcp_config.json", base / "mcp_config.json"]


def scan_windsurf(ctx: Ctx, col: Collector) -> None:
    for p in _windsurf_paths(ctx):
        data = load(col, p, "json")
        if isinstance(data, dict):
            add_servers(ctx, col, data.get("mcpServers"), shown(ctx, p))


# ----------------------------------------------------- VS Code, Cline, Continue


def _vscode_users(ctx: Ctx) -> list[Path]:
    return [ctx.app_support() / v / "User" for v in VSCODE_VARIANTS]


def where_vscode(ctx: Ctx) -> list[str]:
    out = []
    for u in _vscode_users(ctx):
        out += [ctx.show(u / "mcp.json") + " (servers)", ctx.show(u / "settings.json") + " (mcp.servers)"]
    return out + ["<each project>/.vscode/mcp.json"]


def scan_vscode(ctx: Ctx, col: Collector) -> None:
    for u in _vscode_users(ctx):
        data = load(col, u / "mcp.json", "jsonc")
        if isinstance(data, dict):
            add_servers(ctx, col, data.get("servers"), shown(ctx, u / "mcp.json"))
        settings = load(col, u / "settings.json", "jsonc")
        if isinstance(settings, dict):
            mcp = settings.get("mcp")
            servers = mcp.get("servers") if isinstance(mcp, dict) else settings.get("mcp.servers")
            add_servers(ctx, col, servers, shown(ctx, u / "settings.json") + " mcp")
    _project_files(ctx, col, ".vscode/mcp.json", "jsonc", "servers")


CLINE_FILES = ("saoudrizwan.claude-dev/settings/cline_mcp_settings.json", "rooveterinaryinc.roo-cline/settings/mcp_settings.json")


def where_cline(ctx: Ctx) -> list[str]:
    return [ctx.show(u / "globalStorage" / f) for u in _vscode_users(ctx)[:1] for f in CLINE_FILES] + [
        "(the same under Code - Insiders and VSCodium)"]


def scan_cline(ctx: Ctx, col: Collector) -> None:
    for u in _vscode_users(ctx):
        for rel in CLINE_FILES:
            p = u / "globalStorage" / rel
            data = load(col, p, "json")
            if isinstance(data, dict):
                add_servers(ctx, col, data.get("mcpServers"), shown(ctx, p))


def where_continue(ctx: Ctx) -> list[str]:
    c = ctx.home / ".continue"
    return [ctx.show(c / "config.yaml") + " (mcpServers)", ctx.show(c / "config.json") + " (experimental.modelContextProtocolServers)",
            ctx.show(c / "mcpServers") + "/*.yaml|*.json", "<each project>/.continue/mcpServers/*"]


def _continue_block(ctx: Ctx, col: Collector, p: Path) -> None:
    data = load(col, p, "yaml" if p.suffix in (".yaml", ".yml") else "json")
    if isinstance(data, dict):
        add_servers(ctx, col, data.get("mcpServers"), shown(ctx, p))


def scan_continue(ctx: Ctx, col: Collector) -> None:
    c = ctx.home / ".continue"
    _continue_block(ctx, col, c / "config.yaml")
    data = load(col, c / "config.json", "json")
    if isinstance(data, dict):
        exp = data.get("experimental")
        servers = exp.get("modelContextProtocolServers") if isinstance(exp, dict) else None
        add_servers(ctx, col, servers, shown(ctx, c / "config.json"))
    for base in [c] + [p / ".continue" for p in _projects(ctx)]:
        for p in bounded_glob(base / "mcpServers", "*", 100):
            if p.suffix in (".yaml", ".yml", ".json"):
                _continue_block(ctx, col, p)


# ------------------------------------------------------------------ Zed, Goose


def _zed_settings(ctx: Ctx) -> Path:
    return (ctx.appdata() / "Zed" / "settings.json") if ctx.platform == "windows" else ctx.xdg_config() / "zed" / "settings.json"


def scan_zed(ctx: Ctx, col: Collector) -> None:
    p = _zed_settings(ctx)
    data = load(col, p, "jsonc")
    if isinstance(data, dict):
        add_servers(ctx, col, data.get("context_servers"), shown(ctx, p))
    _project_files(ctx, col, ".zed/settings.json", "jsonc", "context_servers")


def _goose_dir(ctx: Ctx) -> Path:
    return (ctx.appdata() / "Block" / "goose" / "config") if ctx.platform == "windows" else ctx.xdg_config() / "goose"


def scan_goose(ctx: Ctx, col: Collector) -> None:
    d = _goose_dir(ctx)
    data = load(col, d / "config.yaml", "yaml")
    if isinstance(data, dict):
        add_servers(ctx, col, data.get("extensions"), shown(ctx, d / "config.yaml"))
    secrets = load(col, d / "secrets.yaml", "yaml")
    if isinstance(secrets, dict):
        for name in sorted(secrets):
            col.add(Finding(col.source, shown(ctx, d / "secrets.yaml"), "env-file-var", ctx.redactor.field(name),
                            key_where=["file"], auth_kind="api-key", plain_file=True,
                            how_to_add=how_to_add(Finding(col.source, "", "env-var", "", key_where=["file"]))))


# ----------------------------------------------------------------------- Hermes


def _hermes_home(ctx: Ctx) -> Path:
    return ctx.env_path("HERMES_HOME") or ctx.home / ".hermes"


def where_hermes(ctx: Ctx) -> list[str]:
    h = _hermes_home(ctx)
    return [ctx.show(h / "config.yaml") + " (mcp_servers)", ctx.show(h / "profiles") + "/*/config.yaml",
            ctx.show(h / ".env") + " (variable names)", ctx.show(h / "profiles") + "/*/.env (variable names)"]


def env_file(ctx: Ctx, col: Collector, path: Path) -> None:
    from kit.plugins.environment import env_file_findings

    env_file_findings(ctx, col, path)


def scan_hermes(ctx: Ctx, col: Collector) -> None:
    h = _hermes_home(ctx)
    homes = [h] + sorted(p for p in bounded_glob(h / "profiles", "*", 100) if p.is_dir())
    for home in homes:
        data = load(col, home / "config.yaml", "yaml")
        if isinstance(data, dict):
            add_servers(ctx, col, data.get("mcp_servers"), shown(ctx, home / "config.yaml"))
        env_file(ctx, col, home / ".env")


# ------------------------------------------------------------------ OpenMausBot


def _mausbot_paths(ctx: Ctx) -> list[Path]:
    out = list(ctx.extra.get("openmausbot", []))
    base = ctx.env_path("OPENMAUSBOT_HOME")
    if base:
        out += [base / "data" / "config.json", base / "config.json"]
    out += [ctx.home / ".openmausbot" / "config.json", ctx.home / ".openmausbot" / "data" / "config.json",
            ctx.home / "openmausbot" / "data" / "config.json"]
    return out


def scan_openmausbot(ctx: Ctx, col: Collector) -> None:
    for p in _mausbot_paths(ctx):
        data = load(col, p, "json")
        if isinstance(data, dict):
            add_servers(ctx, col, data.get("mcpServers"), shown(ctx, p))


# ---------------------------------------------------------------------- Oddboro


def _oddboro_home(ctx: Ctx) -> Path:
    return ctx.env_path("ODDBORO_HOME") or ctx.home / ".oddboro"


def where_oddboro(ctx: Ctx) -> list[str]:
    h = _oddboro_home(ctx)
    return [ctx.show(h) + " (office home: present or not)", ctx.show(h / ".env") + " (variable names)",
            ctx.show(h / "accounts") + "/<tool>/<account>/ (each tool account's own MCP config)",
            "Services tab (the service list is in the office database; the interview records the names)"]


def scan_oddboro(ctx: Ctx, col: Collector) -> None:
    h = _oddboro_home(ctx)
    col.look(h, FOUND if h.is_dir() else MISSING)
    if not h.is_dir():
        return
    env_file(ctx, col, h / ".env")
    homes: list[tuple[str, Path]] = []
    for tool_dir in bounded_glob(h / "accounts", "*", 50):
        for acct in bounded_glob(tool_dir, "*", 50):
            if acct.is_dir():
                homes.append((tool_dir.name, acct))
    for legacy in ("grok", "codex"):
        if (h / legacy).is_dir():
            homes.append((legacy, h / legacy))
    for tool, acct in homes:
        col.add(Finding(col.source, shown(ctx, acct.parent), "account-home", ctx.redactor.name(f"{tool}/{acct.name}"),
                        key_where=["file"], auth_kind="oauth", plain_file=False,
                        how_to_add="A coding tool's account inside the office. Its own MCP servers are listed below it."))
        if tool == "codex":
            codex_config(ctx, col, acct / "config.toml")
            codex_auth(ctx, col, acct / "auth.json")
        elif tool == "claude":
            data = load(col, acct / ".claude.json", "json")
            if isinstance(data, dict):
                add_servers(ctx, col, data.get("mcpServers"), shown(ctx, acct / ".claude.json"))
        elif tool == "grok":
            grok_config(ctx, col, acct / "config.toml")
    col.notes.append("Oddboro keeps its service list in the office database. Read the names from the Services tab.")


# ---------------------------------------------------------------------- GrokBot


def grok_config(ctx: Ctx, col: Collector, path: Path) -> None:
    data = load(col, path, "toml")
    if not isinstance(data, dict):
        return
    servers = data.get("mcp_servers")
    if servers is None:
        for key in sorted(data, key=str):
            table = data[key]
            if "mcp" in str(key).lower() and isinstance(table, dict):
                servers = table.get("servers", table)
                break
    add_servers(ctx, col, servers, shown(ctx, path))


def _grok_home(ctx: Ctx) -> Path:
    return ctx.env_path("GROK_HOME") or ctx.home / ".grok"


def scan_grokbot(ctx: Ctx, col: Collector) -> None:
    grok_config(ctx, col, _grok_home(ctx) / "config.toml")
    col.notes.append("GrokBot's CLI also reads Claude Code's MCP list. Its desktop app keeps logins on the vendor's servers.")


# --------------------------------------------------------- any other JSON/TOML/YAML


def where_extra(ctx: Ctx) -> list[str]:
    return ["files given with --extra mcp=PATH (keys mcpServers, servers, mcp_servers, context_servers, extensions)"]


def scan_extra(ctx: Ctx, col: Collector) -> None:
    for p in ctx.extra.get("mcp", []):
        fmt = {".toml": "toml", ".yaml": "yaml", ".yml": "yaml"}.get(p.suffix.lower(), "jsonc")
        data = load(col, p, fmt)
        if isinstance(data, dict):
            for key in ("mcpServers", "servers", "mcp_servers", "context_servers", "extensions"):
                add_servers(ctx, col, data.get(key), shown(ctx, p) + f" {key}")


def _paths_where(fn):
    return lambda ctx: [ctx.show(p) for p in fn(ctx)]


PLUGINS = [
    Plugin("claude-code", "Claude Code", "harness", where_claude_code, scan_claude_code),
    Plugin("claude-desktop", "Claude Desktop", "harness", where_claude_desktop, scan_claude_desktop),
    Plugin("codex", "Codex", "harness", where_codex, scan_codex),
    Plugin("cursor", "Cursor", "harness", where_cursor, scan_cursor),
    Plugin("windsurf", "Windsurf", "harness", _paths_where(_windsurf_paths), scan_windsurf),
    Plugin("vscode", "VS Code (native MCP)", "harness", where_vscode, scan_vscode),
    Plugin("cline", "Cline and Roo Code (VS Code)", "harness", where_cline, scan_cline),
    Plugin("continue", "Continue (VS Code, JetBrains)", "harness", where_continue, scan_continue),
    Plugin("zed", "Zed", "harness", lambda ctx: [ctx.show(_zed_settings(ctx)) + " (context_servers)", "<each project>/.zed/settings.json"], scan_zed),
    Plugin("goose", "Goose", "harness", lambda ctx: [ctx.show(_goose_dir(ctx) / "config.yaml") + " (extensions)",
                                                    ctx.show(_goose_dir(ctx) / "secrets.yaml") + " (names)"], scan_goose),
    Plugin("hermes", "Hermes", "harness", where_hermes, scan_hermes),
    Plugin("openmausbot", "OpenMausBot", "harness", _paths_where(_mausbot_paths), scan_openmausbot),
    Plugin("oddboro", "Oddboro", "harness", where_oddboro, scan_oddboro),
    Plugin("grokbot", "GrokBot", "harness", lambda ctx: [ctx.show(_grok_home(ctx) / "config.toml") + " (mcp_servers)",
                                                        "Claude Code's list (read by the CLI)"], scan_grokbot),
    Plugin("extra", "Other MCP config files you name", "harness", where_extra, scan_extra),
]
