"""An in-process door for tests: fake upstreams, a memory vault, no socket, no network.

`in_process(app)` runs the app's lifespan (refresh, the session manager, the purge and reload
loops) and returns an httpx client bound to it through `httpx.ASGITransport`.
"""

from __future__ import annotations

import contextlib
import shutil
from collections.abc import AsyncIterator
from pathlib import Path

import httpx

from universal_connector.upstreams.base import ToolInfo
from universal_connector.vault import MemorySecretStore

EXAMPLES = Path(__file__).resolve().parents[2] / "examples" / "manifest"


class FakeUpstream:
    def __init__(self, tools: list[str]) -> None:
        self.tools = tools
        self.calls: list[tuple[str, dict]] = []

    async def list_tools(self) -> list[ToolInfo]:
        return [ToolInfo(t, f"fake {t}", {"type": "object"}) for t in self.tools]

    async def call_tool(self, name: str, arguments: dict) -> str:
        self.calls.append((name, arguments))
        return f"ran {name}"

    async def probe(self):  # pragma: no cover - not used
        raise NotImplementedError

    def secret_values(self) -> list[str]:
        return []

    def purge(self) -> int:
        return 0


def fake_builder(manifest, store, machine) -> dict[str, FakeUpstream]:
    return {c.name: FakeUpstream([t.name for t in c.tools]) for c in manifest.connections}


def copy_examples(tmp_path: Path) -> Path:
    """A writable copy of the example manifest."""
    target = tmp_path / "manifest"
    shutil.copytree(EXAMPLES, target)
    return target


def memory_store() -> MemorySecretStore:
    return MemorySecretStore({})


@contextlib.asynccontextmanager
async def in_process(app, base_url: str = "https://door.localhost") -> AsyncIterator[httpx.AsyncClient]:
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url=base_url) as http:
            yield http


@contextlib.asynccontextmanager
async def lifespan_only(app) -> AsyncIterator[httpx.ASGITransport]:
    """The app's lifespan, and a transport for a client the test builds itself."""
    async with app.router.lifespan_context(app):
        yield httpx.ASGITransport(app=app)
