"""Shared pieces for every scan plug-in: the run context, findings, and safe file loaders.

Loaders never raise and never quote file content. A parser's own error text can
hold a slice of the file, so it is dropped and only a fixed status is kept.
"""

from __future__ import annotations

import configparser
import json
import os
import re
import stat
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from kit.redact import Redactor

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - older Python
    tomllib = None  # type: ignore[assignment]

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - PyYAML is optional
    yaml = None  # type: ignore[assignment]

MAX_FILE_BYTES = 5_000_000
FRONTMATTER_BYTES = 65_536

# Statuses a looked-at place can have.
FOUND, MISSING, MALFORMED, UNREADABLE, TOO_LARGE = "found", "missing", "malformed", "unreadable", "too-large"
NEEDS_PYYAML, SKIPPED, OPT_IN, UNAVAILABLE = "needs-pyyaml", "skipped", "opt-in-required", "unavailable"

Runner = Callable[[list[str], dict[str, str], float], "str | None"]


def default_runner(argv: list[str], env: dict[str, str], timeout: float) -> str | None:
    """Run one listing command. stdin closed, stderr dropped, output kept in memory only."""
    try:
        done = subprocess.run(
            argv, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, timeout=timeout, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0 or len(done.stdout) > MAX_FILE_BYTES:
        return None
    return done.stdout.decode("utf-8", "replace")


def _forms(path: Path) -> list[str]:
    """The spellings a path can reach output in, longest first."""
    out: list[str] = []
    for form in (str(path), os.path.abspath(path), os.path.realpath(path)):
        if form not in out:
            out.append(form)
    return sorted(out, key=len, reverse=True)


@dataclass
class Ctx:
    home: Path
    env: dict[str, str]
    platform: str = "linux"  # linux | darwin | windows
    root: Path = Path("/")
    projects: list[Path] = field(default_factory=list)
    follow_projects: bool = True
    include_vaults: bool = False
    extra: dict[str, list[Path]] = field(default_factory=dict)
    runner: Runner = default_runner
    redactor: Redactor = field(default_factory=Redactor)
    door_hosts: set[str] = field(default_factory=set)  # scheme://host[:port] of the person's own door
    notes_for_run: list[str] = field(default_factory=list)

    def safe_location(self, where: Path | str) -> str:
        """Any place shown in output: home as `~`, control characters gone, key-shaped text hidden."""
        from kit.redact import risky, strip_controls

        text = strip_controls(self.show(where) if isinstance(where, Path) else str(where))
        return self.redactor.hide(text) if risky(text) else text

    def env_path(self, name: str) -> Path | None:
        return self.expand(self.env.get(name, "").strip())

    def expand(self, value: str) -> Path | None:
        """A path from config text. `~` means this scan's home, never the real one in a test."""
        if not value:
            return None
        if value == "~" or value.startswith(("~/", "~\\")):
            return self.home / value[2:]
        return Path(value)

    def sys_path(self, absolute: str) -> Path:
        """A system path (such as /etc/...) read under `root`, so tests can use a fixture tree."""
        return self.root / absolute.lstrip("/")

    def xdg_config(self) -> Path:
        return self.env_path("XDG_CONFIG_HOME") or self.home / ".config"

    def appdata(self) -> Path:
        return self.env_path("APPDATA") or self.home / "AppData" / "Roaming"

    def app_support(self) -> Path:
        """Per-user application settings folder for the platform."""
        if self.platform == "darwin":
            return self.home / "Library" / "Application Support"
        if self.platform == "windows":
            return self.appdata()
        return self.xdg_config()

    def show(self, path: Path | str) -> str:
        """A path for output: home as `~`, a test root as `/`. Never a value."""
        text = str(path)
        for home in _forms(self.home):  # as given, absolute, and with links resolved (/home -> /var/home)
            if text == home or text.startswith(home + os.sep):
                return "~" + text[len(home):]
        for root in _forms(self.root):
            if root not in ("/", "") and (text == root or text.startswith(root + os.sep)):
                return "/" + text[len(root):].lstrip(os.sep)
        return text


@dataclass
class Finding:
    source: str
    location: str
    kind: str  # mcp-server | env-var | cli-login | vault-entry | listening-port | service | account-home ...
    name: str
    transport: str | None = None
    host: str | None = None
    command: str | None = None
    key_fields: list[str] = field(default_factory=list)
    key_where: list[str] = field(default_factory=list)
    auth_kind: str = "none-found"
    plain_file: bool = False
    how_to_add: str = ""
    detail: str = ""
    door_entry: bool = False  # a harness entry for the person's own door, holding that harness's door key

    @property
    def key(self) -> str:
        return f"{self.source}|{self.location}|{self.kind}|{self.name}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.key, "source": self.source, "location": self.location, "kind": self.kind,
            "name": self.name, "transport": self.transport, "host": self.host, "command": self.command,
            "key_fields": sorted(set(self.key_fields)), "key_where": sorted(set(self.key_where)),
            "auth_kind": self.auth_kind, "plain_file": self.plain_file, "how_to_add": self.how_to_add,
            "detail": self.detail, "door_entry": self.door_entry,
        }


@dataclass
class SkillEntry:
    harness: str
    location: str
    name: str
    description: str
    klass: str  # external-api | portable-instructions | harness-specific
    signals: list[str]
    next_step: str

    @property
    def key(self) -> str:
        return f"{self.harness}|{self.location}|{self.name}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.key, "harness": self.harness, "location": self.location, "name": self.name,
            "description": self.description, "class": self.klass, "signals": sorted(set(self.signals)),
            "next_step": self.next_step,
        }


@dataclass
class Collector:
    """What one plug-in found. Statuses are per place, so a missing file is never an error."""

    source: str
    ctx: Ctx
    looked: list[dict[str, str]] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    skills: list[SkillEntry] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def look(self, where: Path | str, status: str) -> None:
        self.looked.append({"path": self.ctx.safe_location(where), "status": status})

    def add(self, finding: Finding) -> None:
        self.findings.append(finding)


# ---------------------------------------------------------------- safe loaders


def read_bytes(path: Path, limit: int = MAX_FILE_BYTES, truncate: bool = False) -> tuple[str, bytes | None]:
    """(status, bytes) of a regular file only. A pipe, socket or device is never read, so nothing hangs:
    the open does not block, and the file's type is checked on the open handle before any read."""
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_CLOEXEC", 0))
    except FileNotFoundError:
        return MISSING, None
    except OSError:
        return (UNREADABLE if os.path.lexists(path) else MISSING), None
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            return UNREADABLE, None
        if st.st_size > limit and not truncate:
            return TOO_LARGE, None
        chunks, left = [], limit
        while left > 0:
            chunk = os.read(fd, min(left, 1 << 20))
            if not chunk:
                break
            chunks.append(chunk)
            left -= len(chunk)
        return FOUND, b"".join(chunks)
    except OSError:
        return UNREADABLE, None
    finally:
        os.close(fd)


def read_text(path: Path, limit: int = MAX_FILE_BYTES) -> tuple[str, str | None]:
    """(status, text). Text stays in this process."""
    status, data = read_bytes(path, limit)
    if data is None:
        return status, None
    try:
        return FOUND, data.decode("utf-8")
    except UnicodeDecodeError:
        return MALFORMED, None


if yaml is not None:
    class _NoAliasLoader(yaml.SafeLoader):
        """Safe YAML that refuses anchors and aliases: a few lines of them can expand to billions of nodes.
        Hand-written harness configs do not use them."""

        def compose_node(self, parent, index):
            if self.check_event(yaml.events.AliasEvent):
                raise yaml.composer.ComposerError(None, None, "aliases are refused", self.peek_event().start_mark)
            return super().compose_node(parent, index)


def load_yaml(text: str) -> Any:
    return yaml.load(text, Loader=_NoAliasLoader)  # noqa: S506 - a SafeLoader subclass


def _strip_jsonc(text: str) -> str:
    """Remove // and /* */ comments and trailing commas, leaving strings alone."""
    out, i, n = [], 0, len(text)
    in_str = False
    while i < n:
        c = text[i]
        if in_str:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if c == '"':
                in_str = False
            i += 1
            continue
        if c == '"':
            in_str = True
            out.append(c)
            i += 1
        elif text.startswith("//", i):
            j = text.find("\n", i)
            i = n if j < 0 else j
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            i = n if j < 0 else j + 2
        else:
            out.append(c)
            i += 1
    return re.sub(r",(\s*[}\]])", r"\1", "".join(out))


def parse(text: str, fmt: str) -> tuple[str, Any]:
    """(status, data). fmt is json, jsonc, toml, yaml or ini."""
    try:
        if fmt == "json":
            return FOUND, json.loads(text)
        if fmt == "jsonc":
            return FOUND, json.loads(_strip_jsonc(text))
        if fmt == "toml":
            if tomllib is None:
                return SKIPPED, None
            return FOUND, tomllib.loads(text)
        if fmt == "yaml":
            if yaml is None:
                return NEEDS_PYYAML, None
            return FOUND, load_yaml(text)
        if fmt == "ini":
            cp = configparser.RawConfigParser(strict=False, interpolation=None)
            cp.read_string(text)
            return FOUND, cp
    except Exception:  # noqa: BLE001 - parser errors can quote file content; keep a fixed status
        return MALFORMED, None
    raise ValueError(f"unknown format {fmt}")


def load(col: Collector, path: Path, fmt: str) -> Any:
    """Read and parse one file, record its status, and return the data or None."""
    status, text = read_text(path)
    if text is None:
        col.look(path, status)
        return None
    status, data = parse(text, fmt)
    col.look(path, status)
    return data if status == FOUND else None


def frontmatter(path: Path) -> tuple[str, dict[str, Any] | None]:
    """Only the leading `---` block of a SKILL.md. The body is never read past it."""
    status, data = read_bytes(path, FRONTMATTER_BYTES, truncate=True)
    if data is None:
        return status, None
    head = data.decode("utf-8", "replace")
    m = re.match(r"^﻿?---\r?\n(.*?)\r?\n---\s*(?:\r?\n|$)", head, re.S)
    if not m:
        return MALFORMED, None
    block = m.group(1)
    if yaml is not None:
        try:
            data = load_yaml(block)
        except Exception:  # noqa: BLE001
            data = None
        if isinstance(data, dict):
            return FOUND, data
    data = {}
    for line in block.splitlines():
        mm = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*):\s*(.*)$", line)
        if mm:
            data[mm.group(1)] = mm.group(2).strip().strip("\"'")
    return (FOUND, data) if data else (MALFORMED, None)


def dotenv_names(text: str) -> list[str]:
    """Variable names in a .env style or shell file. Values are skipped, never kept."""
    names = []
    for raw in text.splitlines():
        line = raw.strip()
        m = re.match(r"^(?:export\s+|set\s+-gx\s+|set\s+-x\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=", line)
        if not m:
            m = re.match(r"^set\s+-[gxU]+\s+([A-Za-z_][A-Za-z0-9_]*)\s+\S", line)  # fish
        if m:
            names.append(m.group(1))
    return names


def bounded_glob(base: Path, pattern: str, limit: int = 300) -> list[Path]:
    """`base.glob(pattern)` that never follows a huge tree past `limit` results."""
    out: list[Path] = []
    try:
        for p in base.glob(pattern):
            out.append(p)
            if len(out) >= limit:
                break
    except OSError:
        pass
    return sorted(out)


def platform_name() -> str:
    if sys.platform.startswith("darwin"):
        return "darwin"
    if sys.platform.startswith("win"):
        return "windows"
    return "linux"
