"""What an agent needs to connect, and the safe edit of `agents.yaml`.

`entry_for` renders the one config entry an agent system needs. The agent file helpers write
`agents.yaml` from validated models, atomically, and can put the old bytes back.
"""

from __future__ import annotations

import contextlib
import errno
import json
import os
import re
import stat
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

import yaml

from universal_connector import portable
from universal_connector.models import AgentGrant
from universal_connector.state import LOCK_NAME, LOCK_REFUSED, StateDirError, open_state

FORMATS = ("generic", "oddboro")
DEFAULT_URL = "http://127.0.0.1:8765/mcp"
AGENTS_FILE = "agents.yaml"
LOCK_UNREADABLE = "could not open the lock file"
LOCK_BUSY = "the state lock stayed busy; nothing was changed"
LOCK_FILE = LOCK_NAME
KEY_IN_FILE = "<key in file>"
RELOAD_HINT = "Reload the running door to apply: uconnector reload (or SIGHUP on Linux and macOS)."
ODDBORO_HTTPS = "Oddboro needs an https address."
ODDBORO_PATH = (
    "Oddboro would rewrite this address path; use only letters, digits and - . _ ~ in it"
)
ODDBORO_HOST = "Oddboro needs a plain ASCII host name in the address"
BAD_ADDRESS = "the address must be an http or https URL with a host and no user info"
# Oddboro refuses a whole run when a granted tool's full name is not 1 to 64 characters of
# `a-z A-Z 0-9 _ -`. Past 57 characters `connect` warns: the margin that holds across versions.
ODDBORO_NAME_LIMIT = 64
ODDBORO_NAME_WARN = 57
# The most one call of an Oddboro agent takes, retry included. Oddboro's safe wait is under 45 s.
# The first try gets the tool's own timeout, capped at the budget; a green tool's one retry gets
# only what is left, and none when nothing is left.
ODDBORO_CALL_TIMEOUT_S = 40
SNAKE_CASE = re.compile(r"[a-z0-9]+(?:_[a-z0-9]+)*(?:__[a-z0-9]+(?:_[a-z0-9]+)*)?")
_BAD_CHARS = re.compile(r"[\s\"'\\<>`]")
_ODDBORO_SEGMENT = re.compile(r"[A-Za-z0-9._~-]+")
_ODDBORO_HOST = re.compile(r"[a-z0-9.-]+")  # no IPv6: Oddboro rewrites its spelling


def entry_for(fmt: str, url: str, key: str) -> str:
    """The config entry for one agent system. `key` may be the placeholder `<key in file>`."""
    header = f"Bearer {key}"
    if fmt == "generic":
        body = {"mcpServers": {"connector": {"type": "http", "url": url, "headers": {"Authorization": header}}}}
        return json.dumps(body, indent=2)
    if fmt == "oddboro":
        return f"Address: {url}\nHeader name: Authorization\nHeader value: {header}"
    raise ValueError(f"unknown format; use one of {', '.join(FORMATS)}")


def address_problem(url: str, fmt: str) -> str | None:
    """A fixed message when the address is not acceptable. It never echoes the address."""
    if _BAD_CHARS.search(url):
        return BAD_ADDRESS
    try:
        parts = urlsplit(url)
        parts.port  # noqa: B018 - raises ValueError on a bad port
    except ValueError:
        return BAD_ADDRESS
    if parts.scheme not in ("http", "https") or not parts.hostname or "@" in parts.netloc:
        return BAD_ADDRESS
    if fmt == "oddboro":
        if parts.scheme != "https":
            return ODDBORO_HTTPS
        return _oddboro_problem(parts.hostname, parts.path)
    return None


_IPV4 = re.compile(r"(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(\.(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3}")
_NUMERIC_LABEL = re.compile(r"0x[0-9a-f]*|[0-9]+")


def _oddboro_problem(host: str, path: str) -> str | None:
    """Refuse an address whose host or path Oddboro's URL parser would rewrite.

    Only then is `oddboro_service_id` sure to match the id Oddboro builds. Oddboro reads the
    address with the WHATWG URL parser: it rewrites IPv6 and short IPv4 forms, percent-encodes
    some characters and resolves `.` and `..` path steps.
    """
    if not _ODDBORO_HOST.fullmatch(host):
        return ODDBORO_HOST
    last = host.rstrip(".").rsplit(".", 1)[-1]
    if _NUMERIC_LABEL.fullmatch(last) and not _IPV4.fullmatch(host):
        return ODDBORO_HOST
    for segment in path.split("/"):
        if not segment:
            continue
        if segment in (".", "..") or not _ODDBORO_SEGMENT.fullmatch(segment):
            return ODDBORO_PATH
    return None


def oddboro_service_id(url: str) -> str:
    """The service id Oddboro gives a server named by its address.

    Host name plus path, a leading `io.github.` dropped, lower case, every run of characters
    outside `a-z0-9` made one `-`, then one `-` trimmed from each end. No port, no query.
    Call it only on an address `address_problem(url, "oddboro")` accepts.
    """
    parts = urlsplit(url)
    text = f"{parts.hostname or ''}{parts.path or '/'}"
    text = re.sub(r"^io\.github\.", "", text).lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return re.sub(r"^-|-$", "", text)


def oddboro_longest_name(url: str, tool_names: list[str]) -> int:
    """The length of the longest full tool name Oddboro builds: `mcp__<service id>__<tool>`."""
    service = oddboro_service_id(url)
    return max(len(f"mcp__{service}__{name}") for name in tool_names)


def oddboro_too_long(length: int) -> str:
    """The fixed refusal. It names the computed length and the limit, never the address."""
    return (
        f"refused: Oddboro would name a tool with {length} characters, over its limit of "
        f"{ODDBORO_NAME_LIMIT}; use a shorter address, or fixed tools only; nothing was changed"
    )


def oddboro_near_limit(length: int) -> str:
    """The fixed warning for a name over the safe margin but within the limit."""
    return (
        f"warning: Oddboro would name a tool with {length} characters; past "
        f"{ODDBORO_NAME_WARN} leaves little margin across Oddboro versions"
    )


ODDBORO_NOT_SNAKE = (
    "refused: Oddboro tools need snake_case names (a-z, 0-9 and _); "
    "use fixed tools only or rename the pinned tool; nothing was changed"
)


def oddboro_names_problem(url: str, tool_names: list[str]) -> tuple[str | None, str | None]:
    """(refusal, warning) for the names an Oddboro agent would see. Each is fixed text or None."""
    if not all(SNAKE_CASE.fullmatch(name) for name in tool_names):
        return ODDBORO_NOT_SNAKE, None
    longest = oddboro_longest_name(url, tool_names)
    if longest > ODDBORO_NAME_LIMIT:
        return oddboro_too_long(longest), None
    if longest > ODDBORO_NAME_WARN:
        return None, oddboro_near_limit(longest)
    return None, None


def _agent_dict(agent: AgentGrant) -> dict:
    data = {
        "name": agent.name,
        "scopes": sorted(s.value for s in agent.scopes),
        "reach": agent.reach.value,
        "addons": sorted(a.value for a in agent.addons),
        "enabled": agent.enabled,
    }
    if not agent.pinned_tools:  # the default is not written, so older files stay the same
        data["pinned_tools"] = False
    if agent.call_timeout_s is not None:
        data["call_timeout_s"] = agent.call_timeout_s
    return data


def render_agents(agents: list[AgentGrant]) -> bytes:
    """`agents.yaml` text from validated models. Comments in an older file are not kept."""
    data = {"version": 1, "agents": [_agent_dict(a) for a in agents]}
    return yaml.safe_dump(data, sort_keys=False).encode("utf-8")


def read_agents_bytes(manifest_dir: Path) -> bytes:
    return (manifest_dir / AGENTS_FILE).read_bytes()


def write_agents_bytes(manifest_dir: Path, data: bytes) -> None:
    """Atomic: a temporary file in the same folder, then `os.replace`. The mode is kept."""
    target = manifest_dir / AGENTS_FILE
    mode = target.stat().st_mode & 0o777 if target.exists() else 0o644
    fd, tmp = tempfile.mkstemp(dir=manifest_dir, prefix=".agents-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, target)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def create_key_file(path: Path) -> int:
    """Create `path` exclusively, never through a link, mode 0600. Return the open descriptor.

    `O_EXCL` with `O_CREAT` fails on any existing name, a link included, on every system.
    """
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    return os.open(path, flags | portable.nofollow_flag() | portable.binary_flag(), 0o600)


class KeyFile:
    """A key file this run creates. `discard` removes it only when this run's own open worked.

    A path that already existed is never ours: the exclusive open fails, `created` stays False,
    and `discard` leaves the other party's file alone.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self.created = False
        self._fd: int | None = None

    def create(self) -> None:
        self._fd = create_key_file(self.path)
        self.created = True

    def write(self, key: str) -> None:
        """Write the whole key, then close. Any fault leaves the caller to `discard`."""
        assert self._fd is not None
        data = (key + "\n").encode("utf-8")
        try:
            view = memoryview(data)
            while view:
                view = view[os.write(self._fd, view):]
            os.fsync(self._fd)
        finally:
            self.close()

    def close(self) -> None:
        if self._fd is not None:
            with contextlib.suppress(OSError):
                os.close(self._fd)
            self._fd = None

    def discard(self) -> None:
        self.close()
        if self.created:
            with contextlib.suppress(OSError):
                self.path.unlink()
            self.created = False


@contextlib.contextmanager
def state_lock(state: Path):
    """One exclusive lock for a whole read, change and write of `agents.yaml` and the keys.

    `open_state` runs first: every refusal of the state folder applies before the lock touches it,
    and `state.db` exists before `connector.lock`. The lock file is never followed through a link
    and must be a regular file with one link. Any fault gives `StateDirError` with fixed text.
    POSIX locks with `fcntl.flock`; Windows with `msvcrt.locking` (`portable.exclusive_lock`).
    """
    open_state(state).close()
    try:
        fd = portable.open_no_link(Path(state) / LOCK_FILE, os.O_RDWR | os.O_CREAT, 0o600)
    except OSError as exc:  # its text would hold the path, so only fixed text goes on
        if exc.errno == errno.EACCES:  # a lock that exists but cannot be opened
            raise StateDirError(LOCK_UNREADABLE) from None
        raise StateDirError(LOCK_REFUSED) from None  # ELOOP for a link, EISDIR for a folder
    try:
        opened = os.fstat(fd)
        if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
            raise StateDirError(LOCK_REFUSED)
        portable.owner_only_file(fd)  # an older lock kept its mode; every state file is 0600
        with contextlib.ExitStack() as held:
            try:
                held.enter_context(portable.exclusive_lock(fd))
            except portable.LockBusy:
                raise StateDirError(LOCK_BUSY) from None
            yield
    finally:
        os.close(fd)  # closing releases the lock
