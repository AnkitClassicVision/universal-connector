"""One table of every harness the kit knows: where its config lives, how it takes a
remote MCP server, and its known limits. The scanner, `entry.py`, the smoke tests
and the options guide all read this table, so they cannot drift apart.

`confidence` says where a row came from:
  seen-in-build   hit and checked while the reference door was built
  vendor-docs     taken from the vendor's docs when this was written; check before relying on it
  unverified      believed true; check the vendor docs
"""

from __future__ import annotations

import json
import re
import shlex
from dataclasses import dataclass, field
from urllib.parse import urlsplit

DEFAULT_URL = "http://127.0.0.1:8765/mcp"
DEFAULT_NAME = "door"
UNKNOWN = "unknown: check the vendor docs"


@dataclass(frozen=True)
class Harness:
    id: str
    label: str
    stage: str
    config: dict[str, list[str]]  # os -> display paths
    format: str
    tool_name: str = "mcp__{server}__{tool}"
    name_limit: int = 64
    read_timeout: str = UNKNOWN
    https_required: str = "no"
    headers: str = "yes"
    paging: str = UNKNOWN
    key_by_reference: str = UNKNOWN
    confidence: str = "vendor-docs"
    notes: list[str] = field(default_factory=list)


H = Harness
HARNESSES: dict[str, Harness] = {h.id: h for h in [
    H("claude-code", "Claude Code", "05a-connect-claude-code",
      {"all": ["~/.claude.json (user and local scope)", "<project>/.mcp.json (project scope)",
               "$CLAUDE_CONFIG_DIR/.claude.json when CLAUDE_CONFIG_DIR is set", "~/.claude/settings.json (env)"]},
      "json-mcpServers",
      read_timeout="MCP_TOOL_TIMEOUT env var, in milliseconds (MCP_TIMEOUT is start-up only)",
      key_by_reference="${NAME} expansion in .mcp.json; check that your version expands it in user scope too",
      notes=["Add with `claude mcp add-json`; quote the JSON in single quotes so the shell does not expand ${NAME}.",
             "GrokBot's CLI reads this same list."]),
    H("claude-desktop", "Claude Desktop", "05b-connect-claude-desktop",
      {"darwin": ["~/Library/Application Support/Claude/claude_desktop_config.json"],
       "windows": ["%APPDATA%\\Claude\\claude_desktop_config.json"],
       "linux": ["~/.config/Claude/claude_desktop_config.json (community builds)"]},
      "json-mcpServers-stdio",
      https_required="yes for custom connectors added in Settings; no for a local stdio bridge",
      headers="not in the JSON file (stdio only); use a local stdio bridge that adds the header",
      key_by_reference="no: values in the env block are plain text; use a wrapper that reads the key at start",
      notes=["The app rewrites this file on quit: quit it before you edit, back up first.",
             "Custom connectors in Settings may be reached from the vendor's servers, so a loopback door may not be reachable that way."]),
    H("codex", "Codex", "05c-connect-codex",
      {"all": ["~/.codex/config.toml", "$CODEX_HOME/config.toml when CODEX_HOME is set",
               "<project>/.codex/config.toml (trusted projects, newer versions)"]},
      "toml-mcp_servers",
      read_timeout="tool_timeout_sec per server (default 60); startup_timeout_sec for start-up",
      key_by_reference="yes: bearer_token_env_var = \"NAME\" or env_http_headers",
      notes=["Older versions need experimental_use_rmcp_client = true for remote servers: check the vendor docs."]),
    H("cursor", "Cursor", "05d-connect-cursor",
      {"all": ["~/.cursor/mcp.json (global)", "<project>/.cursor/mcp.json (project)"]},
      "json-mcpServers",
      name_limit=60,
      key_by_reference="${env:NAME} in newer versions: check the vendor docs",
      confidence="unverified",
      notes=["Cursor has warned on long server plus tool names and capped the number of active tools: check the vendor docs."]),
    H("windsurf", "Windsurf", "05e-connect-windsurf",
      {"all": ["~/.codeium/windsurf/mcp_config.json"]},
      "json-mcpServers-serverUrl",
      key_by_reference="${env:NAME}: check the vendor docs",
      confidence="unverified",
      notes=["Remote servers use the key serverUrl. Windsurf caps the total number of tools: check the vendor docs."]),
    H("vscode", "VS Code (native, Continue, Cline)", "05f-connect-vscode",
      {"linux": ["~/.config/Code/User/mcp.json", "<project>/.vscode/mcp.json",
                 "~/.config/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json (Cline)",
                 "~/.continue/config.yaml (Continue)"],
       "darwin": ["~/Library/Application Support/Code/User/mcp.json", "<project>/.vscode/mcp.json",
                  "~/Library/Application Support/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json (Cline)",
                  "~/.continue/config.yaml (Continue)"],
       "windows": ["%APPDATA%\\Code\\User\\mcp.json", "<project>\\.vscode\\mcp.json",
                   "%APPDATA%\\Code\\User\\globalStorage\\saoudrizwan.claude-dev\\settings\\cline_mcp_settings.json (Cline)",
                   "%USERPROFILE%\\.continue\\config.yaml (Continue)"]},
      "json-servers",
      read_timeout="Cline: timeout per server in seconds (default 60). VS Code and Continue: check the vendor docs",
      key_by_reference="VS Code: ${input:id} with password: true (stored by VS Code). Continue: secrets templating. Cline: check the vendor docs",
      notes=["VS Code native MCP uses the top-level key servers, not mcpServers.",
             "Insiders and VSCodium keep the same files under their own folder names."]),
    H("zed", "Zed", "05g-connect-zed",
      {"linux": ["~/.config/zed/settings.json", "<project>/.zed/settings.json"],
       "darwin": ["~/.config/zed/settings.json", "<project>/.zed/settings.json"],
       "windows": ["%APPDATA%\\Zed\\settings.json"]},
      "jsonc-context_servers",
      headers="url plus headers in newer versions: check the vendor docs",
      key_by_reference="no known expansion: check the vendor docs",
      confidence="unverified",
      notes=["settings.json allows comments and trailing commas; keep them when you edit."]),
    H("goose", "Goose", "05h-connect-goose",
      {"linux": ["~/.config/goose/config.yaml"], "darwin": ["~/.config/goose/config.yaml"],
       "windows": ["%APPDATA%\\Block\\goose\\config\\config.yaml"]},
      "yaml-extensions",
      read_timeout="timeout per extension, in seconds (default 300)",
      key_by_reference="env_keys values live in the OS keyring for stdio extensions; headers: check the vendor docs",
      confidence="unverified"),
    H("hermes", "Hermes", "05i-connect-hermes",
      {"all": ["~/.hermes/config.yaml", "~/.hermes/profiles/<profile>/config.yaml", "~/.hermes/.env",
               "$HERMES_HOME when set"]},
      "yaml-mcp_servers",
      read_timeout="timeout and connect_timeout per server: check the vendor docs",
      key_by_reference="${NAME} from ~/.hermes/.env: check the vendor docs",
      confidence="unverified",
      notes=["Each profile has its own config.yaml: connect the profiles that should reach the door, one entry each."]),
    H("openmausbot", "OpenMausBot", "05j-connect-mausbot",
      {"all": ["<install folder>/data/config.json", "$OPENMAUSBOT_HOME/data/config.json",
               "~/.openmausbot/config.json"]},
      "json-mcpServers-enabled",
      key_by_reference="no: the key is plain text in config.json; use the revocable door key only, never an upstream key",
      confidence="seen-in-build",
      notes=["The install folder differs per machine: the interview asks where it is."]),
    H("oddboro", "Oddboro", "05k-connect-oddboro",
      {"all": ["Services tab in the office (the service list lives in the office database)",
               "$ODDBORO_HOME or ~/.oddboro (office home: .env, accounts/<tool>/<account>/)"]},
      "oddboro-services-tab",
      tool_name="mcp__{server}__{tool}",
      read_timeout=UNKNOWN,
      https_required="yes: only https:// service addresses",
      headers="one header: name Authorization; a bare value gets 'Bearer ' added",
      paging="first page of tools only",
      key_by_reference="no: the key is saved on the office desk task",
      confidence="seen-in-build",
      notes=["Needs Oddboro v0.0.6 or later (a 'Takes a key' button); see skills/connector-options/references/oddboro.md.",
             "The Pi worker refuses any granted tool whose full name mcp__<service id>__<tool> is over 64 characters.",
             "The service id comes from the address, so a long host name makes long tool names.",
             "A Read only grant reaches a tool only with readOnlyHint: true, no destructiveHint and no change word in its name.",
             "Removing an Odd's grant can delete the stored key; you may need to paste it again."]),
    H("grokbot", "GrokBot", "05l-connect-grokbot",
      {"all": ["CLI: reads Claude Code's MCP list", "~/.grok/config.toml (mcp_servers)",
               "$GROK_HOME/config.toml when GROK_HOME is set", "Desktop app: logins kept on the vendor's servers"]},
      "via-claude-code",
      key_by_reference="through Claude Code's entry",
      confidence="unverified",
      notes=["Desktop app connectors are hosted by the vendor: list them as hosted, not portable yet."]),
    H("other", "Any other MCP client", "05m-connect-other",
      {"all": ["the client's own MCP settings"]},
      "generic",
      key_by_reference="depends on the client",
      confidence="unverified",
      notes=["Generic form: the door URL plus one header, Authorization: Bearer <key>."]),
]}


def full_tool_name(harness: str, server: str, tool: str) -> str:
    return HARNESSES[harness].tool_name.format(server=server, tool=tool)


def limits_table() -> str:
    """The known-limits table in the options guide is this output, checked by a test."""
    rows = ["| Harness | Tool name form | Name limit | Read timeout setting | https only | Header support | Tool-list paging | Source |",
            "|---|---|---|---|---|---|---|---|"]
    for h in HARNESSES.values():
        rows.append(f"| {h.label} | `{h.tool_name}` | {h.name_limit} | {h.read_timeout} | {h.https_required} | "
                    f"{h.headers} | {h.paging} | {h.confidence} |")
    return "\n".join(rows) + "\n"


NAME_RULE = re.compile(r"[A-Za-z0-9_-]{1,40}")
ENV_RULE = re.compile(r"[A-Z_][A-Z0-9_]{0,63}")
URL_BAD = re.compile(r"[\s\"'\\<>`$;|(){}]")  # '&' and '?' are fine: every output quotes or escapes the URL


def entry_problem(url: str, key_env: str, name: str) -> str | None:
    """A fixed message when an argument is not safe to put in a config or a shell line. Never echoes input."""
    try:
        parts = urlsplit(url)
        parts.port  # noqa: B018 - raises on a bad port
    except ValueError:
        return "the URL is not valid"
    if URL_BAD.search(url) or parts.scheme not in ("http", "https") or not parts.hostname or "@" in parts.netloc:
        return "the URL must be http or https, with a host, no user info, and no spaces, quotes or shell characters"
    if NAME_RULE.fullmatch(name) is None:
        return "the name may hold only letters, digits, '-' and '_' (40 at most)"
    if ENV_RULE.fullmatch(key_env) is None:
        return "the variable name must look like DOOR_KEY: capitals, digits and '_'"
    return None


TOML_BARE = re.compile(r"[A-Za-z0-9_-]+")


def toml_table(name: str, body: dict) -> str:
    """A TOML table with every string escaped as a basic string (JSON escapes are valid TOML ones)."""
    key = name if TOML_BARE.fullmatch(name) else json.dumps(name)
    lines = [f"[mcp_servers.{key}]"]
    for k, v in body.items():
        lines.append(f"{k} = {json.dumps(v) if isinstance(v, str) else str(v).lower() if isinstance(v, bool) else v}")
    return "\n".join(lines) + "\n"


PLAIN_KEY = {"zed", "goose", "openmausbot", "cline", "other"}  # harnesses that keep the door key in their own config


def entry_body(harness: str, url: str, key_env: str, name: str, read_timeout: int, key: str | None = None) -> dict:
    """The structured entry for one harness. `key` is the door key itself, only for harnesses that keep it in
    their config (PLAIN_KEY), and only in add_entry's own process; everyone else gets a reference."""
    ref = "${" + key_env + "}"
    if harness == "claude-code":
        return {"type": "http", "url": url, "headers": {"Authorization": f"Bearer {ref}"}}
    if harness == "codex":
        return {"url": url, "bearer_token_env_var": key_env, "tool_timeout_sec": read_timeout, "startup_timeout_sec": 20}
    if harness == "cursor":
        return {"url": url, "headers": {"Authorization": f"Bearer {key}" if key else "Bearer ${env:" + key_env + "}"}}
    if harness == "windsurf":
        return {"serverUrl": url, "headers": {"Authorization": f"Bearer {key}" if key else "Bearer ${env:" + key_env + "}"}}
    if harness == "vscode":
        return {"type": "http", "url": url, "headers": {"Authorization": "Bearer ${input:" + name + "-key}"}}
    if harness == "cline":
        return {"url": url, "type": "streamableHttp", "headers": {"Authorization": f"Bearer {key}"}, "timeout": read_timeout}
    if harness == "zed":
        return {"url": url, "headers": {"Authorization": f"Bearer {key}"}}
    if harness == "goose":
        return {"name": name, "type": "streamable_http", "uri": url, "headers": {"Authorization": f"Bearer {key}"},
                "enabled": True, "timeout": read_timeout}
    if harness == "hermes":
        return {"url": url, "headers": {"Authorization": f"Bearer {ref}"}, "timeout": read_timeout}
    if harness == "openmausbot":
        return {"type": "http", "url": url, "headers": {"Authorization": f"Bearer {key}"}, "enabled": True}
    raise KeyError(harness)


def entry(harness: str, url: str = DEFAULT_URL, key_env: str = "DOOR_KEY", name: str = DEFAULT_NAME,
          read_timeout: int = 120) -> str:
    """The config entry text for one harness. It never holds a key: a reference or a placeholder."""
    paste = "<paste this harness's door key here>"
    ref = "${" + key_env + "}"
    if harness == "claude-code":
        body = {"type": "http", "url": url, "headers": {"Authorization": f"Bearer {ref}"}}
        return (json.dumps({"mcpServers": {name: body}}, indent=2) + "\n\n# or, user scope (the quoting keeps ${...} literal):\n"
                f"claude mcp add-json --scope user {shlex.quote(name)} {shlex.quote(json.dumps(body))}\n"
                f"# read timeout: set MCP_TOOL_TIMEOUT={read_timeout * 1000} in the environment Claude Code starts with\n")
    if harness == "claude-desktop":
        body = {"command": "<path to your bridge wrapper>", "args": [url],
                "env": {"DOOR_KEY_FILE": "<path to a 0600 file holding this harness's key>"}}
        return (json.dumps({"mcpServers": {name: body}}, indent=2)
                + "\n# The wrapper reads the key from DOOR_KEY_FILE at start and adds the Authorization header.\n")
    if harness == "codex":
        return toml_table(name, entry_body("codex", url, key_env, name, read_timeout))
    if harness == "cursor":
        return json.dumps({"mcpServers": {name: {"url": url, "headers": {"Authorization": "Bearer ${env:" + key_env + "}"}}}}, indent=2) + "\n"
    if harness == "windsurf":
        return json.dumps({"mcpServers": {name: {"serverUrl": url, "headers": {"Authorization": "Bearer ${env:" + key_env + "}"}}}}, indent=2) + "\n"
    if harness == "vscode":
        body = {"inputs": [{"type": "promptString", "id": f"{name}-key", "description": "Door key for VS Code", "password": True}],
                "servers": {name: {"type": "http", "url": url, "headers": {"Authorization": "Bearer ${input:" + name + "-key}"}}}}
        return json.dumps(body, indent=2) + "\n"
    if harness == "zed":
        return json.dumps({"context_servers": {name: {"url": url, "headers": {"Authorization": f"Bearer {paste}"}}}}, indent=2) + "\n"
    if harness in ("goose", "hermes"):
        import yaml

        top = "extensions" if harness == "goose" else "mcp_servers"
        return yaml.safe_dump({top: {name: entry_body(harness, url, key_env, name, read_timeout, key=paste)}},
                              sort_keys=False, default_flow_style=False)
    if harness == "openmausbot":
        body = {"type": "http", "url": url, "headers": {"Authorization": f"Bearer {paste}"}, "enabled": True}
        return json.dumps({"mcpServers": {name: body}}, indent=2) + "\n"
    if harness == "oddboro":
        return ("Services tab > add a hosted MCP service\n"
                f"Address: {url if url.startswith('https://') else '<your https route to the door>'}\n"
                "Takes a key: yes\nHeader name: Authorization\n"
                "Key: saved on the office desk task by you (a bare key is fine; Oddboro adds 'Bearer ')\n"
                "Grant: one Odd, Read only. Then press Connect.\n")
    if harness == "grokbot":
        return "GrokBot's CLI reads Claude Code's MCP list. Connect Claude Code (05a), then check GrokBot lists the door.\n"
    if harness == "other":
        return f"URL: {url}\nHeader: Authorization: Bearer {paste}\n"
    raise KeyError(harness)
