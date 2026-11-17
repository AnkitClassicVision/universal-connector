"""Load and validate the two manifest files. Problems never echo a secret value."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any, TypeVar
from urllib.parse import urlsplit

import yaml
from pydantic import BaseModel, ValidationError

from universal_connector.models import AgentGrant, Connection, Manifest, Scope
from universal_connector.router import change_words_in
from universal_connector.scan import find_secrets

CONNECTOR_FILE = "connector.yaml"
AGENTS_FILE = "agents.yaml"
MAX_PINNED = 20
TIMEOUT_MIN, TIMEOUT_MAX = 1, 600
NO_UPSTREAM_KINDS = {"google", "browser", "computer"}
LOOPBACK_HOSTS = {"127.0.0.1", "localhost"}
CONNECTION_NAME = re.compile(r"[a-z][a-z0-9]*(_[a-z0-9]+)*")
TOOL_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}")
AGENT_NAME = re.compile(r"[a-z][a-z0-9-]*")
SECRET_POINTER = re.compile(r"[A-Za-z0-9_.\-/]+")
NEEDS_SECRET = ("header", "bearer", "google-oauth")

M = TypeVar("M", bound=BaseModel)


class ManifestError(Exception):
    """The manifest is invalid. `problems` lists every fault found."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = list(problems)
        super().__init__(f"{len(self.problems)} manifest problem(s): " + "; ".join(self.problems))


def _safe(value: object) -> str:
    """Echo a user-written value only when it is short and does not look like a secret."""
    text = str(value)
    if len(text) > 64 or find_secrets(text):
        return "[hidden]"
    return text


def _read(directory: Path, filename: str, problems: list[str]) -> dict[str, Any] | None:
    path = directory / filename
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        problems.append(f"{filename}: missing")
        return None
    except (OSError, UnicodeDecodeError):
        problems.append(f"{filename}: cannot be read")
        return None
    for rule in find_secrets(raw):
        problems.append(f"{filename}: possible secret value ({rule})")
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        where = f" near line {mark.line + 1}" if mark is not None else ""
        problems.append(f"{filename}: not valid YAML{where}")
        return None
    if not isinstance(data, dict):
        problems.append(f"{filename}: top level must be a mapping")
        return None
    return data


def _items(
    data: dict[str, Any] | None, filename: str, key: str, model: type[M], problems: list[str]
) -> list[M]:
    if data is None:
        return []
    for extra in sorted(set(map(str, data)) - {"version", key}):
        problems.append(f"{filename}: unknown key {_safe(extra)}")
    version = data.get("version")
    if not isinstance(version, int) or isinstance(version, bool):
        problems.append(f"{filename}: version must be an integer")
    items = data.get(key)
    if not isinstance(items, list):
        problems.append(f"{filename}: {key} must be a list")
        return []
    out: list[M] = []
    for index, item in enumerate(items):
        try:
            out.append(model.model_validate(item))
        except ValidationError as exc:
            for err in exc.errors():
                loc = ".".join(_safe(part) for part in (key, index, *err["loc"]))
                msg = err["msg"] if not find_secrets(err["msg"]) else "invalid value"
                problems.append(f"{filename}: {loc}: {msg}")
    return out


def _check_names(kind: str, names: list[str], pattern: re.Pattern[str], problems: list[str]) -> None:
    for name, count in Counter(names).items():
        if count > 1:
            problems.append(f"duplicate {kind} name: {_safe(name)}")
    for name in names:
        if not pattern.fullmatch(name):
            problems.append(f"{kind} {_safe(name)}: name must match {pattern.pattern}")


def _upstream_problem(conn: Connection) -> str | None:
    """Rule 9. Return a fixed message, never the value, when `upstream` is not acceptable."""
    upstream = conn.upstream
    if conn.kind in NO_UPSTREAM_KINDS:
        return f"kind {conn.kind} must not have an upstream" if upstream is not None else None
    if upstream is None:
        return f"kind {conn.kind} needs an upstream"
    if conn.kind == "mcp-stdio":
        if not upstream.startswith("/") or re.search(r"\s", upstream):
            return "upstream must be an absolute path with no spaces for mcp-stdio"
        return None
    if "://" not in upstream:
        return "upstream must be a URL with a scheme"
    try:
        parts = urlsplit(upstream)
        parts.port  # noqa: B018 - raises ValueError on a bad port
    except ValueError:
        return "upstream is not a valid URL"
    if not parts.hostname:
        return "upstream must have a host"
    loopback_http = parts.scheme == "http" and parts.hostname in LOOPBACK_HOSTS
    if parts.scheme != "https" and not loopback_http:
        return "upstream must use https (http only for 127.0.0.1 or localhost)"
    if "@" in parts.netloc:
        return "upstream must not carry user info"
    if "?" in upstream or "#" in upstream:
        return "upstream must not carry a query string or fragment"
    return None


def _check_connection(conn: Connection, problems: list[str]) -> None:
    label = f"connection {_safe(conn.name)}"
    if not conn.scopes:
        problems.append(f"{label}: scopes must not be empty")
    found = change_words_in(conn.name)
    if found:
        # Oddboro would strip every read tool of this connection: its visible names start with this.
        problems.append(f"{label}: name contains a change word ({', '.join(sorted(found))})")
    upstream_problem = _upstream_problem(conn)
    if upstream_problem:
        problems.append(f"{label}: {upstream_problem}")
    for tool in conn.tools:
        if not TOOL_NAME.fullmatch(tool.name):
            problems.append(f"{label}: tool {_safe(tool.name)}: name must match {TOOL_NAME.pattern}")
        if not TIMEOUT_MIN <= tool.timeout_s <= TIMEOUT_MAX:
            problems.append(
                f"{label}: tool {_safe(tool.name)}: timeout_s must be between "
                f"{TIMEOUT_MIN} and {TIMEOUT_MAX}"
            )
    for tool, count in Counter(t.name for t in conn.tools).items():
        if count > 1:
            problems.append(f"{label}: duplicate tool name: {_safe(tool)}")
    for field in ("secret", "token_secret"):
        value = getattr(conn.auth, field)
        if value is not None and not SECRET_POINTER.fullmatch(value):
            problems.append(f"{label}: auth.{field} is not a vault entry name")
    if conn.auth.type in NEEDS_SECRET and not conn.auth.secret:
        problems.append(f"{label}: auth.type {conn.auth.type} needs auth.secret")
    if conn.auth.type == "header" and not conn.auth.header:
        problems.append(f"{label}: auth.type header needs auth.header")


def _check_agent(agent: AgentGrant, problems: list[str]) -> None:
    label = f"agent {_safe(agent.name)}"
    if not agent.scopes:
        problems.append(f"{label}: scopes must not be empty")
    if Scope.restricted in agent.scopes:
        problems.append(f"{label}: restricted cannot be granted in this version")
    if agent.call_timeout_s is not None and not TIMEOUT_MIN <= agent.call_timeout_s <= TIMEOUT_MAX:
        problems.append(
            f"{label}: call_timeout_s must be between {TIMEOUT_MIN} and {TIMEOUT_MAX}"
        )


def load_manifest(directory: Path) -> Manifest:
    """Load `connector.yaml` and `agents.yaml` from `directory`. Raise `ManifestError` on any fault."""
    directory = Path(directory)
    problems: list[str] = []
    connector_data = _read(directory, CONNECTOR_FILE, problems)
    agents_data = _read(directory, AGENTS_FILE, problems)
    connections = _items(connector_data, CONNECTOR_FILE, "connections", Connection, problems)
    agents = _items(agents_data, AGENTS_FILE, "agents", AgentGrant, problems)

    _check_names("connection", [c.name for c in connections], CONNECTION_NAME, problems)
    _check_names("agent", [a.name for a in agents], AGENT_NAME, problems)
    for conn in connections:
        _check_connection(conn, problems)
    for agent in agents:
        _check_agent(agent, problems)
    pinned = sum(1 for conn in connections for tool in conn.tools if tool.pinned)
    if pinned > MAX_PINNED:
        problems.append(f"pinned tools: {pinned}, limit {MAX_PINNED}")

    if problems:
        raise ManifestError(problems)
    assert connector_data is not None
    return Manifest(version=connector_data["version"], connections=connections, agents=agents)
