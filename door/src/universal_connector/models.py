"""Manifest data models. Names and vault pointers only, never secret values."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt


class Tier(str, Enum):
    green = "green"
    yellow = "yellow"
    red = "red"
    black = "black"


class Scope(str, Enum):
    work = "work"
    restricted = "restricted"  # for data no agent may reach; cannot be granted in this version
    personal = "personal"


class Reach(str, Enum):
    starter = "starter"
    full_read = "full-read"


class AddOn(str, Enum):
    drafts = "drafts"
    browser = "browser"
    computer = "computer"


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ToolSpec(_Model):
    name: str
    tier: Tier
    pinned: StrictBool = False
    timeout_s: StrictInt = 60


class Auth(_Model):
    type: Literal["none", "header", "bearer", "google-oauth"]
    header: str | None = None
    secret: str | None = None
    token_secret: str | None = None
    account: str | None = None
    fields: dict[str, str] = {}


class Connection(_Model):
    name: str
    kind: Literal["mcp-remote", "mcp-stdio", "google", "multica", "browser", "computer"]
    upstream: str | None = None
    auth: Auth
    scopes: set[Scope] = Field(min_length=1)
    reach: Reach
    tools: list[ToolSpec]
    probe: str | None = None
    options: dict[str, Any] = {}


class AgentGrant(_Model):
    name: str
    scopes: set[Scope] = Field(min_length=1)
    reach: Reach
    addons: set[AddOn] = set()
    enabled: StrictBool = True
    pinned_tools: StrictBool = True
    # The most one call of this agent may take, retry included. None: each tool's own timeout.
    call_timeout_s: StrictInt | None = None


class Manifest(_Model):
    version: StrictInt
    connections: list[Connection]
    agents: list[AgentGrant]

    def connection(self, name: str) -> Connection | None:
        return next((c for c in self.connections if c.name == name), None)

    def agent(self, name: str) -> AgentGrant | None:
        return next((a for a in self.agents if a.name == name), None)
