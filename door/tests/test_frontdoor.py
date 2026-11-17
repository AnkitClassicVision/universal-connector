from __future__ import annotations

import ast
import asyncio
import contextlib
import io
import json
import logging
import os
import re
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import anyio
import httpx
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from helpers.mcp_stub import run_app as _run_app
from universal_connector import audit, frontdoor, keys
from universal_connector.cli import main
from universal_connector.frontdoor import Holder, build_app
from universal_connector.scan import find_secrets
from universal_connector.upstreams.base import ToolInfo
from universal_connector.vault import MemorySecretStore


@contextlib.contextmanager
def run_app(app):
    """Serve on 127.0.0.1 with an OS-chosen port, then tell the app that port for its Host check."""
    with _run_app(app) as base:
        app.state.set_port(int(base.rsplit(":", 1)[1]))
        yield base


TESTS_DIR = Path(__file__).resolve().parent
SRC_DIR = TESTS_DIR.parent / "src"


def free_port() -> int:
    """A port the OS reports free on 127.0.0.1. Never the default 8765."""
    while True:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        if port != frontdoor.DEFAULT_PORT:
            return port


def listening(port: int) -> bool:
    with socket.socket() as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def _ready(base: str, key: str) -> bool:
    """Ready only if the door behaves like ours on both sides of the gate.

    The real key must get an MCP initialize result, and a made-up key must get 401. A foreign
    listener that answers 200 to everything fails the second half. Any failure to connect or
    answer is just not ready.
    """
    good = {"Authorization": f"Bearer {key}", **MCP_HEADERS}
    bad = {"Authorization": "Bearer pc_" + "x" * 43, **MCP_HEADERS}
    try:
        reply = httpx.post(f"{base}/mcp", json=INIT_BODY, headers=good, timeout=2)
        stranger = httpx.post(f"{base}/mcp", json=INIT_BODY, headers=bad, timeout=2)
    except httpx.HTTPError:
        return False
    return reply.status_code == 200 and "serverInfo" in reply.text and stranger.status_code == 401

@contextlib.contextmanager
def real_serve(env, tmp_path, extra_args: tuple[str, ...] = (), port: int | None = None):
    """Run the real `frontdoor.serve` in a child process: real uvicorn, real logging wiring.

    The child binds 127.0.0.1 on a free port, never 8765, with fake upstreams and a memory store.
    It is stopped in `finally`. After the block, `served.stderr` holds all it wrote, and the port
    is proved closed. The child imports this tree's `src` first, so a worktree that shares the
    virtual environment tests its own code. Ready means an authenticated call succeeded with the
    test key of agent alpha, so a stranger that takes the port in the gap can never pass.
    """
    port = free_port() if port is None else port
    err_path = tmp_path / "serve-stderr.txt"
    served = SimpleNamespace(base=f"http://127.0.0.1:{port}", stderr="")
    child_env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(SRC_DIR), str(TESTS_DIR)])}
    argv = [
        sys.executable, "-m", "helpers.serve_child",
        str(env.manifest), str(env.state), str(port), *extra_args,
    ]
    with open(err_path, "wb") as err:
        child = subprocess.Popen(
            argv, cwd=tmp_path, env=child_env,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=err,
        )
    try:
        deadline = time.monotonic() + 15
        while not _ready(served.base, env.keys["alpha"]):
            assert child.poll() is None, "serve exited before it was ready"
            assert time.monotonic() < deadline, "serve was not ready"
            time.sleep(0.02)
        yield served
    finally:
        child.send_signal(signal.SIGINT)
        try:
            child.wait(timeout=10)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()
        served.stderr = err_path.read_text(errors="replace")
    assert not listening(port)


_ALLOWED_LINE = re.compile(r"[\w.]+ (DEBUG|INFO|WARNING|ERROR|CRITICAL)( [A-Za-z_]\w*)?")


def stderr_leaks(text: str, *values: str) -> dict[str, bool]:
    """Which kinds of leak `text` shows. Booleans only, so a failing test prints no value."""
    lines = text.splitlines()
    return {
        "a request value": any(v in text for v in values),
        "the scheme word": "Bearer" in text,
        "a secret shape": bool(find_secrets(text)),
        "a free-text line": any(
            not line.startswith("universal_connector.") and not _ALLOWED_LINE.fullmatch(line)
            for line in lines
        ),
    }


async def rpc(base: str, headers: dict[str, str], body: dict) -> httpx.Response:
    async with httpx.AsyncClient(timeout=10) as http:
        return await http.post(
            f"{base}/mcp", content=json.dumps(body).encode(), headers={**MCP_HEADERS, **headers}
        )


CONNECTOR_YAML = """\
version: 1
connections:
  - name: mail
    kind: mcp-remote
    upstream: https://up.example.invalid/mcp
    auth: {type: none}
    scopes: [work]
    reach: starter
    tools:
      - {name: search, tier: green, pinned: true}
      - {name: draft, tier: yellow, pinned: true}
      - {name: wipe, tier: red}
  - name: diary
    kind: mcp-remote
    upstream: https://up.example.invalid/diary
    auth: {type: none}
    scopes: [personal]
    reach: starter
    tools:
      - {name: lookup, tier: green, pinned: true}
"""

AGENTS_YAML = """\
version: 1
agents:
  - {name: alpha, scopes: [work], reach: starter}
  - {name: beta, scopes: [work, personal], reach: full-read, addons: [drafts]}
  - {name: gamma, scopes: [work], reach: starter, enabled: false}
"""

INIT_BODY = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "t", "version": "0"},
    },
}
MCP_HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


class FakeUpstream:
    def __init__(self, tools: list[str]) -> None:
        self.tools = tools
        self.list_calls = 0
        self.purges = 0
        self.calls: list[tuple[str, dict]] = []

    async def list_tools(self) -> list[ToolInfo]:
        self.list_calls += 1
        return [ToolInfo(t, f"fake {t}", {"type": "object"}) for t in self.tools]

    async def call_tool(self, name: str, arguments: dict) -> str:
        self.calls.append((name, arguments))
        return f"ran {name}"

    async def probe(self):  # pragma: no cover - not used
        raise NotImplementedError

    def secret_values(self) -> list[str]:
        return []

    def purge(self) -> int:
        self.purges += 1
        return 0


class SpyStore(MemorySecretStore):
    def __init__(self) -> None:
        super().__init__({})
        self.purges = 0

    def purge(self) -> int:
        self.purges += 1
        return 0


class Builder:
    """An upstream builder that records every generation of fakes it made."""

    def __init__(self, fresh: bool = False) -> None:
        self.fresh = fresh
        self.generations: list[dict[str, FakeUpstream]] = []

    def __call__(self, manifest, store, machine) -> dict[str, FakeUpstream]:
        if self.generations and not self.fresh:
            return self.generations[0]
        made = {c.name: FakeUpstream([t.name for t in c.tools]) for c in manifest.connections}
        self.generations.append(made)
        return made

    @property
    def fakes(self) -> dict[str, FakeUpstream]:
        return self.generations[-1]


@pytest.fixture(autouse=True)
def _no_machine_file(monkeypatch, tmp_path):
    empty = tmp_path / "empty-machine.yaml"  # an explicit machine file must exist; empty is fine
    empty.write_text("")
    monkeypatch.setenv("UCONNECTOR_MACHINE_FILE", str(empty))


@pytest.fixture
def env(tmp_path):
    manifest = tmp_path / "manifest"
    manifest.mkdir()
    (manifest / "connector.yaml").write_text(CONNECTOR_YAML)
    (manifest / "agents.yaml").write_text(AGENTS_YAML)
    state = tmp_path / "state"
    builder = Builder()
    store = SpyStore()
    holder = Holder(manifest, state, store, builder)
    minted = {name: keys.mint(state, name) for name in ("alpha", "beta", "gamma", "ghost")}
    return SimpleNamespace(
        manifest=manifest, state=state, builder=builder, store=store, holder=holder, keys=minted
    )


def bearer(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


async def with_session(base: str, headers: dict[str, str], action):
    with anyio.fail_after(15):
        async with (
            httpx.AsyncClient(headers=headers, follow_redirects=False) as http,
            streamable_http_client(f"{base}/mcp", http_client=http) as (read, write, _),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            return await action(session)


async def list_names(session: ClientSession) -> list[str]:
    return [t.name for t in (await session.list_tools()).tools]


async def raw_post(base: str, headers: list[tuple[str, str]] | dict[str, str]):
    items = list(headers.items()) if isinstance(headers, dict) else list(headers)
    merged = httpx.Headers(list(MCP_HEADERS.items()) + items)
    async with httpx.AsyncClient() as http:
        return await http.post(f"{base}/mcp", json=INIT_BODY, headers=merged)


def tick_wait(ticks: list[int], target: int) -> None:
    deadline = time.monotonic() + 10
    while ticks[0] < target:
        assert time.monotonic() < deadline, "purge loop did not tick"
        time.sleep(0.005)


def fast_sleep():
    """A sleep that stands in for the 60-second wait: 10 ms, with a tick counter."""
    ticks = [0]

    async def sleep(_seconds: float) -> None:
        await asyncio.sleep(0.01)
        ticks[0] += 1

    return sleep, ticks


# -- the gate ----------------------------------------------------------------------------------


async def test_valid_key_lists_and_calls(env):
    async def act(session: ClientSession):
        names = await list_names(session)
        result = await session.call_tool("mail__search", {"q": "x"})
        return names, result

    with run_app(build_app(env.holder, env.state)) as base:
        names, result = await with_session(base, bearer(env.keys["alpha"]), act)
    assert names[:5] == [
        "connector_guide",
        "find_read_tools",
        "call_read_tool",
        "find_write_tools",
        "call_write_tool",
    ]
    assert "mail__search" in names
    assert result.isError is False
    assert result.content[0].text == "ran search"
    assert env.builder.fakes["mail"].calls == [("search", {"q": "x"})]


async def gate_post(env, headers: dict[str, str]):
    """Post straight to the app. A refusal never reaches the MCP layer, so no server is needed."""
    transport = httpx.ASGITransport(app=build_app(env.holder, env.state))
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as http:
        return await http.post("/mcp", json=INIT_BODY, headers={**MCP_HEADERS, **headers})


async def test_no_key_401(env):
    response = await gate_post(env, {})
    assert response.status_code == 401
    assert response.json() == {"error": "unauthorized"}
    assert response.text == '{"error":"unauthorized"}'


async def test_unknown_key_401(env):
    response = await gate_post(env, bearer(keys.KEY_PREFIX + "x" * 43))
    assert response.status_code == 401
    assert response.text == '{"error":"unauthorized"}'


async def test_key_for_agent_not_in_manifest_401(env):
    response = await gate_post(env, bearer(env.keys["ghost"]))
    assert response.status_code == 401


async def test_disabled_agent_403(env):
    response = await gate_post(env, bearer(env.keys["gamma"]))
    assert response.status_code == 403


async def test_malformed_headers_never_500(env):
    key = env.keys["alpha"]
    with run_app(build_app(env.holder, env.state)) as base:
        lower = await raw_post(base, {"Authorization": f"bearer {key}"})
        spaced = await raw_post(base, {"Authorization": f"Bearer    {key}"})
        shouting = await raw_post(base, {"Authorization": f"BEARER {key}"})
        padded = await raw_post(base, {"Authorization": f"Bearer\t{key}"})
        scheme_only = await raw_post(base, {"Authorization": "Bearer"})
        huge = await raw_post(base, {"Authorization": "Bearer " + "a" * 10000})
        no_scheme = await raw_post(base, {"Authorization": key})
        other_scheme = await raw_post(base, {"Authorization": f"Basic {key}"})
        inner_space = await raw_post(base, {"Authorization": f"Bearer {key} extra"})
        twice = await raw_post(
            base, [("Authorization", f"Bearer {key}"), ("Authorization", f"Bearer {key}")]
        )
        non_ascii = await raw_post(base, [("Authorization", "Bearer café".encode("latin-1"))])
    for ok in (lower, spaced, shouting, padded, no_scheme):  # a bare key is accepted too
        assert ok.status_code == 200
    for refused in (scheme_only, huge, other_scheme, inner_space, twice):
        assert refused.status_code == 401
        assert refused.text == '{"error":"unauthorized"}'
    assert non_ascii.status_code == 401


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (b"Bearer abc", "abc"),
        (b"bearer abc", "abc"),
        (b"BeArEr   abc", "abc"),
        (b"  Bearer abc  ", "abc"),
        (b"Bearer ", None),
        (b"Bearer   ", None),
        (b"Bearer", None),
        (b"", None),
        (b"abc", "abc"),  # a bare key, taken exactly as sent
        (b"  abc  ", "abc"),
        (b"bearer", None),
        (b"BEARER", None),
        (b"a b", None),
        (b"Bearer a b", None),
        (b"Bearer \xff\xfe", "\xff\xfe"),
        (b"Token abc", None),
    ],
)
def test_token_parsing_edge_cases(raw, expected):
    assert frontdoor._token({"headers": [(b"authorization", raw)]}) == expected


@pytest.mark.parametrize(
    "origin",
    ["SAME", "http://localhost", "null", "https://evil.example.invalid", "file://", "x",
     "chrome-extension://abc"],
)  # fmt: skip
async def test_any_origin_header_is_refused_and_no_origin_passes(env, origin):
    key = env.keys["alpha"]
    with run_app(build_app(env.holder, env.state)) as base:
        sent = base if origin == "SAME" else origin  # even the door's own origin is refused
        with_origin = await raw_post(base, {**bearer(key), "Origin": sent})
        keyless = await raw_post(base, {"Origin": sent})
        without = await raw_post(base, bearer(key))
    assert with_origin.status_code == 403
    assert sent not in with_origin.text
    assert keyless.status_code == 401  # the key check still comes first
    assert without.status_code == 200


async def test_bare_key_gets_the_same_hash_check(env):
    key = env.keys["alpha"]
    with run_app(build_app(env.holder, env.state)) as base:
        bare = await raw_post(base, {"Authorization": key})
        wrong_case = await raw_post(base, {"Authorization": key.upper()})
        cut = await raw_post(base, {"Authorization": key[:-1]})
        longer = await raw_post(base, {"Authorization": key + "x"})
        revoked_name = await raw_post(base, {"Authorization": env.keys["ghost"]})
    assert bare.status_code == 200
    for refused in (wrong_case, cut, longer, revoked_name):
        assert refused.status_code == 401
        assert refused.text == '{"error":"unauthorized"}'


def test_token_needs_exactly_one_header():
    assert frontdoor._token({"headers": []}) is None
    one = (b"authorization", b"Bearer abc")
    assert frontdoor._token({"headers": [one, one]}) is None


async def test_revoke_without_restart(env):
    async def call(session: ClientSession):
        return await session.call_tool("mail__search", {})

    key = env.keys["alpha"]
    with run_app(build_app(env.holder, env.state)) as base:
        first = await with_session(base, bearer(key), call)
        assert first.isError is False
        assert keys.revoke(env.state, "alpha") is True
        after = await raw_post(base, bearer(key))
    assert after.status_code == 401


async def test_verify_error_fails_closed(env, monkeypatch):
    def broken(directory, presented):
        raise RuntimeError("state gone")

    monkeypatch.setattr(frontdoor.keys, "verify", broken)
    response = await gate_post(env, bearer(env.keys["alpha"]))
    assert response.status_code == 503
    assert response.json() == {"error": "unavailable"}


async def test_host_header_must_match_port_exactly(env):
    auth = bearer(env.keys["alpha"])
    with run_app(build_app(env.holder, env.state)) as base:
        port = base.rsplit(":", 1)[1]
        bad = [
            "evil.example",
            "127.0.0.1:evil",
            f"localhost:{port}@evil.example",
            "127.0.0.1",
            f"127.0.0.1:{int(port) + 1}",
            f"127.0.0.1:{port}.evil.example",
        ]
        refused = [(await raw_post(base, {**auth, "Host": h})).status_code for h in bad]
        good = [
            (await raw_post(base, {**auth, "Host": h})).status_code
            for h in (f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}")
        ]
    assert refused == [421] * len(bad)
    assert good == [200, 200, 200]


TAIL_HOST = "door.tailnet-name.ts.net"


async def test_no_door_hosts_gives_only_loopback(env):
    app = build_app(env.holder, env.state)
    with run_app(app) as base:
        port = int(base.rsplit(":", 1)[1])
        status = (await raw_post(base, {**bearer(env.keys["alpha"]), "Host": TAIL_HOST})).status_code
    assert status == 421
    assert frontdoor.hosts_for(port) == [f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"]


async def test_listed_tailnet_host_with_key_gets_mcp_answer(env):
    app = build_app(env.holder, env.state, door_hosts=[TAIL_HOST, f"{TAIL_HOST}:8443"])
    auth = bearer(env.keys["alpha"])
    with run_app(app) as base:
        port = base.rsplit(":", 1)[1]
        replies = [
            await raw_post(base, {**auth, "Host": h})
            for h in (TAIL_HOST, f"{TAIL_HOST}:8443", f"127.0.0.1:{port}")
        ]
    assert [r.status_code for r in replies] == [200, 200, 200]
    assert all("serverInfo" in r.text for r in replies)


async def test_unlisted_tailnet_hosts_refused(env):
    app = build_app(env.holder, env.state, door_hosts=[TAIL_HOST])
    auth = bearer(env.keys["alpha"])
    with run_app(app) as base:
        bad = [
            "other.tailnet-name.ts.net",
            f"{TAIL_HOST}:8443",  # listed without a port: the port form is another value
            f"{TAIL_HOST}:1",
            f"sub.{TAIL_HOST}",
            f"{TAIL_HOST}.evil.example",
            f"{TAIL_HOST}@evil.example",
            "tailnet-name.ts.net",
            TAIL_HOST.upper(),
        ]
        refused = [(await raw_post(base, {**auth, "Host": h})).status_code for h in bad]
    assert refused == [421] * len(bad)


async def test_listed_tailnet_host_without_key_still_401(env):
    app = build_app(env.holder, env.state, door_hosts=[TAIL_HOST])
    with run_app(app) as base:
        no_key = await raw_post(base, {"Host": TAIL_HOST})
        wrong = await raw_post(base, {"Host": TAIL_HOST, **bearer("pc_" + "x" * 43)})
    assert no_key.status_code == 401
    assert wrong.status_code == 401


def test_door_hosts_do_not_leak_between_apps(env):
    first = build_app(env.holder, env.state, door_hosts=[TAIL_HOST])
    second = build_app(env.holder, env.state)
    first.state.set_port(8765)
    second.state.set_port(8765)  # must not see the first app's hosts


@pytest.mark.parametrize(
    "entry",
    ["*.tailnet-name.ts.net", "https://door.tailnet-name.ts.net", "100.64.0.1:8443",
     "Door.tailnet-name.ts.net", "door.tailnet-name.ts.net:0", "door.tailnet-name.ts.net/x",
     "user@door.tailnet-name.ts.net"],
)
def test_serve_cli_bad_door_hosts_stops_before_bind(env, tmp_path, monkeypatch, capsys, no_server, entry):
    machine = tmp_path / "bad-machine.yaml"
    machine.write_text(f"door_hosts:\n  - '{entry}'\n")
    monkeypatch.setenv("UCONNECTOR_MACHINE_FILE", str(machine))
    code = main(["serve", "--manifest", str(env.manifest), "--state", str(env.state)])
    captured = capsys.readouterr()
    assert code == 2
    assert captured.err == "bad door_hosts entry\n"
    assert captured.out == ""


def test_serve_cli_passes_door_hosts_to_serve(env, tmp_path, monkeypatch):
    machine = tmp_path / "good-machine.yaml"
    machine.write_text(f"door_hosts:\n  - '{TAIL_HOST}:8443'\n")
    monkeypatch.setenv("UCONNECTOR_MACHINE_FILE", str(machine))
    seen = {}

    async def fake_serve(holder, state, host, port, door_hosts=()):
        seen.update(host=host, port=port, door_hosts=list(door_hosts))

    monkeypatch.setattr(frontdoor, "serve", fake_serve)
    monkeypatch.setattr("universal_connector.cli.store_for", lambda machine: MemorySecretStore({}))
    code = main(["serve", "--manifest", str(env.manifest), "--state", str(env.state)])
    assert code == 0
    assert seen == {"host": "127.0.0.1", "port": 8765, "door_hosts": [f"{TAIL_HOST}:8443"]}


async def test_host_unset_port_refuses_everything(env):
    app = build_app(env.holder, env.state)  # set_port never called
    with _run_app(app) as base:
        response = await raw_post(base, bearer(env.keys["alpha"]))
    assert response.status_code == 421


async def test_trailing_slash_is_not_redirected(env):
    transport = httpx.ASGITransport(app=build_app(env.holder, env.state))
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as http:
        response = await http.post(
            "/mcp/", json=INIT_BODY, headers={**MCP_HEADERS, **bearer(env.keys["alpha"])}
        )
    assert response.status_code == 404
    assert "location" not in response.headers


async def test_body_over_limit_413(env):
    auth = {**MCP_HEADERS, **bearer(env.keys["alpha"])}
    transport = httpx.ASGITransport(app=build_app(env.holder, env.state))
    big = b"x" * (frontdoor.MAX_BODY_BYTES + 1)

    async def chunks():
        for start in range(0, len(big), 65536):
            yield big[start : start + 65536]

    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as http:
        by_length = await http.post("/mcp", content=big, headers=auth)
        chunked_request = http.build_request("POST", "/mcp", content=chunks(), headers=auth)
        assert "content-length" not in chunked_request.headers
        chunked = await http.send(chunked_request)
        unauthorized = await http.post("/mcp", content=big, headers=MCP_HEADERS)
    assert by_length.status_code == 413
    assert chunked.status_code == 413
    assert unauthorized.status_code == 401  # the key check comes first


async def test_get_and_delete_give_405(env):
    auth = bearer(env.keys["alpha"])
    transport = httpx.ASGITransport(app=build_app(env.holder, env.state))
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as http:
        got = await http.get("/mcp", headers={**auth, "Accept": "text/event-stream"})
        deleted = await http.delete("/mcp", headers=auth)
        anonymous = await http.get("/mcp")
    assert got.status_code == 405
    assert deleted.status_code == 405
    assert anonymous.status_code == 401


async def test_slow_verify_does_not_block_other_requests(env, monkeypatch):
    def verify(directory, presented):
        if presented == "slow":
            time.sleep(0.2)

    monkeypatch.setattr(frontdoor.keys, "verify", verify)
    transport = httpx.ASGITransport(app=build_app(env.holder, env.state))
    done: list[str] = []
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as http:

        async def post(token: str) -> None:
            await http.post("/mcp", json=INIT_BODY, headers={**MCP_HEADERS, **bearer(token)})
            done.append(token)

        await asyncio.gather(post("slow"), post("fast"))
    assert done == ["fast", "slow"]


async def test_reload_disabling_agent_gives_403(env):
    # A GET reaches its 405 only after the gate lets the agent in, so no MCP server is needed.
    transport = httpx.ASGITransport(app=build_app(env.holder, env.state))
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as http:
        headers = bearer(env.keys["alpha"])
        assert (await http.get("/mcp", headers=headers)).status_code == 405
        (env.manifest / "agents.yaml").write_text(
            AGENTS_YAML.replace("{name: alpha, scopes: [work], reach: starter}",
                                "{name: alpha, scopes: [work], reach: starter, enabled: false}")
        )
        assert env.holder.reload() == []
        assert (await http.get("/mcp", headers=headers)).status_code == 403


async def test_reload_removing_agent_gives_401(env):
    transport = httpx.ASGITransport(app=build_app(env.holder, env.state))
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as http:
        headers = bearer(env.keys["alpha"])
        assert (await http.get("/mcp", headers=headers)).status_code == 405
        (env.manifest / "agents.yaml").write_text(
            AGENTS_YAML.replace("  - {name: alpha, scopes: [work], reach: starter}\n", "")
        )
        assert env.holder.reload() == []
        assert (await http.get("/mcp", headers=headers)).status_code == 401


def test_caller_agent_checks_enabled(env):
    def request(name):
        return SimpleNamespace(state=SimpleNamespace(caller=name))

    assert frontdoor.agent_for(env.holder, request("alpha")).name == "alpha"
    assert frontdoor.agent_for(env.holder, request("gamma")) is None  # disabled
    assert frontdoor.agent_for(env.holder, request("ghost")) is None  # not in the manifest
    assert frontdoor.agent_for(env.holder, request(None)) is None
    assert frontdoor.agent_for(env.holder, SimpleNamespace()) is None
    assert frontdoor.agent_for(env.holder, None) is None


async def test_call_by_name_as_unseeing_agent_refused(env):
    async def fill_cache(session: ClientSession):
        return await list_names(session)

    async def raw_calls(session: ClientSession):
        return [
            await session.call_tool("diary__lookup", {}),  # hidden by scope
            await session.call_tool("mail__draft", {}),  # needs the drafts add-on
        ]

    with run_app(build_app(env.holder, env.state)) as base:
        seen_by_beta = await with_session(base, bearer(env.keys["beta"]), fill_cache)
        results = await with_session(base, bearer(env.keys["alpha"]), raw_calls)
    assert {"diary__lookup", "mail__draft"} <= set(seen_by_beta)
    assert [r.isError for r in results] == [True, True]
    assert env.builder.fakes["diary"].calls == []
    assert env.builder.fakes["mail"].calls == []


async def test_purge_loop_survives_a_failing_target(env, caplog):
    caplog.set_level(logging.DEBUG)
    marker = "MARKER-purge-secret"

    def failing() -> int:
        raise RuntimeError(marker)

    env.builder.fakes["mail"].purge = failing
    sleep, ticks = fast_sleep()
    with run_app(build_app(env.holder, env.state, sleep=sleep)):
        tick_wait(ticks, 2)
        before = env.store.purges
        tick_wait(ticks, ticks[0] + 3)  # the loop is still alive after the failure
        assert env.store.purges > before
        assert env.builder.fakes["diary"].purges >= 2  # a later target still ran every time
    failed = [r for r in caplog.records if r.getMessage() == "purge failed"]
    assert failed and all(r.exc_info and r.exc_info[0] is RuntimeError for r in failed)
    assert marker not in "\n".join(r.getMessage() for r in caplog.records)
    stream = io.StringIO()
    handler = frontdoor._AllowListHandler(stream)
    handler.emit(failed[0])  # what the real handler prints: the type name, never the text
    assert stream.getvalue().strip() == "universal_connector.frontdoor ERROR purge failed RuntimeError"


async def test_real_serve_wiring_keeps_request_values_out_of_stderr(env, tmp_path):
    """The real `serve`: `set_port` lets the right Host in, and stderr holds no request value."""
    marker = "MRK-body-value"
    pasted = env.keys["beta"]  # a key pasted into malformed arguments
    auth = bearer(env.keys["alpha"])

    async def call(session: ClientSession):
        return await session.call_tool("mail__search", {"q": "ok"})

    probes = [
        {  # arguments that are not an object
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {"name": "mail__search", "arguments": f"{marker}-5 {pasted}"},
        },
        {  # a malformed cancel notification
            "jsonrpc": "2.0",
            "method": "notifications/cancelled",
            "params": {"requestId": [f"{marker}-6"], "reason": f"{marker}-6 {pasted}"},
        },
        {  # a client response with a marker id
            "jsonrpc": "2.0",
            "id": f"{marker}-7",
            "result": {"k": f"{marker}-7 {pasted}"},
        },
    ]
    with real_serve(env, tmp_path) as served:
        first = await with_session(served.base, auth, call)
        statuses = [(await rpc(served.base, auth, body)).status_code for body in probes]
        after = await with_session(served.base, auth, call)  # the door still serves
    assert first.isError is False
    assert first.content[0].text.startswith("ran search ")
    assert after.isError is False
    assert statuses == [200, 202, 202]
    leaks = stderr_leaks(served.stderr, marker, pasted, env.keys["alpha"])
    assert leaks == dict.fromkeys(leaks, False)
    sdk_logged = "root WARNING" in served.stderr.splitlines()
    assert sdk_logged  # the SDK did log these requests, as names only


async def test_sdk_warnings_never_log_header_values(env, tmp_path):
    marker = "MRK-header-value"
    auth = bearer(env.keys["alpha"])

    async def unknown_tool(session: ClientSession):
        return await session.call_tool(f"{marker}-tool", {})

    with real_serve(env, tmp_path) as served:
        host = await raw_post(served.base, {**auth, "Host": f"{marker}.example"})
        origin = await raw_post(served.base, {**auth, "Origin": f"http://{marker}.example"})
        async with httpx.AsyncClient() as http:
            ctype = await http.post(
                f"{served.base}/mcp",
                content=b"{}",
                headers={**auth, "Accept": MCP_HEADERS["Accept"], "Content-Type": f"text/{marker}"},
            )
        unknown = await with_session(served.base, auth, unknown_tool)
    assert [host.status_code, origin.status_code, ctype.status_code] == [421, 403, 400]
    assert unknown.isError is True
    leaks = stderr_leaks(served.stderr, marker, env.keys["alpha"])
    assert leaks == dict.fromkeys(leaks, False)


def test_readiness_ignores_foreign_listener(env, tmp_path):
    """A stranger on the chosen port answers 200 to everything. `real_serve` must not call it ready."""
    import http.server
    import threading

    class Anything(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            body = b'{"result": {"serverInfo": {}}}'
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):  # no request line goes anywhere
            pass

    while True:
        stranger = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Anything)
        port = stranger.server_address[1]
        if port != frontdoor.DEFAULT_PORT:
            break
        stranger.server_close()
    thread = threading.Thread(target=stranger.serve_forever, daemon=True)
    thread.start()
    try:
        with (
            pytest.raises(AssertionError, match="serve (exited|was not ready)"),
            real_serve(env, tmp_path, port=port),
        ):
            pytest.fail("a foreign listener was reported as the door")
    finally:
        stranger.shutdown()
        stranger.server_close()
        thread.join(timeout=5)
    assert not listening(port)


async def test_uvicorn_config_has_no_log_config(env, monkeypatch):
    import uvicorn

    seen: dict = {}

    def record(*args, **kwargs):
        seen.update(kwargs)
        return SimpleNamespace(**kwargs)

    async def no_serve(self, *args, **kwargs):
        return None

    monkeypatch.setattr(uvicorn, "Config", record)
    monkeypatch.setattr(uvicorn.Server, "serve", no_serve)
    monkeypatch.setattr(frontdoor, "configure_logging", lambda: None)  # pytest's own handlers stay
    await frontdoor.serve(env.holder, env.state, "127.0.0.1", free_port())
    assert "log_config" in seen and seen["log_config"] is None
    assert seen["access_log"] is False


def test_serve_child_system_exit_guard(env, monkeypatch, capsys):
    from helpers import serve_child

    async def exits(*args, **kwargs):
        raise SystemExit("MRK-child-exit")

    monkeypatch.setattr(frontdoor, "serve", exits)
    code = serve_child.main([str(env.manifest), str(env.state), str(free_port())])
    captured = capsys.readouterr()
    assert code == 1
    assert captured.err == "serve child stopped on an exit request\n"
    assert "MRK" not in captured.out + captured.err


async def test_serve_child_logging_wiring(env, tmp_path):
    with real_serve(env, tmp_path, ("--print-wiring",)) as served:
        for _ in range(500):  # the child prints once it sees the port open
            if "WIRING " in (tmp_path / "serve-stderr.txt").read_text(errors="replace"):
                break
            await asyncio.sleep(0.01)
    lines = [ln for ln in served.stderr.splitlines() if ln.startswith("WIRING ")]
    assert len(lines) == 1
    wiring = json.loads(lines[0].removeprefix("WIRING "))
    assert wiring and all(isinstance(v, bool) for v in wiring.values())
    assert wiring == dict.fromkeys(wiring, True)
    assert wiring["imports_this_tree"] is True  # the child tests this tree, not an installed copy


def test_connector_log_calls_are_constant():
    """Every logging call under src/connector: one string literal, no `%`, no f-string, no extra."""
    # By method name, on any receiver: an aliased logger or `fatal` cannot slip past.
    levels = {"debug", "info", "warning", "warn", "error", "exception", "critical", "fatal", "log"}
    checked = 0
    for path in sorted(SRC_DIR.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            # `getattr(log, "error")(...)` names the method in a string: refused outright.
            is_getattr = (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "getattr"
                and len(node.args) >= 2
                and isinstance(node.args[1], ast.Constant)
                and node.args[1].value in levels
            )
            assert not is_getattr, f"getattr for a log method: {path.name}:{node.lineno}"
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
                continue
            if node.func.attr not in levels:
                continue
            checked += 1
            where = f"{path.name}:{node.lineno}"
            assert len(node.args) == 1, where
            arg = node.args[0]
            assert isinstance(arg, ast.Constant) and isinstance(arg.value, str), where
            assert "%" not in arg.value, where
            assert all(k.arg == "exc_info" for k in node.keywords), where
    assert checked > 0  # the walk found the calls it is meant to police


def test_serve_cli_system_exit_prints_one_fixed_line(env, capsys, monkeypatch, no_server):
    async def exits(*args, **kwargs):
        raise SystemExit("MRK-exit-text")

    monkeypatch.setattr("universal_connector.frontdoor.serve", exits)
    monkeypatch.setattr("universal_connector.cli.store_for", lambda machine: MemorySecretStore({}))
    code = main(["serve", "--port=18999", "--manifest", str(env.manifest), "--state", str(env.state)])
    captured = capsys.readouterr()
    assert code == 1
    assert captured.err == "the front door stopped on an exit request\n"
    assert "MRK" not in captured.out


def test_log_allow_list_drops_third_party_text():
    stream = io.StringIO()
    handler = frontdoor._AllowListHandler(stream)
    marker = "MRK-allow-list"
    try:
        raise ValueError(marker)
    except ValueError:
        exc_info = sys.exc_info()

    def record(name, msg, args=None, info=None):
        return logging.LogRecord(name, logging.ERROR, __file__, 1, msg, args, info)

    for item in (
        record("root", f"Failed to validate request: {marker}"),
        record("mcp.server", "got %s", (marker,), exc_info),
        record("uvicorn.error", OSError(marker)),
        record("universal_connector.frontdoor", "purge failed: %s", ("RuntimeError",)),
        record("universal_connector.frontdoor", "key check failed", None, exc_info),
        record("universal_connector.frontdoor", "broken %s %s", (marker,)),
        record("connectorx", f"not ours {marker}"),
    ):
        handler.handle(item)
    assert stream.getvalue().splitlines() == [
        "root ERROR",
        "mcp.server ERROR ValueError",
        "uvicorn.error ERROR OSError",
        "universal_connector.frontdoor ERROR purge failed: RuntimeError",
        "universal_connector.frontdoor ERROR key check failed ValueError",
        "universal_connector.frontdoor ERROR unwritable record",
        "connectorx ERROR",
    ]


class CountBodyMessages:
    """Wraps an app and counts the body messages uvicorn hands it, per HTTP request."""

    def __init__(self, app) -> None:
        self.app = app
        self.state = app.state
        self.counts: list[int] = []

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        index = len(self.counts)
        self.counts.append(0)

        async def counted():
            message = await receive()
            if message["type"] == "http.request":
                self.counts[index] += 1
            return message

        await self.app(scope, counted, send)


async def test_large_body_over_real_socket(env):
    blob = "".join(f"{i:07d}" for i in range(900 * 1024 // 7))  # every chunk differs
    body = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 9,
            "method": "tools/call",
            "params": {"name": "mail__search", "arguments": {"q": blob}},
        }
    ).encode()
    assert 900 * 1024 < len(body) < frontdoor.MAX_BODY_BYTES
    headers = {**MCP_HEADERS, **bearer(env.keys["alpha"])}

    async def chunks():
        for start in range(0, len(body), 65536):
            yield body[start : start + 65536]

    app = CountBodyMessages(build_app(env.holder, env.state))
    with run_app(app) as base:
        async with httpx.AsyncClient(timeout=15) as http:
            by_length = await http.post(f"{base}/mcp", content=body, headers=headers)
            request = http.build_request("POST", f"{base}/mcp", content=chunks(), headers=headers)
            assert "content-length" not in request.headers
            chunked = await http.send(request)
    for response in (by_length, chunked):
        assert response.status_code == 200
        assert response.json()["result"]["isError"] is False
    assert min(app.counts) > 1  # uvicorn handed each body over in several messages
    assert env.builder.fakes["mail"].calls == [("search", {"q": blob})] * 2


async def test_content_length_over_limit_reads_no_body(env):
    app = build_app(env.holder, env.state)
    reads: list[str] = []
    sent: list[dict] = []

    async def receive():
        reads.append("receive")
        raise AssertionError("the body was read")

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/mcp",
        "raw_path": b"/mcp",
        "query_string": b"",
        "root_path": "",
        "client": ("127.0.0.1", 50000),
        "server": ("127.0.0.1", 80),
        "headers": [
            (b"host", b"127.0.0.1"),
            (b"content-type", b"application/json"),
            (b"authorization", f"Bearer {env.keys['alpha']}".encode()),
            (b"content-length", str(frontdoor.MAX_BODY_BYTES + 1).encode()),
        ],
    }
    await app(scope, receive, send)
    assert reads == []
    assert sent[0]["type"] == "http.response.start"
    assert sent[0]["status"] == 413


async def test_two_agents_see_different_tools(env):
    with run_app(build_app(env.holder, env.state)) as base:
        alpha = await with_session(base, bearer(env.keys["alpha"]), list_names)
        beta = await with_session(base, bearer(env.keys["beta"]), list_names)
    assert "mail__search" in alpha
    assert "diary__lookup" not in alpha
    assert "mail__draft" not in alpha
    assert {"mail__search", "mail__draft", "diary__lookup"} <= set(beta)


# -- annotations -------------------------------------------------------------------------------


async def test_read_tools_marked_read_only(env):
    async def tools(session: ClientSession):
        return {t.name: t for t in (await session.list_tools()).tools}

    with run_app(build_app(env.holder, env.state)) as base:
        listed = await with_session(base, bearer(env.keys["alpha"]), tools)
    for name in ("connector_guide", "find_read_tools", "call_read_tool", "mail__search"):
        assert listed[name].annotations.readOnlyHint is True
        assert listed[name].annotations.destructiveHint is False


async def test_annotations_match_tiers(env):
    async def tools(session: ClientSession):
        return {t.name: t for t in (await session.list_tools()).tools}

    with run_app(build_app(env.holder, env.state)) as base:
        listed = await with_session(base, bearer(env.keys["beta"]), tools)
    expected = {
        "connector_guide": True,
        "find_read_tools": True,
        "call_read_tool": True,
        "find_write_tools": False,
        "call_write_tool": False,
        "mail__search": True,
        "diary__lookup": True,
        "mail__draft": False,
    }
    assert {n: listed[n].annotations.readOnlyHint for n in expected} == expected
    assert all(t.annotations.destructiveHint is not True for t in listed.values())


# -- startup, reload, purge --------------------------------------------------------------------


async def test_startup_refreshes_once(env):
    with run_app(build_app(env.holder, env.state)) as base:
        assert {n: f.list_calls for n, f in env.builder.fakes.items()} == {"mail": 1, "diary": 1}
        await with_session(base, bearer(env.keys["alpha"]), list_names)
        await with_session(base, bearer(env.keys["beta"]), list_names)
    assert {n: f.list_calls for n, f in env.builder.fakes.items()} == {"mail": 1, "diary": 1}


async def test_reload_and_refresh_refreshes_once(env):
    before = {n: f.list_calls for n, f in env.builder.fakes.items()}
    assert await env.holder.reload_and_refresh() == []
    after = {n: f.list_calls for n, f in env.builder.fakes.items()}
    assert after == {n: c + 1 for n, c in before.items()}
    # A failed reload refreshes nothing.
    (env.manifest / "connector.yaml").write_text("version: 1\nconnections: nope\n")
    assert await env.holder.reload_and_refresh() != []
    assert {n: f.list_calls for n, f in env.builder.fakes.items()} == after


async def test_no_timer_calls_refresh(env):
    sleep, ticks = fast_sleep()
    with run_app(build_app(env.holder, env.state, sleep=sleep, purge_interval_s=60)):
        tick_wait(ticks, 6)
    assert {n: f.list_calls for n, f in env.builder.fakes.items()} == {"mail": 1, "diary": 1}


async def test_idle_purge_loop_runs(env):
    sleep, ticks = fast_sleep()
    with run_app(build_app(env.holder, env.state, sleep=sleep)):
        tick_wait(ticks, 3)
    assert env.store.purges >= 1  # the vault store
    assert all(f.purges >= 1 for f in env.builder.fakes.values())  # every upstream


async def test_purge_loop_uses_current_router(tmp_path, env):
    builder = Builder(fresh=True)
    holder = Holder(env.manifest, env.state, env.store, builder)
    sleep, ticks = fast_sleep()
    with run_app(build_app(holder, env.state, sleep=sleep)):
        tick_wait(ticks, 2)
        old = builder.generations[0]
        assert all(f.purges >= 1 for f in old.values())
        assert holder.reload() == []
        new = builder.generations[1]
        tick_wait(ticks, ticks[0] + 2)  # let a purge that began before the swap finish
        frozen = {n: f.purges for n, f in old.items()}
        tick_wait(ticks, ticks[0] + 3)
        assert {n: f.purges for n, f in old.items()} == frozen
        assert all(f.purges >= 1 for f in new.values())


async def test_invalid_manifest_reload_keeps_last_good(env):
    (env.manifest / "connector.yaml").write_text("version: 1\nconnections: nope\n")

    async def call(session: ClientSession):
        return await session.call_tool("mail__search", {})

    with run_app(build_app(env.holder, env.state)) as base:
        problems = env.holder.reload()
        assert problems
        assert env.holder.last_error
        result = await with_session(base, bearer(env.keys["alpha"]), call)
    assert result.isError is False
    assert result.content[0].text == "ran search"
    (env.manifest / "connector.yaml").write_text(CONNECTOR_YAML)
    assert env.holder.reload() == []
    assert env.holder.last_error is None


async def test_sighup_reloads_and_refreshes(env):
    loop = asyncio.get_running_loop()
    before = env.builder.fakes["mail"].list_calls
    remove = frontdoor.install_sighup(loop, env.holder)
    try:
        os.kill(os.getpid(), signal.SIGHUP)
        deadline = time.monotonic() + 10
        while env.builder.fakes["mail"].list_calls == before:
            assert time.monotonic() < deadline, "SIGHUP did not reload"
            await asyncio.sleep(0.01)
    finally:
        remove()


# -- command line ------------------------------------------------------------------------------


@pytest.fixture
def no_server(monkeypatch):
    """Any path that reaches uvicorn's serve, or builds the vault store, fails the test."""

    async def boom(self, *args, **kwargs):
        raise AssertionError("uvicorn.Server.serve was reached")

    def no_store(*args, **kwargs):
        raise AssertionError("the vault store was built")

    monkeypatch.setattr("uvicorn.Server.serve", boom)
    monkeypatch.setattr("universal_connector.cli.store_for", no_store)


@pytest.mark.parametrize("host", ["0.0.0.0", "", "::", "localhost", "127.0.0.2"])
async def test_serve_function_refuses_non_loopback(env, no_server, host):
    with pytest.raises(ValueError, match="loopback only"):
        await frontdoor.serve(env.holder, env.state, host, 0)


@pytest.mark.parametrize("host", ["0.0.0.0", "localhost", "192.168.1.5", "::", ""])
def test_serve_refuses_non_loopback(env, capsys, no_server, host):
    code = main(
        ["serve", "--host", host, "--manifest", str(env.manifest), "--state", str(env.state)]
    )
    assert code == 2
    assert "loopback only in version 1" in capsys.readouterr().err


@pytest.mark.parametrize("port", [0, -1, 65536, 100000])
async def test_serve_function_refuses_bad_port(env, no_server, port):
    with pytest.raises(ValueError, match="port must be 1 to 65535"):
        await frontdoor.serve(env.holder, env.state, "127.0.0.1", port)


@pytest.mark.parametrize("port", ["0", "-1", "65536"])
def test_serve_cli_bad_port_exits_2(env, capsys, no_server, port):
    code = main(
        ["serve", f"--port={port}", "--manifest", str(env.manifest), "--state", str(env.state)]
    )
    assert code == 2
    assert capsys.readouterr().err == "port must be 1 to 65535\n"


async def test_logs_have_no_token(env, caplog):
    caplog.set_level(logging.DEBUG)
    key = env.keys["alpha"]
    bad = keys.KEY_PREFIX + "y" * 43

    async def call(session: ClientSession):
        await session.list_tools()
        return await session.call_tool("mail__search", {"q": "z"})

    with run_app(build_app(env.holder, env.state)) as base:
        await with_session(base, bearer(key), call)
        await raw_post(base, bearer(bad))
        await raw_post(base, {})
    text = "\n".join(f"{r.name} {r.getMessage()}" for r in caplog.records)
    assert key not in text
    assert bad not in text
    assert "Bearer" not in text
    assert find_secrets(text) == []


async def test_pause_and_resume(env, capsys):
    async def call(session: ClientSession):
        return await session.call_tool("mail__search", {})

    with run_app(build_app(env.holder, env.state)) as base:
        assert main(["pause", "--state", str(env.state)]) == 0
        assert audit.is_paused(env.state) is True
        paused = await with_session(base, bearer(env.keys["alpha"]), call)
        assert main(["resume", "--state", str(env.state)]) == 0
        assert audit.is_paused(env.state) is False
        resumed = await with_session(base, bearer(env.keys["alpha"]), call)
    assert paused.isError is True
    assert resumed.isError is False
    assert capsys.readouterr().out.split() == ["paused", "resumed"]


def test_state_folder_exists_after_holder(tmp_path):
    state = tmp_path / "fresh-state"
    manifest = tmp_path / "m"
    manifest.mkdir()
    (manifest / "connector.yaml").write_text(CONNECTOR_YAML)
    (manifest / "agents.yaml").write_text(AGENTS_YAML)
    Holder(manifest, state, SpyStore(), Builder())
    assert (state / "state.db").is_file()
    assert Path(state).stat().st_mode & 0o777 == 0o700
