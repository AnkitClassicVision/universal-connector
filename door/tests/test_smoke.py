"""`uconnector smoke oddboro`, offline against the in-process door. No socket, no network."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from helpers.door import copy_examples, fake_builder, lifespan_only, memory_store
from universal_connector import keys, router, smoke
from universal_connector.cli import main
from universal_connector.frontdoor import Holder, build_app

URL = "https://door.localhost/mcp"
EXPECTED = [
    "initialize", "no key gives 401", "GET gives 405 or a stream", "tools/list one page",
    "tool shape", "tools/call per read tool",
]  # fmt: skip


def door(tmp_path: Path, *, pinned: bool, host: str = "door.localhost"):
    manifest = copy_examples(tmp_path)
    agent = {"name": "odd", "scopes": ["work"], "reach": "full-read", "pinned_tools": pinned,
             "call_timeout_s": 40}  # fmt: skip
    (manifest / "agents.yaml").write_text(yaml.safe_dump({"version": 1, "agents": [agent]}))
    state = tmp_path / "state"
    holder = Holder(manifest, state, memory_store(), fake_builder)
    key = keys.mint(state, "odd")
    app = build_app(holder, state, door_hosts=[host])
    app.state.set_port(8765)
    return app, holder, key


@pytest.mark.parametrize("pinned", [False, True])
async def test_smoke_passes_on_a_good_door(tmp_path, pinned):
    # Pinned tools need the short host: 5 + 15 + 2 + 42 = 64 characters, just at the limit.
    host = "d.localhost" if pinned else "door.localhost"
    app, holder, key = door(tmp_path, pinned=pinned, host=host)
    async with lifespan_only(app) as transport:
        checks = await smoke.run_smoke(f"https://{host}/mcp", key, transport=transport)
    assert [c.name for c in checks] == EXPECTED
    assert [c.name for c in checks if not c.passed] == []
    shape = next(c for c in checks if c.name == "tool shape")
    assert ("warning: past 57" in shape.detail) is pinned
    text = smoke.render(checks)
    assert key not in text and "Bearer" not in text
    assert text.endswith("6 checks, 0 failed\n")
    calls = holder.upstreams["notes"].calls + holder.upstreams["google_mail_work"].calls
    assert (len(calls) > 0) is pinned  # pinned read tools were each called once


async def test_smoke_with_a_wrong_key_fails_and_stops(tmp_path):
    app, _, key = door(tmp_path, pinned=False)
    wrong = key[:-1] + ("A" if key[-1] != "A" else "B")
    async with lifespan_only(app) as transport:
        checks = await smoke.run_smoke(URL, wrong, transport=transport)
    assert [(c.name, c.passed) for c in checks] == [
        ("initialize", False), ("no key gives 401", True),
    ]
    assert checks[0].detail == "status 401"


async def test_smoke_catches_a_read_tool_oddboro_would_not_read(tmp_path, monkeypatch):
    app, _, key = door(tmp_path, pinned=False)
    real = router.Router.visible

    def with_a_bad_tool(self, agent):
        tools = real(self, agent)
        tools.append(router.VisibleTool("send_note", "fake", {"type": "object"}, True))
        return tools

    monkeypatch.setattr(router.Router, "visible", with_a_bad_tool)
    async with lifespan_only(app) as transport:
        checks = await smoke.run_smoke(URL, key, transport=transport)
    shape = next(c for c in checks if c.name == "tool shape")
    assert not shape.passed
    assert "a read-only tool fails the read-only rule" in shape.detail
    assert smoke.exit_code(checks) == 1


async def test_smoke_catches_a_name_over_64(tmp_path):
    # Through this address the pinned calendar tool is 5 + 28 + 2 + 42 = 77 characters.
    app, _, key = door(tmp_path, pinned=True, host="door.tailnet-name.ts.net")
    async with lifespan_only(app) as transport:
        checks = await smoke.run_smoke("https://door.tailnet-name.ts.net/mcp", key,
                                       transport=transport)  # fmt: skip
    assert checks[0].passed  # the door itself answers
    shape = next(c for c in checks if c.name == "tool shape")
    assert not shape.passed
    assert shape.detail.startswith("longest name 77 of 64 (warning: past 57)")
    assert "a name is over 64 characters" in shape.detail


async def test_smoke_reports_an_unlisted_host(tmp_path):
    app, _, key = door(tmp_path, pinned=False)  # door_hosts holds door.localhost only
    async with lifespan_only(app) as transport:
        checks = await smoke.run_smoke("https://other.localhost/mcp", key, transport=transport)
    assert (checks[0].name, checks[0].passed, checks[0].detail) == (
        "initialize", False, "status 421",
    )


def test_key_file_rules(tmp_path):
    key = "pc_" + "a" * 43
    good = tmp_path / "good"
    good.write_text(key + "\n")
    assert smoke.read_key_file(good) == key
    good.write_text(key)
    assert smoke.read_key_file(good) == key
    for bad in (key + "\n\n", " " + key, key + "\r\n", key[:-1], "pc_" + "a" * 42 + "!", ""):
        path = tmp_path / "bad"
        path.write_text(bad)
        with pytest.raises(ValueError, match="^the key file must hold one key"):
            smoke.read_key_file(path)
    with pytest.raises(ValueError):
        smoke.read_key_file(tmp_path / "missing")


def test_cli_smoke_refuses_bad_input_without_a_request(tmp_path, capsys, monkeypatch):
    def no_run(*a, **k):
        raise AssertionError("no request may be made")

    monkeypatch.setattr(smoke, "run_smoke", no_run)
    key_file = tmp_path / "k"
    key_file.write_text("pc_" + "b" * 43 + "\n")
    assert main(["smoke", "oddboro", "--url", "http://door.localhost/mcp",
                 "--key-file", str(key_file)]) == 2  # fmt: skip
    assert capsys.readouterr().err == "Oddboro needs an https address.\n"
    key_file.write_text("not a key\n")
    assert main(["smoke", "oddboro", "--url", URL, "--key-file", str(key_file)]) == 2
    err = capsys.readouterr().err
    assert err.startswith("the key file must hold one key") and "not a key" not in err


def test_cli_smoke_prints_checks_and_never_the_key(tmp_path, capsys, monkeypatch):
    key = "pc_" + "c" * 43
    key_file = tmp_path / "k"
    key_file.write_text(key + "\n")
    seen = {}

    async def fake_run(url, presented, **kwargs):
        seen.update(url=url, key=presented)
        return [smoke.Check("initialize", True, "protocol 2025-11-25, 0.0 s")]

    monkeypatch.setattr(smoke, "run_smoke", fake_run)
    assert main(["smoke", "oddboro", "--url", URL, "--key-file", str(key_file)]) == 0
    out = capsys.readouterr()
    assert seen == {"url": URL, "key": key}
    assert out.out == "pass initialize: protocol 2025-11-25, 0.0 s\n1 checks, 0 failed\n"
    assert key not in out.out + out.err
