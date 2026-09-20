"""Owner-only text files: permission-checked reads, atomic writes, and a writers' lock."""

from __future__ import annotations

import asyncio
import logging
import os
import stat
import sys
import tempfile
from pathlib import Path
from typing import Self

if sys.platform == "win32":
    import msvcrt

    def _lock_exclusive(fd: int) -> None:
        msvcrt.locking(fd, msvcrt.LK_LOCK, 1)

    def _unlock(fd: int) -> None:
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)

else:
    import fcntl

    def _lock_exclusive(fd: int) -> None:
        fcntl.flock(fd, fcntl.LOCK_EX)

    def _unlock(fd: int) -> None:
        fcntl.flock(fd, fcntl.LOCK_UN)


log = logging.getLogger("bacsy")


def read_private_text(path: Path) -> str | None:
    """Return the text of `path`, or `None` when it does not exist.

    Logs a warning when the file grants any permission to group or others; the check is
    skipped on Windows.
    """
    try:
        mode = path.stat().st_mode
    except FileNotFoundError:
        return None
    if sys.platform != "win32" and mode & (stat.S_IRWXG | stat.S_IRWXO):
        log.warning("%s is readable by other users; run: chmod 600 %s", path, path)
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None


def write_private_text(path: Path, text: str) -> None:
    """Write `text` to `path` atomically with owner-only permissions.

    Creates the destination directory with mode `0o700` if missing; intermediate
    directories use default permissions. The text is written to a uniquely named
    temporary file in the same directory, created with mode `0o600`, which then replaces
    `path`; the temporary file is removed if writing fails.
    """
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    tmp = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        tmp.replace(path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


class FileLock:
    """An exclusive advisory lock for writers of `path`, kept in `<path>.lock` beside it.

    Use as ``async with FileLock(path):`` around a read-modify-write. Entering and
    leaving run in a worker thread; the lock is tied to the open descriptor, not the
    thread, so holding it across ``await`` is fine. Writers in this process and in other
    processes take turns; readers need not hold it, since writes replace the file
    atomically.

    The lock file is created with owner-only permissions and is never removed: removing
    it would let a later holder in beside the current one. On POSIX the lock is
    `fcntl.flock`, which the kernel releases when the descriptor closes, so a crashed
    holder leaves nothing stale. On Windows it is `msvcrt.locking` on one byte, which
    gives up after ten seconds and raises `OSError`.
    """

    def __init__(self, path: Path) -> None:
        self._path: Path = path.with_name(path.name + ".lock")
        self._fd: int | None = None

    def _acquire(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(self._path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            _lock_exclusive(fd)
        except BaseException:
            os.close(fd)
            raise
        self._fd = fd

    def _release(self) -> None:
        fd, self._fd = self._fd, None
        if fd is None:
            return
        try:
            _unlock(fd)
        finally:
            os.close(fd)

    async def __aenter__(self) -> Self:
        await asyncio.to_thread(self._acquire)
        return self

    async def __aexit__(self, *exc: object) -> None:
        await asyncio.to_thread(self._release)
