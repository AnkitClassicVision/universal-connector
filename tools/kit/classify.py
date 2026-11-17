"""Where does a connection's key live? Decided from the shape of the config entry.

Values are looked at here, in this process, and dropped. What comes out is a set of
location kinds, the names of the fields involved, and an auth kind.

Location kinds (`key_where`):
  inline         a literal value sits in the config file (header, env, URL, argument)
  env-reference  the config points at an environment variable (`${NAME}` and friends)
  environment    the value is set in the process environment or a shell profile
  file           the value sits in, or is read from, a plain file on disk
  keyring        an OS keychain or keyring holds it
  vault          a password manager or secret service holds it (1Password, Vault, ...)
  helper         a credential helper program supplies it
  prompt         the harness asks for it at start and stores it itself
  oauth          the harness or a bridge signs in with OAuth
  browser-session a browser profile with a saved sign-in is used
  none           a local tool with no credential
  no-credential-found  a remote server with no credential in its entry
"""

from __future__ import annotations

import re
import shlex
from typing import Any
from urllib.parse import parse_qsl, urlsplit

from kit.core import Finding
from kit.keyshape import is_key_shaped
from kit.redact import LONG_RUN, Redactor, looks_random

CRED_WORD = re.compile(
    r"(?i)(key|token|secret|passw|pwd|auth|credential|cookie|session|bearer|private|signature|"
    r"dsn|database_url|connection_string|conn_str|(^|_)pat($|_)|"
    r"(^|_)(db|database|pg|postgres|mysql|redis|mongo|mongodb|amqp)_(url|uri|dsn)($|_))"
)
KEY_KINDS = {"inline", "env-reference", "file", "vault", "keyring", "prompt", "environment", "helper"}
SERVICE_ACCOUNT = re.compile(r"(?i)(service[-_]?account|google_application_credentials|\bsa[-_][a-z0-9-]*\.json)")
FILE_HINT = re.compile(r"(?i)(_file$|_path$|keyfile|key_file|credentials?$|\.pem$|\.key$|\.p12$|\.json$)")
ENV_REF = re.compile(
    r"\$\{(?:env:)?[A-Za-z_][A-Za-z0-9_]*(?::-[^}]*)?\}|\$[A-Z_][A-Z0-9_]{1,}|\{env:[A-Za-z_][A-Za-z0-9_]*\}"
    r"|\$\{\{\s*secrets\.[A-Za-z0-9_.-]+\s*\}\}|%[A-Za-z_][A-Za-z0-9_]*%|\$env:[A-Za-z_][A-Za-z0-9_]*"
)
ENV_NAME_IN_REF = re.compile(r"(?:\$\{(?:env:)?|\{env:|\$env:|\$|%|secrets\.)([A-Za-z_][A-Za-z0-9_]*)")
PROMPT_REF = re.compile(r"\$\{input:[A-Za-z0-9_.-]+\}")
VAULT_REF = re.compile(r"(?i)(op://|arn:aws:secretsmanager:|secretsmanager|vault://|bws?://|infisical|doppler)")
VAULT_COMMANDS = {"op", "bw", "bws", "vault", "gopass", "pass", "doppler", "infisical", "sops", "keepassxc-cli", "chamber"}
KEYRING_COMMANDS = {"security", "secret-tool", "keyring", "kwallet-query", "cmdkey"}
OAUTH_COMMANDS = {"mcp-remote"}
BROWSER_ARGS = re.compile(r"(?i)^--?(user-data-dir|profile|profile-directory|storage-state|cdp-endpoint|browser-profile)")
BROWSER_COMMANDS = re.compile(r"(?i)(playwright|puppeteer|browser|chrome|chromium|brave|firefox|selenium)")
WRAPPERS = {"npx", "uvx", "bunx", "pnpm", "yarn", "node", "python", "python3", "uv", "pipx", "docker", "deno", "bun", "sh", "bash", "cmd", "env"}
HTTP_KINDS = {"http", "streamable-http", "streamable_http", "streamablehttp", "sse", "ws", "websocket"}
URL_KEYS = ("url", "serverUrl", "server_url", "httpUrl", "uri", "endpoint", "baseUrl")
HEADER_KEYS = ("headers", "http_headers", "httpHeaders", "requestOptions")
ENV_KEYS = ("env", "envs", "environment", "settings")
ENV_NAME_KEYS = ("bearer_token_env_var", "env_vars", "env_keys")
ENV_HEADER_KEYS = ("env_http_headers",)
OAUTH_KEYS = ("oauth", "auth", "authorization_url", "clientId", "client_id", "oauth_client_id")
SAFE_LITERALS = re.compile(r"(?i)^(true|false|yes|no|on|off|null|none|\d{1,6}|debug|info|warn|error|production|development|test|stdio|http|https|json|text)$")


def env_names_in(text: str) -> list[str]:
    return [m.group(1) for m in ENV_NAME_IN_REF.finditer(text) if ENV_REF.search(text)]


def value_kind(value: Any, name: str = "") -> str | None:
    """Classify one literal under a header, env or settings key. None means not a credential."""
    if value is None or isinstance(value, bool) or isinstance(value, (int, float)):
        return None
    if isinstance(value, (dict, list)):
        return None
    text = str(value).strip()
    if not text:
        return None
    if PROMPT_REF.search(text):
        return "prompt"
    if VAULT_REF.search(text):
        return "vault"
    if ENV_REF.search(text):
        return "env-reference"
    credish = bool(CRED_WORD.search(name))
    if credish and (FILE_HINT.search(name) or text.startswith(("/", "~", "./", "file:"))) and not is_key_shaped(text):
        return "file"
    if SAFE_LITERALS.match(text) and not credish:
        return None
    if credish or is_key_shaped(text) or LONG_RUN.search(text) or looks_random(text):
        return "inline"
    return None


def _walk_literals(value: Any, inside: bool, out: list[tuple[str, Any]], key: str = "") -> None:
    if isinstance(value, dict):
        for k, v in value.items():
            _walk_literals(v, inside or str(k) in HEADER_KEYS + ENV_KEYS, out, str(k))
    elif isinstance(value, list):
        for v in value:
            _walk_literals(v, inside, out, key)
    elif inside:
        out.append((key, value))


def _split_command(entry: dict[str, Any]) -> tuple[list[str], str | None]:
    """All words of command plus args, and the executable base name."""
    words: list[str] = []
    cmd = entry.get("command", entry.get("cmd"))
    if isinstance(cmd, dict):  # Zed: {"command": {"path": ..., "args": [...], "env": {...}}}
        words += [str(cmd.get("path", ""))] + [str(a) for a in cmd.get("args") or [] if not isinstance(a, dict)]
    elif isinstance(cmd, str):
        try:
            words += shlex.split(cmd)
        except ValueError:
            words += cmd.split()
    elif isinstance(cmd, list):
        words += [str(w) for w in cmd]
    args = entry.get("args")
    if isinstance(args, str):
        try:
            words += shlex.split(args)
        except ValueError:
            words += args.split()
    elif isinstance(args, list):
        words += [str(a) for a in args if not isinstance(a, (dict, list))]
    rest = [w for w in words if w]
    while rest and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", rest[0]):
        rest.pop(0)
    exe = rest[0] if rest else None
    return words, exe


def _args_kinds(words: list[str]) -> tuple[set[str], set[str]]:
    """Credential kinds and env names seen in command-line words."""
    kinds: set[str] = set()
    names: set[str] = set()
    prev = ""
    for w in words:
        flag, _, inline_value = w.partition("=") if w.startswith("-") and "=" in w else (w, "", "")
        if PROMPT_REF.search(w):
            kinds.add("prompt")
        elif VAULT_REF.search(w):
            kinds.add("vault")
        elif ENV_REF.search(w):
            kinds.add("env-reference")
            names.update(env_names_in(w))
        elif BROWSER_ARGS.match(w):
            kinds.add("browser-session")
        elif inline_value and CRED_WORD.search(flag):
            kinds.add("file" if FILE_HINT.search(flag) else "inline")
        elif prev.startswith("-") and CRED_WORD.search(prev) and not w.startswith("-"):
            kinds.add("file" if FILE_HINT.search(prev) or w.startswith(("/", "~", "./")) else "inline")
        elif is_key_shaped(w) or LONG_RUN.search(w):
            kinds.add("inline")
        prev = w
    return kinds, names


def _url_kinds(url: str) -> set[str]:
    kinds: set[str] = set()
    try:
        parts = urlsplit(url)
    except ValueError:
        return {"inline"}
    if "@" in parts.netloc and ":" in parts.netloc.split("@")[0]:
        kinds.add("inline")
    for k, v in parse_qsl(parts.query, keep_blank_values=True):
        vk = value_kind(v, k)
        if vk:
            kinds.add(vk)
    for piece in (parts.path, parts.fragment):
        for seg in re.split(r"[/;&=]", piece):
            if is_key_shaped(seg) or LONG_RUN.search(seg) or looks_random(seg):
                kinds.add("inline")
            elif ENV_REF.search(seg):
                kinds.add("env-reference")
    return kinds


def classify_entry(raw: dict[str, Any], red: Redactor) -> dict[str, Any]:
    """Transport, host, command, key field names, key locations and auth kind of one MCP entry."""
    entry = dict(raw)
    if isinstance(entry.get("transport"), dict):  # some clients nest the transport
        entry = {**entry["transport"], **{k: v for k, v in entry.items() if k != "transport"}}
    url = next((entry[k] for k in URL_KEYS if isinstance(entry.get(k), str)), None)
    words, exe = _split_command(entry)
    kinds: set[str] = set()
    fields: set[str] = set()

    for key in HEADER_KEYS + ENV_KEYS:
        mapping = entry.get(key)
        if key == "requestOptions" and isinstance(mapping, dict):
            mapping = mapping.get("headers")
        if isinstance(entry.get("command"), dict) and key == "env":
            mapping = {**(mapping or {}), **(entry["command"].get("env") or {})}
        if not isinstance(mapping, dict):
            continue
        for name, value in mapping.items():
            vk = value_kind(value, str(name))
            if vk:
                kinds.add(vk)
                fields.add(red.field(name))
                if vk == "env-reference":
                    fields.update(red.field(n) for n in env_names_in(str(value)))
    for key in ENV_NAME_KEYS:
        value = entry.get(key)
        names = [value] if isinstance(value, str) else value if isinstance(value, list) else []
        for n in names:
            fields.add(red.field(n))
            kinds.add("keyring" if key == "env_keys" else "env-reference")
    for key in ENV_HEADER_KEYS:
        mapping = entry.get(key)
        if isinstance(mapping, dict):
            for h, envname in mapping.items():
                fields.add(red.field(h))
                fields.add(red.field(envname))
                kinds.add("env-reference")
    literals: list[tuple[str, Any]] = []
    _walk_literals({k: v for k, v in entry.items() if k not in ("command", "args", "cmd")}, False, literals)
    for name, value in literals:
        vk = value_kind(value, name)
        if vk:
            kinds.add(vk)
    if words:
        ak, an = _args_kinds(words)
        kinds |= ak
        fields.update(red.field(n) for n in an)
    if url:
        kinds |= _url_kinds(url)

    base = (exe or "").replace("\\", "/").rsplit("/", 1)[-1].lower()
    if base.endswith(".exe"):
        base = base[:-4]
    shown_cmd = red.command(exe) if exe else None
    tool_words = [w.replace("\\", "/").rsplit("/", 1)[-1].lower() for w in words[:4]]
    if base in VAULT_COMMANDS or (base in WRAPPERS and any(t in VAULT_COMMANDS for t in tool_words[1:2])):
        kinds.add("vault")
    if base in KEYRING_COMMANDS:
        kinds.add("keyring")
    if any(t.split("@")[0] in OAUTH_COMMANDS for t in tool_words) and not kinds & KEY_KINDS:
        kinds.add("oauth")  # a bridge with no key given signs in with OAuth itself
    auth_field = entry.get("auth")
    auth_words = ""
    if isinstance(auth_field, dict):  # in memory only; never printed
        auth_words = " ".join(str(x) for x in list(auth_field) + list(auth_field.values())).lower()
    if (any(k in entry for k in OAUTH_KEYS if k != "auth") or str(auth_field).lower() == "oauth"
            or "oauth" in auth_words):
        kinds.add("oauth")
    if any(BROWSER_COMMANDS.search(t) for t in tool_words) and "browser-session" not in kinds:
        if any(BROWSER_ARGS.match(w) for w in words):
            kinds.add("browser-session")

    declared = entry.get("type") or (entry.get("transport") if isinstance(entry.get("transport"), str) else None)
    if isinstance(declared, str) and declared.strip():
        d = declared.strip().lower().replace("_", "-")
        transport = "http" if d in {"http", "streamable-http", "streamablehttp"} else d if d in HTTP_KINDS | {"stdio"} else "other"
    else:
        transport = "http" if url else ("stdio" if exe else "unknown")
    if not kinds:
        kinds.add("no-credential-found" if transport in HTTP_KINDS | {"http"} or url else "none")

    return {
        "transport": transport,
        "host": red.host(url) if url else None,
        "command": shown_cmd,
        "key_fields": sorted(fields),
        "key_where": sorted(kinds),
        "auth_kind": auth_kind(kinds, " ".join(words) + " " + " ".join(fields)),
    }


def auth_kind(kinds: set[str] | list[str], context: str = "") -> str:
    kinds = set(kinds)
    if "browser-session" in kinds:
        return "browser-session"
    if "oauth" in kinds:
        return "oauth"
    if SERVICE_ACCOUNT.search(context) and kinds & {"file", "env-reference", "environment"}:
        return "service-account"
    if kinds & {"inline", "env-reference", "environment", "file", "keyring", "vault", "helper", "prompt"}:
        return "api-key"
    if "no-credential-found" in kinds:
        return "none-found"
    return "not-needed"


PLAIN = {"inline", "file"}


def how_to_add(f: Finding) -> str:
    """One plain sentence on turning this finding into a door connection."""
    where = set(f.key_where)
    move = ""
    if where & PLAIN:
        move = ("A key sits in a plain file. You move it into the vault yourself with the vault's own "
                "store command (03-vault), then remove it from this file. ")
    if f.kind == "mcp-server":
        if f.auth_kind == "oauth":
            return move + "Remote server with OAuth: add it to the door as a remote upstream and sign in once through the door's login flow."
        if f.auth_kind == "browser-session":
            return move + "Browser lane: keep the saved session in its own browser profile; you sign in yourself. Do not move passwords."
        if f.transport in ("http", "sse", "ws", "websocket"):
            if "no-credential-found" in where:
                return "Remote server with no key in its entry: check whether it signs in with OAuth or is open, then add it as a remote upstream."
            return move + "Remote server: add it to the door as a remote upstream with the same header name; the door reads the key from the vault."
        if f.transport == "stdio":
            if "none" in where:
                return "Local tool with no key: run it behind the door as a local upstream, or leave it in its harness if it only reads local files."
            return move + "Local tool: run it behind the door as a local upstream; the door passes the env values from the vault."
        return move + "Unknown transport: read its docs, then add it as a remote or local upstream."
    if f.kind in ("env-var", "env-file-var", "shell-profile-var"):
        return move + "If a connection needs this variable, store the value in the vault under a name and point the door at that name."
    if f.kind == "cli-login":
        return move + "CLI sign-in: keep it in the CLI's own store. To use it through the door, create a scoped token or service account for that service."
    if f.kind == "vault-entry":
        return "Already in a vault: point the door's manifest at this entry name."
    if f.kind == "listening-port":
        return "A local program is listening. Ask what it is; if it is an MCP server, add it as a remote upstream on the loopback address."
    if f.kind == "service":
        return "A service in this harness: list its tools and tier them in 02-plan, then reach it through the door."
    return move + "Review in 02-plan."
