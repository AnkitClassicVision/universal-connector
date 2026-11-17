"""Run the real `frontdoor.serve` with fake upstreams, so a test can watch a real process.

Usage: python -m helpers.serve_child MANIFEST_DIR STATE_DIR PORT

The store is in memory and the upstreams are fakes, so the child makes no network call and
reads no secret. It binds what `serve` binds: 127.0.0.1 and the given port.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import sys
import threading
from pathlib import Path

from universal_connector import frontdoor
from universal_connector.upstreams.base import ToolInfo
from universal_connector.vault import MemorySecretStore


class FakeUpstream:
    def __init__(self, tools: list[str]) -> None:
        self.tools = tools

    async def list_tools(self) -> list[ToolInfo]:
        return [ToolInfo(t, f"fake {t}", {"type": "object"}) for t in self.tools]

    async def call_tool(self, name: str, arguments: dict) -> str:
        digest = hashlib.sha256(json.dumps(arguments, sort_keys=True).encode()).hexdigest()
        return f"ran {name} {digest}"

    async def probe(self):  # pragma: no cover - not used
        raise NotImplementedError

    def secret_values(self) -> list[str]:
        return []

    def purge(self) -> int:
        return 0


def build(manifest, store, machine) -> dict[str, FakeUpstream]:
    return {c.name: FakeUpstream([t.name for t in c.tools]) for c in manifest.connections}


WIRING_FLAG = "--print-wiring"
EXIT_LINE = "serve child stopped on an exit request"


SRC_DIR = Path(__file__).resolve().parents[2] / "src"


def imports_this_tree() -> bool:
    """True when `connector` came from this tree's `src`, and `src` precedes site-packages."""
    entries = [Path(p or ".").resolve() for p in sys.path]
    if SRC_DIR not in entries:
        return False
    site = [i for i, p in enumerate(entries) if p.name in ("site-packages", "dist-packages")]
    first = entries.index(SRC_DIR)
    return (not site or first < min(site)) and Path(frontdoor.__file__).resolve().is_relative_to(
        SRC_DIR
    )


def wiring() -> dict[str, bool]:
    """Booleans only: is each logging hook and setting of `configure_logging` in place?"""
    root = logging.getLogger()
    access = logging.getLogger("uvicorn.access")
    return {
        "imports_this_tree": imports_this_tree(),
        "one_allow_list_root_handler": len(root.handlers) == 1
        and isinstance(root.handlers[0], frontdoor._AllowListHandler),
        "last_resort_is_allow_list": isinstance(logging.lastResort, frontdoor._AllowListHandler),
        "warnings_captured": logging._warnings_showwarning is not None,  # type: ignore[attr-defined]
        "sys_hook": sys.excepthook is frontdoor._log_uncaught,
        "thread_hook": threading.excepthook is frontdoor._log_thread_uncaught,
        "unraisable_hook": sys.unraisablehook is frontdoor._log_unraisable,
        "mcp_at_error": logging.getLogger("mcp").level == logging.ERROR,
        "access_log_off": access.disabled and access.level > logging.CRITICAL,
        "uvicorn_has_no_handlers": not logging.getLogger("uvicorn").handlers
        and not logging.getLogger("uvicorn.error").handlers
        and not access.handlers,
    }


async def _report_when_listening(port: int) -> None:
    for _ in range(1500):
        try:
            _, writer = await asyncio.open_connection("127.0.0.1", port)
        except OSError:
            await asyncio.sleep(0.01)
            continue
        writer.close()
        break
    print("WIRING " + json.dumps(wiring(), sort_keys=True), file=sys.stderr, flush=True)


async def _run(holder, state: Path, port: int, report: bool) -> None:
    if report:
        reporter = asyncio.create_task(_report_when_listening(port))  # noqa: F841
    await frontdoor.serve(holder, state, "127.0.0.1", port)


def main(argv: list[str]) -> int:
    report = WIRING_FLAG in argv
    argv = [a for a in argv if a != WIRING_FLAG]
    manifest, state, port = Path(argv[0]), Path(argv[1]), int(argv[2])
    holder = frontdoor.Holder(manifest, state, MemorySecretStore({}), build)
    try:
        asyncio.run(_run(holder, state, port, report))
    except KeyboardInterrupt:
        pass
    except SystemExit:  # its text can quote a request value: one fixed line instead
        print(EXIT_LINE, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
