"""Operating-system differences in one place: file locks, open flags, modes, signals and folders.

Linux and macOS use `fcntl.flock`, `O_NOFOLLOW`, `fchmod` and SIGHUP. Windows has none of them:
it locks with `msvcrt.locking`, checks for links with `lstat` before and after each open, relies
on the per-user app-data folder for owner-only access, and reloads through `uconnector reload`.

`PLATFORM` is read at call time, so a test can set it to simulate another system.
"""

from __future__ import annotations

import contextlib
import errno
import os
import signal
import stat
import sys
from collections.abc import Iterator
from pathlib import Path

APP_NAME = "universal-connector"
PLATFORM = "windows" if os.name == "nt" else ("macos" if sys.platform == "darwin" else "linux")
# Windows only: each `msvcrt.LK_LOCK` try waits about 10 seconds before it gives up.
LOCK_TRIES = 6
NO_APP_DATA = "the per-user app-data folder (LOCALAPPDATA) is not set; pass --state"
NO_HOME = "the home folder is not known; pass --state"


class LinkRefused(OSError):
    """The path is, or became, a link. Nothing was opened."""

    def __init__(self) -> None:
        super().__init__(getattr(errno, "ELOOP", 0), "a link is refused")


class LockBusy(OSError):
    """The lock stayed taken for the whole wait. Windows only."""


def is_windows() -> bool:
    return PLATFORM == "windows"


def nofollow_flag() -> int:
    """`O_NOFOLLOW` where the system has it, else 0. Without it, `open_no_link` checks by `lstat`."""
    return getattr(os, "O_NOFOLLOW", 0)


def binary_flag() -> int:
    """`O_BINARY` on Windows, so a written newline stays one byte. 0 elsewhere."""
    return getattr(os, "O_BINARY", 0)


def _is_link(path: Path | str) -> bool:
    try:
        return stat.S_ISLNK(os.lstat(path).st_mode)
    except FileNotFoundError:
        return False


def open_no_link(path: Path | str, flags: int, mode: int = 0o600) -> int:
    """Open `path`, never through a link. Return the descriptor.

    With `O_NOFOLLOW` the open itself refuses a link. Without it, a link is refused before the
    open, and after it the path must still name the file that was opened.
    """
    nofollow = nofollow_flag()
    if not nofollow and _is_link(path):
        raise LinkRefused()
    fd = os.open(path, flags | nofollow | binary_flag(), mode)
    if nofollow:
        return fd
    try:
        opened = os.fstat(fd)
        now = os.lstat(path)
    except OSError:
        os.close(fd)
        raise LinkRefused() from None
    if stat.S_ISLNK(now.st_mode) or (opened.st_dev, opened.st_ino) != (now.st_dev, now.st_ino):
        os.close(fd)
        raise LinkRefused()
    return fd


def owner_only_file(fd: int) -> None:
    """Mode 0600 on an open file. Windows has no such mode: the per-user folder guards it."""
    if is_windows() or not hasattr(os, "fchmod"):
        return
    os.fchmod(fd, 0o600)


def owner_only_folder(path: Path | str) -> None:
    """Mode 0700 on a folder. Windows has no such mode: the per-user folder guards it."""
    if is_windows():
        return
    os.chmod(path, 0o700)


@contextlib.contextmanager
def exclusive_lock(fd: int) -> Iterator[None]:
    """Hold an exclusive lock on the open file `fd` for the `with` block.

    POSIX: `fcntl.flock`, which waits as long as it takes; closing the file releases it.
    Windows: `msvcrt.locking` on the first byte, tried `LOCK_TRIES` times, then `LockBusy`.
    """
    if not is_windows():
        import fcntl

        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
        return
    import msvcrt

    os.lseek(fd, 0, os.SEEK_SET)
    for attempt in range(LOCK_TRIES):
        try:
            msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
            break
        except OSError:
            if attempt == LOCK_TRIES - 1:
                raise LockBusy(errno.EAGAIN, "the lock is busy") from None
    try:
        yield
    finally:
        os.lseek(fd, 0, os.SEEK_SET)
        with contextlib.suppress(OSError):
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)


def reload_signal() -> signal.Signals | None:
    """SIGHUP where the system has it. Windows has none: `uconnector reload` is the way there."""
    return getattr(signal, "SIGHUP", None)


def default_state_dir() -> Path:
    """The per-user state folder. Raise ValueError with a fixed text when it cannot be known.

    Windows: `%LOCALAPPDATA%\\universal-connector\\state`. macOS:
    `~/Library/Application Support/universal-connector/state`. Linux and others:
    `$XDG_STATE_HOME/universal-connector/state`, else `~/.local/state/universal-connector/state`.
    """
    if is_windows():
        base = os.environ.get("LOCALAPPDATA", "")
        if not base or not Path(base).is_absolute():
            raise ValueError(NO_APP_DATA)
        return Path(base) / APP_NAME / "state"
    try:
        home = Path.home()
    except (KeyError, RuntimeError):
        raise ValueError(NO_HOME) from None
    if PLATFORM == "macos":
        return home / "Library" / "Application Support" / APP_NAME / "state"
    xdg = os.environ.get("XDG_STATE_HOME", "")
    root = Path(xdg) if xdg and Path(xdg).is_absolute() else home / ".local" / "state"
    return root / APP_NAME / "state"
