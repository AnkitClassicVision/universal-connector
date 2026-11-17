"""Windows and POSIX differences, simulated on Linux: locks, links, modes, signals, folders."""

from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
import sys
import types
from pathlib import Path

import pytest

from universal_connector import adapters, frontdoor, portable
from universal_connector.cli import main
from universal_connector.state import LOCK_REFUSED, StateDirError, open_state

CONNECTOR_YAML = (
    "version: 1\nconnections:\n"
    "  - name: notes\n    kind: mcp-remote\n    upstream: https://notes.example.invalid/mcp\n"
    "    auth: {type: none}\n    scopes: [work]\n    reach: starter\n"
    "    tools:\n      - {name: search_notes, tier: green, pinned: true}\n"
)


def manifest_dir(tmp_path: Path) -> Path:
    folder = tmp_path / "manifest"
    folder.mkdir()
    (folder / "connector.yaml").write_text(CONNECTOR_YAML)
    (folder / "agents.yaml").write_text("version: 1\nagents: []\n")
    return folder


class FakeMsvcrt(types.ModuleType):
    LK_UNLCK, LK_LOCK = 0, 1

    def __init__(self, busy: bool = False) -> None:
        super().__init__("msvcrt")
        self.busy = busy
        self.calls: list[int] = []

    def locking(self, fd: int, mode: int, nbytes: int) -> None:
        self.calls.append(mode)
        if self.busy and mode == self.LK_LOCK:
            raise OSError("locked")


@pytest.fixture
def windows(monkeypatch):
    """Simulate Windows: the platform name, `msvcrt`, and no `fcntl`, `O_NOFOLLOW` or `fchmod`."""
    fake = FakeMsvcrt()
    monkeypatch.setattr(portable, "PLATFORM", "windows")
    monkeypatch.setitem(sys.modules, "msvcrt", fake)
    monkeypatch.setitem(sys.modules, "fcntl", None)  # any import of fcntl now fails
    monkeypatch.delattr(os, "O_NOFOLLOW", raising=False)
    monkeypatch.delattr(os, "fchmod", raising=False)
    return fake


# -- links without O_NOFOLLOW ------------------------------------------------------------------


def test_open_no_link_without_nofollow(tmp_path, monkeypatch):
    monkeypatch.delattr(os, "O_NOFOLLOW")
    target = tmp_path / "real"
    target.write_text("x")
    fd = portable.open_no_link(target, os.O_RDONLY)
    os.close(fd)
    link = tmp_path / "link"
    link.symlink_to(target)
    with pytest.raises(portable.LinkRefused):
        portable.open_no_link(link, os.O_RDONLY)
    dangling = tmp_path / "dangling"
    dangling.symlink_to(tmp_path / "nowhere")
    with pytest.raises(portable.LinkRefused):
        portable.open_no_link(dangling, os.O_RDWR | os.O_CREAT)
    assert not (tmp_path / "nowhere").exists()  # refused before the open could create it


def test_open_no_link_catches_a_swap_after_the_open(tmp_path, monkeypatch):
    monkeypatch.delattr(os, "O_NOFOLLOW")
    path, other = tmp_path / "state.db", tmp_path / "other"
    path.write_text("x")
    other.write_text("y")
    real_open = os.open
    closed: list[int] = []
    real_close = os.close

    def open_then_swap(p, flags, mode=0o777):
        fd = real_open(p, flags, mode)
        os.unlink(path)
        path.symlink_to(other)
        return fd

    monkeypatch.setattr(portable.os, "open", open_then_swap)
    monkeypatch.setattr(portable.os, "close", lambda fd: (closed.append(fd), real_close(fd)))
    with pytest.raises(portable.LinkRefused):
        portable.open_no_link(path, os.O_RDWR)
    assert len(closed) == 1  # the descriptor was closed, not leaked


def test_state_and_lock_refuse_links_without_nofollow(tmp_path, monkeypatch):
    monkeypatch.delattr(os, "O_NOFOLLOW")
    state = tmp_path / "state"
    open_state(state).close()
    real = tmp_path / "elsewhere"
    real.write_text("")
    (state / "connector.lock").symlink_to(real)
    with pytest.raises(StateDirError, match=LOCK_REFUSED), adapters.state_lock(state):
        pass
    os.unlink(state / "connector.lock")
    (state / "state.db").rename(tmp_path / "moved.db")
    (state / "state.db").symlink_to(tmp_path / "moved.db")
    with pytest.raises(StateDirError, match="state.db is not a regular file"):
        open_state(state)


# -- the Windows lock ------------------------------------------------------------------------


def test_windows_lock_uses_msvcrt_and_unlocks(tmp_path, windows):
    with adapters.state_lock(tmp_path / "state"):
        assert windows.calls == [windows.LK_LOCK]
    assert windows.calls == [windows.LK_LOCK, windows.LK_UNLCK]


def test_windows_lock_unlocks_after_an_error(tmp_path, windows):
    with pytest.raises(RuntimeError), adapters.state_lock(tmp_path / "state"):
        raise RuntimeError("inside")
    assert windows.calls[-1] == windows.LK_UNLCK


def test_windows_busy_lock_gives_fixed_text(tmp_path, windows, capsys):
    windows.busy = True
    with pytest.raises(StateDirError, match=f"^{adapters.LOCK_BUSY}$"), adapters.state_lock(
        tmp_path / "state"
    ):
        pass
    assert windows.calls.count(windows.LK_LOCK) == portable.LOCK_TRIES
    manifest = manifest_dir(tmp_path)
    code = main(["connect", "alpha", "--manifest", str(manifest), "--state", str(tmp_path / "state"),
                 "--reach", "starter", "--scopes", "work"])  # fmt: skip
    assert code == 1
    assert capsys.readouterr().err == f"{adapters.LOCK_BUSY}; no key is active for alpha\n"


def test_posix_lock_still_uses_flock(tmp_path, monkeypatch):
    import fcntl

    seen: list[int] = []
    real = fcntl.flock
    monkeypatch.setattr(fcntl, "flock", lambda fd, op: (seen.append(op), real(fd, op)))
    with adapters.state_lock(tmp_path / "state"):
        pass
    assert seen == [fcntl.LOCK_EX]


# -- modes ---------------------------------------------------------------------------------------


def test_modes_are_skipped_on_windows(tmp_path, monkeypatch):
    def refuse(*args):
        raise AssertionError("no POSIX mode on Windows")

    monkeypatch.setattr(os, "fchmod", refuse)
    monkeypatch.setattr(os, "chmod", refuse)
    monkeypatch.setattr(portable, "PLATFORM", "windows")
    fd = os.open(tmp_path / "f", os.O_CREAT | os.O_RDWR, 0o600)
    try:
        portable.owner_only_file(fd)
    finally:
        os.close(fd)
    portable.owner_only_folder(tmp_path)


def test_posix_modes_still_apply(tmp_path):
    state = tmp_path / "state"
    open_state(state).close()
    assert (state.stat().st_mode & 0o777) == 0o700
    assert ((state / "state.db").stat().st_mode & 0o777) == 0o600


def test_key_file_is_binary_and_exclusive_on_every_system(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "O_BINARY", 0x8000, raising=False)  # Windows has it; check it is used
    seen: list[int] = []
    real = os.open
    monkeypatch.setattr(adapters.os, "open",
                        lambda p, flags, mode=0o777: (seen.append(flags), real(p, flags & ~0x8000, mode))[1])  # fmt: skip
    fd = adapters.create_key_file(tmp_path / "k")
    os.close(fd)
    assert seen[0] & 0x8000 and seen[0] & os.O_EXCL and seen[0] & os.O_CREAT


# -- signals -------------------------------------------------------------------------------------


class Loop:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.added: list[object] = []

    def add_signal_handler(self, sig, callback):
        if self.fail:
            raise NotImplementedError
        self.added.append(sig)

    def remove_signal_handler(self, sig):
        self.added.remove(sig)

    def create_task(self, coro):  # pragma: no cover - not reached
        raise AssertionError


def test_no_sighup_means_no_handler(monkeypatch):
    monkeypatch.delattr(signal, "SIGHUP")
    loop = Loop()
    remove = frontdoor.install_sighup(loop, holder=None)  # type: ignore[arg-type]
    assert loop.added == []
    remove()


def test_a_loop_without_signal_support_is_fine():
    remove = frontdoor.install_sighup(Loop(fail=True), holder=None)  # type: ignore[arg-type]
    remove()


def test_sighup_is_kept_on_posix():
    loop = Loop()
    remove = frontdoor.install_sighup(loop, holder=None)  # type: ignore[arg-type]
    assert loop.added == [signal.SIGHUP]
    remove()
    assert loop.added == []


# -- the per-user state folder -----------------------------------------------------------------


def test_default_state_dir_per_system(tmp_path, monkeypatch):
    monkeypatch.setattr(portable, "PLATFORM", "windows")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "AppData" / "Local"))
    assert portable.default_state_dir() == tmp_path / "AppData" / "Local" / "universal-connector" / "state"
    for bad in ("", "relative\\path"):
        monkeypatch.setenv("LOCALAPPDATA", bad)
        with pytest.raises(ValueError, match="^the per-user app-data folder"):
            portable.default_state_dir()
    monkeypatch.delenv("LOCALAPPDATA")
    with pytest.raises(ValueError):
        portable.default_state_dir()
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setattr(portable, "PLATFORM", "macos")
    assert portable.default_state_dir() == (
        tmp_path / "home" / "Library" / "Application Support" / "universal-connector" / "state"
    )
    monkeypatch.setattr(portable, "PLATFORM", "linux")
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "xdg"))
    assert portable.default_state_dir() == tmp_path / "xdg" / "universal-connector" / "state"
    monkeypatch.setenv("XDG_STATE_HOME", "relative")  # ignored, as the spec says
    assert portable.default_state_dir() == (
        tmp_path / "home" / ".local" / "state" / "universal-connector" / "state"
    )


def test_cli_uses_the_app_data_folder_on_windows(tmp_path, monkeypatch, windows, capsys):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    assert main(["pause"]) == 0
    assert (tmp_path / "Local" / "universal-connector" / "state" / "state.db").is_file()
    monkeypatch.delenv("LOCALAPPDATA")
    assert main(["resume"]) == 2
    assert capsys.readouterr().err.endswith(f"{portable.NO_APP_DATA}\n")


# -- the whole command line with no fcntl, O_NOFOLLOW, fchmod or SIGHUP ------------------------

CHILD = r"""
import json, os, signal, sys, types
sys.modules["fcntl"] = None
for name in ("O_NOFOLLOW", "fchmod"):
    if hasattr(os, name):
        delattr(os, name)
if hasattr(signal, "SIGHUP"):
    del signal.SIGHUP
# The CLI must import with none of the POSIX-only names. `msvcrt` goes in only after the import:
# Python's own `subprocess` reads its presence as "this is Windows".
from universal_connector import cli, portable
from universal_connector.cli import main
cli._machine_file_exists = lambda path: True  # the Windows example paths cannot exist here
calls = []
fake = types.ModuleType("msvcrt")
fake.LK_UNLCK, fake.LK_LOCK = 0, 1
fake.locking = lambda fd, mode, n: calls.append(mode)
sys.modules["msvcrt"] = fake
portable.PLATFORM = "windows"
m, s, tmp = sys.argv[1], sys.argv[2], sys.argv[3]
runs = [
    ["connect", "alpha", "--manifest", m, "--state", s, "--reach", "starter", "--scopes", "work",
     "--key-file", tmp + "/alpha.cred"],
    ["list", "--manifest", m, "--state", s],
    ["set-tools", "alpha", "--fixed-only", "--manifest", m, "--state", s],
    ["rotate", "alpha", "--manifest", m, "--state", s, "--key-file", tmp + "/alpha2.cred"],
    ["reload", "--state", s, "--wait", "0"],
    ["pause"],
    ["resume"],
    ["revoke", "alpha", "--manifest", m, "--state", s],
    ["install-service", "--print", "--machine-file", "C:\\door\\machine.yaml",  # an example path
     "--manifest", "C:\\door\\manifest", "--state", "C:\\door\\state",
     "--install-dir", "C:\\Users\\someone\\.local\\bin"],
]
codes = [main(r) for r in runs]
print(json.dumps({"codes": codes, "locks": calls}))
"""


def test_cli_imports_and_runs_with_windows_shapes(tmp_path):
    manifest = manifest_dir(tmp_path)
    env = {**os.environ, "LOCALAPPDATA": str(tmp_path / "Local"), "USERNAME": "someone",
           "USERDOMAIN": "DESK"}  # fmt: skip
    env.pop("UCONNECTOR_MACHINE_FILE", None)
    done = subprocess.run(
        [sys.executable, "-c", CHILD, str(manifest), str(tmp_path / "state"), str(tmp_path)],
        capture_output=True, text=True, env=env, cwd=tmp_path, timeout=120, check=False,
    )  # fmt: skip
    assert done.returncode == 0, done.stderr[-2000:]
    report = json.loads(done.stdout.strip().splitlines()[-1])
    assert report["codes"] == [0, 0, 0, 0, 3, 0, 0, 0, 0]
    assert report["locks"].count(1) == 4 and report["locks"].count(0) == 4  # 4 locked commands
    assert (tmp_path / "alpha.cred").read_bytes().endswith(b"\n")
    assert not (tmp_path / "alpha.cred").read_bytes().endswith(b"\r\n")
    assert (tmp_path / "Local" / "universal-connector" / "state" / "state.db").is_file()
    assert "<Command>C:\\Users\\someone\\.local\\bin\\uconnector.exe</Command>" in done.stdout


# -- the reload request ------------------------------------------------------------------------


def test_reload_counter_and_answer(tmp_path):
    from universal_connector import audit

    state = tmp_path / "state"
    open_state(state).close()
    assert audit.reload_requested(state) == 0 and audit.reload_answer(state) == (0, "")
    assert audit.request_reload(state) == 1
    assert audit.request_reload(state) == 2
    audit.mark_reloaded(state, 2, ok=False)
    assert audit.reload_answer(state) == (2, "failed")


def test_reload_without_a_state_folder_creates_nothing(tmp_path, capsys):
    assert main(["reload", "--state", str(tmp_path / "none"), "--wait", "0"]) == 2
    assert not (tmp_path / "none").exists()
    assert capsys.readouterr().err == "no door state in that folder; nothing to reload\n"
    assert main(["reload", "--state", str(tmp_path), "--wait", "500"]) == 2


def test_reload_with_no_running_door_says_so(tmp_path, capsys):
    state = tmp_path / "state"
    open_state(state).close()
    assert main(["reload", "--state", str(state), "--wait", "0"]) == 3
    assert capsys.readouterr().err == (
        "no door answered in time; a door still starting applies the request when it is up, "
        "and a door started later reads the files when it starts\n"
    )


def test_the_reload_baseline_is_read_before_the_files(tmp_path, monkeypatch):
    from helpers.door import fake_builder, memory_store
    from universal_connector import audit

    order: list[str] = []
    real_count, real_load = audit.reload_requested, frontdoor.load_manifest
    monkeypatch.setattr(audit, "reload_requested", lambda d: (order.append("count"), real_count(d))[1])
    monkeypatch.setattr(frontdoor, "load_manifest", lambda d: (order.append("load"), real_load(d))[1])
    holder = frontdoor.Holder(manifest_dir(tmp_path), tmp_path / "state", memory_store(), fake_builder)
    assert order == ["count", "load"]
    assert holder.reload_baseline == 0


async def test_a_reload_asked_during_startup_is_applied(tmp_path):
    from helpers.door import FakeUpstream, lifespan_only, memory_store
    from universal_connector import audit

    manifest, state = manifest_dir(tmp_path), tmp_path / "state"
    asked: list[bool] = []

    class AskWhileStarting(FakeUpstream):
        async def list_tools(self):
            if not asked:  # the door has read the files and is still in its startup refresh
                asked.append(True)
                (manifest / "agents.yaml").write_text(
                    "version: 1\nagents:\n  - {name: late, scopes: [work], reach: starter}\n"
                )
                await asyncio.to_thread(audit.request_reload, state)
            return await super().list_tools()

    def builder(m, store, machine):
        return {c.name: AskWhileStarting([t.name for t in c.tools]) for c in m.connections}

    holder = frontdoor.Holder(manifest, state, memory_store(), builder)
    app = frontdoor.build_app(holder, state, reload_poll_s=0.05)
    async with lifespan_only(app):
        for _ in range(200):
            if audit.reload_answer(state)[0] >= 1:
                break
            await asyncio.sleep(0.02)
    assert asked == [True]
    assert audit.reload_answer(state) == (1, "ok")
    assert holder.manifest.agent("late") is not None


async def test_reload_reaches_a_running_door_and_reports(tmp_path, capsys):
    from helpers.door import fake_builder, lifespan_only, memory_store

    manifest = manifest_dir(tmp_path)
    state = tmp_path / "state"
    holder = frontdoor.Holder(manifest, state, memory_store(), fake_builder)
    app = frontdoor.build_app(holder, state, reload_poll_s=0.05)
    async with lifespan_only(app):
        await asyncio.sleep(0.1)  # the loop takes its first number
        (manifest / "agents.yaml").write_text(
            "version: 1\nagents:\n  - {name: beta, scopes: [work], reach: starter}\n"
        )
        code = await asyncio.to_thread(main, ["reload", "--state", str(state), "--wait", "10"])
        assert code == 0
        assert holder.manifest.agent("beta") is not None
        (manifest / "agents.yaml").write_text("version: 1\nagents: nope\n")
        code = await asyncio.to_thread(main, ["reload", "--state", str(state), "--wait", "10"])
        assert code == 1
        assert holder.manifest.agent("beta") is not None  # the last good manifest keeps serving
    out = capsys.readouterr()
    assert out.out == "reloaded\n"
    assert out.err == "the new manifest did not load; the door keeps the last good one\n"


async def test_reload_check_survives_a_state_fault(tmp_path, monkeypatch, caplog):
    from universal_connector import audit

    def broken(directory):
        raise OSError(f"cannot open {directory}")

    monkeypatch.setattr(audit, "reload_requested", broken)
    assert await frontdoor.reload_check(holder=None, state_dir=tmp_path, seen=7) == 7  # type: ignore[arg-type]
    assert [r.getMessage() for r in caplog.records] == ["reload check failed: state unavailable"]
    assert json.dumps([r.getMessage() for r in caplog.records]).count(str(tmp_path)) == 0
