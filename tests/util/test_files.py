"""Owner-only files and the writers' lock beside them."""

from __future__ import annotations

import asyncio
import contextlib
import stat
import sys
from asyncio.subprocess import PIPE
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING

import pytest

from bacsy._util.files import FileLock, read_private_text, write_private_text

if TYPE_CHECKING:
    from pathlib import Path


def test_read_private_text_returns_none_for_a_missing_file(tmp_path: Path) -> None:
    assert read_private_text(tmp_path / "missing.json") is None


def test_writers_over_one_file_do_not_collide(tmp_path: Path) -> None:
    path = tmp_path / "state" / "data.json"
    texts = [f"text {i}" for i in range(8)]

    def write(text: str) -> None:
        write_private_text(path, text)

    with ThreadPoolExecutor(len(texts)) as pool:
        list(pool.map(write, texts))

    assert path.read_text() in texts
    assert [p.name for p in path.parent.iterdir()] == ["data.json"]


async def test_file_lock_serialises_two_holders(tmp_path: Path) -> None:
    path = tmp_path / "data.json"
    marker = tmp_path / "marker"
    entered = asyncio.Event()

    async def first() -> None:
        async with FileLock(path):
            entered.set()
            await asyncio.sleep(0.05)
            await asyncio.to_thread(marker.write_text, "done")

    async def second() -> str:
        await entered.wait()
        async with FileLock(path):
            return await asyncio.to_thread(marker.read_text)

    _, seen = await asyncio.gather(first(), second())

    assert seen == "done"


CHILD = """
import asyncio
import sys
from pathlib import Path

from bacsy._util.files import FileLock


async def main() -> None:
    async with FileLock(Path(sys.argv[1])):
        print("locked", flush=True)
        await asyncio.to_thread(sys.stdin.readline)


asyncio.run(main())
"""


async def test_file_lock_excludes_another_process(tmp_path: Path) -> None:
    path = tmp_path / "data.json"
    child = await asyncio.create_subprocess_exec(
        sys.executable, "-c", CHILD, str(path), stdin=PIPE, stdout=PIPE
    )
    assert child.stdin is not None
    assert child.stdout is not None
    acquired = asyncio.Event()
    task: asyncio.Task[None] | None = None

    async def take() -> None:
        async with FileLock(path):
            acquired.set()

    try:
        assert (await asyncio.wait_for(child.stdout.readline(), 30)).rstrip() == b"locked"
        task = asyncio.create_task(take())
        await asyncio.sleep(0.2)
        assert not acquired.is_set()
        child.stdin.close()
        await asyncio.wait_for(task, 30)
    finally:
        child.stdin.close()
        await asyncio.wait_for(child.wait(), 30)
        if task is not None and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    assert acquired.is_set()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions")
async def test_file_lock_creates_an_owner_only_file(tmp_path: Path) -> None:
    path = tmp_path / "state" / "data.json"

    async with FileLock(path):
        pass

    lock_file = path.with_name("data.json.lock")
    assert stat.S_IMODE(lock_file.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
