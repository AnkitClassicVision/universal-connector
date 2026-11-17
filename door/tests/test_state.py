from __future__ import annotations

import os
import sqlite3
import threading
from contextlib import closing

import pytest

from universal_connector.state import LOCK_NAME, LOCK_REFUSED, StateDirError, open_state


def test_concurrent_first_open_all_succeed(tmp_path):
    state = tmp_path / "new" / "state"
    errors: list[BaseException] = []
    start = threading.Barrier(30)

    def first_open() -> None:
        try:
            start.wait(timeout=10)
            with closing(open_state(state)):
                pass
        except BaseException as exc:  # noqa: BLE001 - collected and asserted below
            errors.append(exc)

    threads = [threading.Thread(target=first_open) for _ in range(30)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert errors == []
    assert sorted(p.name for p in state.iterdir() if p.name.startswith("state.db")) == ["state.db"]
    assert (state.stat().st_mode & 0o777) == 0o700
    assert ((state / "state.db").stat().st_mode & 0o777) == 0o600


def test_foreign_folder_still_refused(tmp_path):
    state = tmp_path / "state"
    state.mkdir(mode=0o755)
    (state / "notes.txt").write_text("not ours")
    with pytest.raises(StateDirError):
        open_state(state)
    assert sorted(p.name for p in state.iterdir()) == ["notes.txt"]  # nothing was added
    assert (state.stat().st_mode & 0o777) == 0o755  # nothing was changed
    # A foreign file next to a database's own journal is still foreign.
    (state / "state.db-journal").write_text("")
    with pytest.raises(StateDirError):
        open_state(state)


@pytest.mark.parametrize("existing_target", [False, True])
def test_symlink_state_db_refused(tmp_path, existing_target):
    outside = tmp_path / "outside"
    outside.mkdir()
    target = outside / "target.db"
    if existing_target:
        target.write_text("outside content")
        target.chmod(0o644)
    state = tmp_path / "state"
    state.mkdir(mode=0o755)
    state.chmod(0o755)
    (state / "state.db").symlink_to(target)
    with pytest.raises(StateDirError):
        open_state(state)
    assert (state.stat().st_mode & 0o777) == 0o755  # the folder was not changed
    assert [p.name for p in state.iterdir()] == ["state.db"]
    assert (state / "state.db").is_symlink()
    if existing_target:
        assert target.read_text() == "outside content"
        assert (target.stat().st_mode & 0o777) == 0o644
    else:
        assert not target.exists()  # nothing was created outside the folder
    assert [p.name for p in outside.iterdir()] == (["target.db"] if existing_target else [])


def test_link_appearing_after_the_check_is_not_followed(tmp_path, monkeypatch):
    """The check saw no state.db, then a link appeared. The open must not follow it."""
    outside = tmp_path / "outside"
    outside.mkdir()
    target = outside / "target.db"
    state = tmp_path / "state"
    state.mkdir()
    (state / "state.db").symlink_to(target)

    def saw_nothing(path, *args, **kwargs):
        raise FileNotFoundError(path)

    monkeypatch.setattr("universal_connector.state.os.lstat", saw_nothing)
    with pytest.raises(StateDirError):
        open_state(state)
    assert not target.exists()
    assert list(outside.iterdir()) == []


def test_state_db_directory_refused_untouched(tmp_path):
    state = tmp_path / "state"
    state.mkdir()
    state.chmod(0o755)
    (state / "state.db").mkdir()
    with pytest.raises(StateDirError):
        open_state(state)
    assert (state.stat().st_mode & 0o777) == 0o755
    assert [p.name for p in state.iterdir()] == ["state.db"]


@pytest.mark.parametrize("name", ["state.db-evil", "state.dbx", "state.db.bak", "state.db-journal2"])
def test_only_db_side_files_exempt_refused(tmp_path, name):
    state = tmp_path / "state"
    state.mkdir()
    state.chmod(0o755)
    (state / name).write_text("")
    with pytest.raises(StateDirError):
        open_state(state)
    assert [p.name for p in state.iterdir()] == [name]
    assert (state.stat().st_mode & 0o777) == 0o755


@pytest.mark.parametrize("name", ["state.db-journal", "state.db-wal", "state.db-shm"])
def test_only_db_side_files_exempt(tmp_path, name):
    state = tmp_path / "state"
    state.mkdir()
    (state / name).write_text("")
    with closing(open_state(state)):
        pass
    assert (state / "state.db").is_file()


@pytest.mark.parametrize("name", ["state.db-journal", "state.db-wal", "state.db-shm"])
def test_side_file_link_refused(tmp_path, name):
    state = tmp_path / "state"
    state.mkdir()
    state.chmod(0o755)
    (state / name).symlink_to(tmp_path / "nowhere")  # dangling
    with pytest.raises(StateDirError):
        open_state(state)
    assert [p.name for p in state.iterdir()] == [name]  # no state.db was added
    assert (state.stat().st_mode & 0o777) == 0o755  # the folder was not changed


def test_hard_linked_state_db_refused(tmp_path):
    outside = tmp_path / "outside.db"
    outside.write_text("outside content")
    outside.chmod(0o644)
    state = tmp_path / "state"
    state.mkdir()
    state.chmod(0o755)
    os.link(outside, state / "state.db")
    with pytest.raises(StateDirError):
        open_state(state)
    assert outside.read_text() == "outside content"
    assert (outside.stat().st_mode & 0o777) == 0o644
    assert (state.stat().st_mode & 0o777) == 0o755


def test_state_folder_link_refused(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    real.chmod(0o755)
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    with pytest.raises(StateDirError):
        open_state(link)
    assert list(real.iterdir()) == []
    assert (real.stat().st_mode & 0o777) == 0o755
    dangling = tmp_path / "dangling"
    dangling.symlink_to(tmp_path / "missing", target_is_directory=True)
    with pytest.raises(StateDirError):
        open_state(dangling)
    assert not (tmp_path / "missing").exists()


def test_swap_after_connect_detected(tmp_path, monkeypatch):
    state = tmp_path / "state"
    real_connect = sqlite3.connect

    def connect_then_swap(path, *args, **kwargs):
        db = real_connect(path, *args, **kwargs)
        replacement = state / "other"
        replacement.write_text("")
        os.replace(replacement, path)  # a different file now sits at the path
        return db

    monkeypatch.setattr("universal_connector.state.sqlite3.connect", connect_then_swap)
    with pytest.raises(StateDirError):
        open_state(state)


def test_hard_link_after_connect_detected(tmp_path, monkeypatch):
    state = tmp_path / "state"
    outside = tmp_path / "outside.db"
    real_connect = sqlite3.connect

    def connect_then_link(path, *args, **kwargs):
        db = real_connect(path, *args, **kwargs)
        os.link(path, outside)  # same file, now two links
        return db

    monkeypatch.setattr("universal_connector.state.sqlite3.connect", connect_then_link)
    with pytest.raises(StateDirError):
        open_state(state)


def test_mode_set_on_descriptor_not_path(tmp_path, monkeypatch):
    outside = tmp_path / "outside.db"
    outside.write_text("outside content")
    outside.chmod(0o644)
    state = tmp_path / "state"
    real_open = os.open

    def open_then_link(path, *args, **kwargs):
        fd = real_open(path, *args, **kwargs)
        if str(path).endswith("state.db"):
            os.unlink(path)
            os.symlink(outside, path)  # a link replaces the file right after the open
        return fd

    monkeypatch.setattr("universal_connector.state.os.open", open_then_link)
    with pytest.raises(StateDirError):
        open_state(state)
    assert (outside.stat().st_mode & 0o777) == 0o644
    assert outside.read_text() == "outside content"


def test_db_own_files_do_not_make_a_folder_foreign(tmp_path):
    state = tmp_path / "state"
    state.mkdir()
    (state / "state.db-journal").write_text("")
    with closing(open_state(state)):
        pass
    assert (state / "state.db").is_file()


# -- QA round 2 on Task 13: the key-change lock lives in the state folder ------------------------


def test_lock_file_before_state_db_is_accepted(tmp_path):
    """The folder an older build left behind: only connector.lock, no state.db. It must heal."""
    state = tmp_path / "state"
    state.mkdir(mode=0o700)
    (state / LOCK_NAME).write_text("")
    (state / LOCK_NAME).chmod(0o600)
    with closing(open_state(state)):
        pass
    assert sorted(p.name for p in state.iterdir()) == [LOCK_NAME, "state.db"]
    assert ((state / "state.db").stat().st_mode & 0o777) == 0o600
    # A foreign file next to the lock is still foreign.
    other = tmp_path / "other"
    other.mkdir()
    (other / LOCK_NAME).write_text("")
    (other / "notes.txt").write_text("not ours")
    with pytest.raises(StateDirError):
        open_state(other)
    assert sorted(p.name for p in other.iterdir()) == [LOCK_NAME, "notes.txt"]


@pytest.mark.parametrize("with_db", [False, True])
@pytest.mark.parametrize("kind", ["dangling link", "link to a file", "folder", "hard link"])
def test_lock_file_must_be_one_regular_file(tmp_path, kind, with_db):
    outside = tmp_path / "outside.txt"
    outside.write_text("outside content")
    outside.chmod(0o644)
    state = tmp_path / "state"
    if with_db:
        with closing(open_state(state)):
            pass
    else:
        state.mkdir()
    state.chmod(0o755)
    lock = state / LOCK_NAME
    if kind == "dangling link":
        lock.symlink_to(tmp_path / "nowhere")
    elif kind == "link to a file":
        lock.symlink_to(outside)
    elif kind == "folder":
        lock.mkdir()
    else:
        os.link(outside, lock)
    before = sorted(p.name for p in state.iterdir())
    with pytest.raises(StateDirError) as refused:
        open_state(state)
    assert str(refused.value) == LOCK_REFUSED  # fixed text, never a path
    assert sorted(p.name for p in state.iterdir()) == before  # nothing was added
    assert (state.stat().st_mode & 0o777) == 0o755  # nothing was changed
    assert outside.read_text() == "outside content"
    assert (outside.stat().st_mode & 0o777) == 0o644
    assert not (tmp_path / "nowhere").exists()
