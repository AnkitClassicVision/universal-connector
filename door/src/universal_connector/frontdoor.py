"""The front door: one MCP server over streamable HTTP, with a bearer gate in front.

The gate checks the key on every request, before any MCP handling. The tool list and every call
come from the router for the caller the gate named. No header and no token ever reaches a log line.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import re
import sys
import threading
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from pathlib import Path

from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.types import ASGIApp, Receive, Scope, Send

from universal_connector import audit, keys, portable
from universal_connector.machine import load_machine
from universal_connector.manifest import ManifestError, load_manifest
from universal_connector.models import AgentGrant, Manifest
from universal_connector.router import Router
from universal_connector.state import open_state
from universal_connector.upstreams.base import Upstream
from universal_connector.upstreams.factory import build_upstreams
from universal_connector.vault import SecretStore

LOG_ROOT = "universal_connector"
log = logging.getLogger(f"{LOG_ROOT}.frontdoor")

LOOPBACK_HOSTS = ("127.0.0.1", "::1")
DEFAULT_PORT = 8765
PURGE_INTERVAL_S = 60
RELOAD_POLL_S = 3.0
INSTRUCTIONS = "Call connector_guide first. It lists what you can reach."
UNAUTHORIZED = {"error": "unauthorized"}
FORBIDDEN = {"error": "forbidden"}
UNAVAILABLE = {"error": "unavailable"}
TOO_LARGE = {"error": "request too large"}
MAX_BODY_BYTES = 1024 * 1024
LOOPBACK_ONLY = "loopback only in version 1"
PORT_RANGE = "port must be 1 to 65535"

_WHITESPACE = re.compile(r"\s+")

UpstreamBuilder = Callable[[Manifest, SecretStore, dict], dict[str, Upstream]]


class Holder:
    """The current good manifest, router and upstreams. A failed reload changes nothing."""

    def __init__(
        self,
        manifest_dir: Path,
        state_dir: Path,
        store: SecretStore,
        upstream_builder: UpstreamBuilder = build_upstreams,
        machine_file: Path | None = None,
    ) -> None:
        self._manifest_dir = Path(manifest_dir)
        self._state_dir = Path(state_dir)
        self._store = store
        self._builder = upstream_builder
        self._machine_file = machine_file  # None: `UCONNECTOR_MACHINE_FILE`, else ./machine.yaml
        self._last_error: str | None = None
        # The reload counter BEFORE the files are read: a reload asked while the door is still
        # starting (its first refresh can be slow) is then newer than this and gets applied.
        # An unreadable counter gives 0, so the first good look reloads once rather than never.
        try:
            self.reload_baseline = audit.reload_requested(self._state_dir)
        except Exception:  # noqa: BLE001 - fixed fallback; the error text could hold a path
            self.reload_baseline = 0
        # Raises ManifestError (or another error) when the first load fails: there is no good state yet.
        self._current = self._build()

    def _build(self) -> tuple[Manifest, Router, dict[str, Upstream]]:
        manifest = load_manifest(self._manifest_dir)
        machine = load_machine(self._machine_file)
        upstreams = self._builder(manifest, self._store, machine)
        router = Router(manifest, upstreams, self._state_dir)  # opens and closes the state once
        return manifest, router, upstreams

    @property
    def router(self) -> Router:
        return self._current[1]

    @property
    def manifest(self) -> Manifest:
        return self._current[0]

    @property
    def upstreams(self) -> dict[str, Upstream]:
        return self._current[2]

    @property
    def store(self) -> SecretStore:
        return self._store

    @property
    def last_error(self) -> str | None:
        return self._last_error

    def current(self) -> tuple[Manifest, Router, dict[str, Upstream]]:
        """Manifest, router and upstreams that belong together. Read once per request."""
        return self._current

    def reload(self) -> list[str]:
        """Build a new router from the files. Swap it in only when there are no problems."""
        try:
            built = self._build()
        except ManifestError as err:
            problems = list(err.problems)
        except Exception as exc:  # noqa: BLE001 - only the type name is kept, never a value
            problems = [f"reload failed: {type(exc).__name__}"]
        else:
            self._current = built
            self._last_error = None
            return []
        self._last_error = "; ".join(problems)
        return problems

    async def reload_and_refresh(self) -> list[str]:
        problems = self.reload()
        if not problems:
            await self.router.refresh()
        return problems


# -- the gate ----------------------------------------------------------------------------------


def _token(scope: Scope) -> str | None:
    """The presented key, or None. Exactly one Authorization header.

    Two forms: `Bearer <key>`, the scheme in any letter case, or the bare `<key>` alone, taken
    exactly as sent. Either way the key then passes the same hash check. `Bearer` alone, another
    scheme, or anything with a space inside the key gives None.
    """
    values = [v for k, v in scope.get("headers", []) if k == b"authorization"]
    if len(values) != 1:  # none, or several: refused, never guessed
        return None
    text = values[0].decode("latin-1").strip()
    parts = _WHITESPACE.split(text, maxsplit=1)
    if len(parts) == 1:  # one word: a bare key, or nothing, or the scheme with no key
        return text if text and text.lower() != "bearer" else None
    if parts[0].lower() != "bearer":
        return None
    token = parts[1].strip()
    if not token or _WHITESPACE.search(token):
        return None
    return token


class _Gate:
    def __init__(self, manager: StreamableHTTPSessionManager, holder: Holder, state_dir: Path):
        self.manager = manager
        self.holder = holder
        self.state_dir = state_dir

    async def _refuse(self, scope: Scope, receive: Receive, send: Send, status: int, body: dict):
        await JSONResponse(body, status_code=status)(scope, receive, send)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        token = _token(scope)
        if token is None:
            await self._refuse(scope, receive, send, 401, UNAUTHORIZED)
            return
        try:
            # On every request: a revoke acts at once. Off the event loop: a locked state file
            # stalls this request only.
            name = await asyncio.to_thread(keys.verify, self.state_dir, token)
        except Exception:  # noqa: BLE001 - fail closed; nothing about the request is logged
            log.error("key check failed: state unavailable")
            await self._refuse(scope, receive, send, 503, UNAVAILABLE)
            return
        agent = self.holder.manifest.agent(name) if name is not None else None
        if agent is None:
            await self._refuse(scope, receive, send, 401, UNAUTHORIZED)
            return
        if not agent.enabled:
            await self._refuse(scope, receive, send, 403, FORBIDDEN)
            return
        if scope.get("method") != "POST":
            # Stateless JSON mode needs no GET stream, and an open stream would outlive a revoke.
            await JSONResponse(
                {"error": "method not allowed"}, status_code=405, headers={"Allow": "POST"}
            )(scope, receive, send)
            return
        replay = await self._limited_body(scope, receive, send)
        if replay is None:
            return
        scope = {**scope, "state": {**scope.get("state", {}), "caller": agent.name}}
        await self.manager.handle_request(scope, replay, send)

    async def _limited_body(self, scope: Scope, receive: Receive, send: Send) -> Receive | None:
        """Refuse a body over the limit with 413. Otherwise return a `receive` that replays it."""
        for key, value in scope.get("headers", []):
            if key == b"content-length":
                try:
                    declared = int(value)
                except ValueError:
                    declared = -1
                if declared < 0:
                    await self._refuse(scope, receive, send, 400, {"error": "bad request"})
                    return None
                if declared > MAX_BODY_BYTES:
                    await self._refuse(scope, receive, send, 413, TOO_LARGE)
                    return None
        messages: list[dict] = []
        total = 0
        while True:  # counted as it is read, so a chunked body cannot slip past
            message = await receive()
            messages.append(message)
            if message["type"] == "http.disconnect":
                return None
            total += len(message.get("body", b""))
            if total > MAX_BODY_BYTES:
                await self._refuse(scope, receive, send, 413, TOO_LARGE)
                return None
            if not message.get("more_body", False):
                break
        pending = iter(messages)

        async def replay() -> dict:
            try:
                return next(pending)
            except StopIteration:
                return await receive()

        return replay


def hosts_for(port: int) -> list[str]:
    """The only Host header values the door accepts, with the real bound port."""
    return [f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"]


def agent_for(holder: Holder, request: object) -> AgentGrant | None:
    """The enabled agent the gate named for this request, read from the current manifest."""
    name = getattr(getattr(request, "state", None), "caller", None)
    agent = holder.manifest.agent(name) if isinstance(name, str) else None
    return agent if agent is not None and agent.enabled else None


def _exception_type(record: logging.LogRecord) -> str | None:
    info = record.exc_info
    if isinstance(info, tuple) and isinstance(info[0], type):
        return info[0].__name__
    if isinstance(record.msg, BaseException):  # e.g. uvicorn's `logger.error(exc)`
        return type(record.msg).__name__
    return None


class _AllowListHandler(logging.StreamHandler):
    """Logs are an allow-list. A `universal_connector.*` record prints as written; those hold
    fixed text.

    Any other record prints only its logger name, its level and its exception type name. No
    message, no arguments and no traceback, so no third-party text can carry a request value.
    """

    def format(self, record: logging.LogRecord) -> str:
        parts = [record.name, record.levelname]
        if record.name == LOG_ROOT or record.name.startswith(f"{LOG_ROOT}."):
            parts.append(record.getMessage())
        kind = _exception_type(record)
        if kind is not None:
            parts.append(kind)
        return " ".join(parts)

    def handleError(self, record: logging.LogRecord) -> None:
        # The stock version prints the record's raw message and arguments.
        with contextlib.suppress(Exception):
            self.stream.write(f"{record.name} {record.levelname} unwritable record\n")


def _log_uncaught(exc_type, exc, tb) -> None:  # a traceback can quote a request value
    logging.getLogger("uncaught").error("", exc_info=(exc_type, exc, tb))


def _log_thread_uncaught(args: threading.ExceptHookArgs) -> None:
    if args.exc_type is not SystemExit:
        _log_uncaught(args.exc_type, args.exc_value, args.exc_traceback)


def _log_unraisable(args) -> None:
    _log_uncaught(args.exc_type, args.exc_value, args.exc_traceback)


def configure_logging() -> None:
    """Install the allow-list as the only log output. Used by `serve`; tests run it there.

    The SDK logs request bodies and header values through the root logger, the `mcp` tree and
    tracebacks (`mcp/shared/session.py`, `lowlevel/server.py`, `streamable_http_manager.py`).
    Silencing names is not enough, so every line goes through one root handler that drops all
    third-party text. Python's own fallbacks (the last-resort handler, `warnings` and the
    uncaught-exception hooks) are routed through the same handler.
    """
    handler = _AllowListHandler(sys.stderr)
    root = logging.getLogger()
    for old in list(root.handlers):
        root.removeHandler(old)
    for logger in list(logging.Logger.manager.loggerDict.values()):
        if isinstance(logger, logging.Logger):  # no other handler may write a line
            for old in list(logger.handlers):
                logger.removeHandler(old)
    root.addHandler(handler)
    root.setLevel(logging.WARNING)
    logging.lastResort = handler  # records from a logger that does not propagate
    logging.captureWarnings(True)  # warning texts can quote a value
    sys.excepthook = _log_uncaught
    threading.excepthook = _log_thread_uncaught
    sys.unraisablehook = _log_unraisable
    logging.getLogger("mcp").setLevel(logging.ERROR)
    access = logging.getLogger("uvicorn.access")
    access.disabled = True
    access.setLevel(logging.CRITICAL + 1)


# -- purge loop --------------------------------------------------------------------------------


def purge_once(holder: Holder) -> None:
    """Purge the store and every upstream of the current router. One failure stops no other purge."""
    targets = [holder.store, *holder.upstreams.values()]
    for target in targets:
        purge = getattr(target, "purge", None)  # MemorySecretStore holds no timed cache
        if purge is None:
            continue
        try:
            purge()
        except Exception:  # the loop must survive; the handler prints the type only
            log.exception("purge failed")


async def _purge_loop(holder: Holder, sleep: Callable[[float], Awaitable[None]], interval: float):
    while True:
        await sleep(interval)
        purge_once(holder)


# -- reload requests (`uconnector reload`, every system) -----------------------------------------


async def reload_check(holder: Holder, state_dir: Path, seen: int) -> int:
    """One look at the reload counter. Return the number now seen.

    A number that moved since `seen` reloads the manifest and writes the answer back. The first
    `seen` is the holder's baseline, read before the files were. A state fault logs one fixed
    line and changes nothing.
    """
    try:
        number = await asyncio.to_thread(audit.reload_requested, state_dir)
    except Exception:  # noqa: BLE001 - fixed text only
        log.error("reload check failed: state unavailable")
        return seen
    if number == seen:
        return number
    problems = await holder.reload_and_refresh()
    try:
        await asyncio.to_thread(audit.mark_reloaded, state_dir, number, not problems)
    except Exception:  # noqa: BLE001 - fixed text only
        log.error("reload answer failed: state unavailable")
    return number


async def _reload_loop(
    holder: Holder, state_dir: Path, sleep: Callable[[float], Awaitable[None]], interval: float
):
    seen = await reload_check(holder, state_dir, holder.reload_baseline)  # at once, no wait
    while True:
        await sleep(interval)
        seen = await reload_check(holder, state_dir, seen)


# -- the app -----------------------------------------------------------------------------------


def build_app(
    holder: Holder,
    state_dir: Path,
    *,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    purge_interval_s: float = PURGE_INTERVAL_S,
    door_hosts: Sequence[str] = (),
    reload_sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    reload_poll_s: float = RELOAD_POLL_S,
) -> ASGIApp:
    state_dir = Path(state_dir)
    open_state(state_dir).close()  # the folder exists before the first request
    server: Server = Server("connector", instructions=INSTRUCTIONS)

    def caller_agent() -> AgentGrant | None:
        return agent_for(holder, server.request_context.request)

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        agent = caller_agent()
        if agent is None:
            return []
        out: list[types.Tool] = []
        for tool in holder.router.visible(agent):
            out.append(
                types.Tool(
                    name=tool.name,
                    description=tool.description,
                    inputSchema=tool.input_schema,
                    annotations=types.ToolAnnotations(
                        readOnlyHint=tool.read_only,
                        **({"destructiveHint": False} if tool.read_only else {}),
                    ),
                )
            )
        return out

    # The router checks policy and arguments itself. The SDK's cached schemas are shared by callers.
    @server.call_tool(validate_input=False)
    async def call_tool(name: str, arguments: dict) -> types.CallToolResult:
        agent = caller_agent()
        if agent is None:
            text, ok = "Refused: unauthorized.", False
        else:
            result = await holder.router.call(agent, name, arguments)
            text, ok = result.text, result.ok
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=text)], isError=not ok
        )

    # Exact Host values with the real port, never a wildcard. The list stays empty (every Host gets
    # 421) until `app.state.set_port` runs with the bound port.
    security = TransportSecuritySettings(enable_dns_rebinding_protection=True, allowed_hosts=[])
    manager = StreamableHTTPSessionManager(
        app=server, json_response=True, stateless=True, security_settings=security
    )

    @contextlib.asynccontextmanager
    async def lifespan(_: Starlette) -> AsyncIterator[None]:
        await holder.router.refresh()  # once, before the first request. Never on a timer.
        async with manager.run():
            tasks = [
                asyncio.create_task(_purge_loop(holder, sleep, purge_interval_s)),
                asyncio.create_task(_reload_loop(holder, state_dir, reload_sleep, reload_poll_s)),
            ]
            try:
                yield
            finally:
                for task in tasks:
                    task.cancel()
                for task in tasks:
                    with contextlib.suppress(asyncio.CancelledError):
                        await task

    gate = _Gate(manager, holder, state_dir)
    app = Starlette(
        routes=[Route("/mcp", endpoint=gate, methods=["GET", "POST", "DELETE"])],
        lifespan=lifespan,
    )
    # `POST /mcp/` must give 404. A redirect would answer before the gate and echo the Host.
    app.router.redirect_slashes = False

    extra_hosts = list(door_hosts)  # exact values, already checked by `machine.door_hosts`

    def set_port(port: int) -> None:
        security.allowed_hosts = [*hosts_for(port), *extra_hosts]

    app.state.set_port = set_port
    return app


# -- serving -----------------------------------------------------------------------------------


def install_sighup(loop: asyncio.AbstractEventLoop, holder: Holder) -> Callable[[], None]:
    """On SIGHUP, schedule `reload_and_refresh` on `loop`. Returns a function that removes it.

    Windows has no SIGHUP, and its event loop takes no signal handler: there this does nothing
    and `uconnector reload` is the only way to reload.
    """
    hup = portable.reload_signal()
    if hup is None:
        return lambda: None
    pending: set[asyncio.Task] = set()

    def on_hup() -> None:
        task = loop.create_task(holder.reload_and_refresh())
        pending.add(task)
        task.add_done_callback(pending.discard)

    try:
        loop.add_signal_handler(hup, on_hup)
    except (NotImplementedError, RuntimeError, ValueError):
        return lambda: None
    return lambda: loop.remove_signal_handler(hup)


def check_bind(host: str, port: int) -> None:
    """Refuse a bind outside version 1. The error texts are fixed and quote no input."""
    if host not in LOOPBACK_HOSTS:
        raise ValueError(LOOPBACK_ONLY)
    if not 1 <= port <= 65535:  # the Host check needs the real port
        raise ValueError(PORT_RANGE)


async def serve(
    holder: Holder, state_dir: Path, host: str, port: int, door_hosts: Sequence[str] = ()
) -> None:
    check_bind(host, port)  # a second check: a broken caller can never bind wider
    import uvicorn

    app = build_app(holder, state_dir, door_hosts=door_hosts)
    app.state.set_port(port)
    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="warning",
        log_config=None,  # uvicorn adds no handler of its own
        lifespan="on",
        access_log=False,
    )
    configure_logging()  # after uvicorn's config, so nothing it sets up can bypass it
    remove = install_sighup(asyncio.get_running_loop(), holder)
    try:
        await uvicorn.Server(config).serve()
    finally:
        remove()
