"""Upstream protocol and shared types. No secret value ever appears in an error text."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

DEFAULT_TTL_S = 900


@dataclass
class ToolInfo:
    name: str
    description: str
    input_schema: dict


@dataclass
class ProbeResult:
    ok: bool
    status: str  # one of: ok, needs-login, not-in-vault, dead
    detail: str


class UpstreamAuthError(Exception):
    """The upstream refused the login (401 or 403) or no usable login exists."""


class UpstreamError(Exception):
    """Any other upstream failure."""


class Upstream(Protocol):
    async def list_tools(self) -> list[ToolInfo]: ...

    async def call_tool(self, name: str, arguments: dict) -> str: ...

    async def probe(self) -> ProbeResult: ...

    def secret_values(self) -> list[str]:
        """Values held now, no duplicates. Used only for redaction."""
        ...

    def purge(self) -> int:
        """Drop holds that are 900 seconds old or older. Return how many were dropped."""
        ...


def scrub(text: str, values: list[str]) -> str:
    """Replace every known secret value in `text` with `[redacted]`. Empty values are ignored.

    The longest values go first, so no tail of a longer value survives a shorter one.
    """
    for value in sorted({v for v in values if v}, key=len, reverse=True):
        text = text.replace(value, "[redacted]")
    return text


def clean_error(exc: Exception, values: list[str]) -> Exception:
    """A fresh error of the same kind with scrubbed text. Raise it outside the `except` block."""
    kind = UpstreamAuthError if isinstance(exc, UpstreamAuthError) else UpstreamError
    return kind(scrub(str(exc), values))


class HoldBook:
    """Things that carry a secret value, each held with the time it was read."""

    def __init__(
        self, clock: Callable[[], float] = time.monotonic, ttl_s: int = DEFAULT_TTL_S
    ) -> None:
        self.clock = clock
        self.ttl_s = ttl_s
        self._holds: dict[str, tuple[float, Any, list[str]]] = {}

    def put(self, key: str, obj: Any, values: list[str]) -> None:
        self._holds[key] = (self.clock(), obj, list(values))

    def get(self, key: str) -> Any | None:
        hold = self._holds.get(key)
        return None if hold is None else hold[1]

    def held(self, key: str) -> tuple[Any, list[str]] | None:
        """The held object and the values it carries, or None. A call adds the values to `used`."""
        hold = self._holds.get(key)
        return None if hold is None else (hold[1], list(hold[2]))

    def drop_expired(self) -> int:
        now = self.clock()
        expired = [k for k, (stamp, _, _) in self._holds.items() if now - stamp >= self.ttl_s]
        for key in expired:
            del self._holds[key]
        return len(expired)

    def values(self) -> list[str]:
        seen: list[str] = []
        for _, _, values in self._holds.values():
            for value in values:
                if value and value not in seen:
                    seen.append(value)
        return seen
