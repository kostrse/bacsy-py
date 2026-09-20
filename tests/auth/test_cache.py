"""The bundled access token caches."""

from __future__ import annotations

import asyncio
import errno
import json
import logging
import stat
import sys
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest

from bacsy.auth import (
    AccessToken,
    DefaultAccessTokenCache,
    FileAccessTokenCache,
    MemoryAccessTokenCache,
    TokenScope,
    default_token_cache_path,
)
from bacsy.auth import cache as cache_module
from tests.auth.fakes import DAY

if TYPE_CHECKING:
    from tests.conftest import FakeClock

NOW = 1_000_000
FAR = 9_000_000_000_000


def _token(value: str) -> AccessToken:
    return AccessToken(value=value, expires_at=FAR, scope=TokenScope.READ)


def _blocked_path(tmp_path: Path) -> Path:
    """A path whose parent is a regular file, unusable even by root."""
    blocker = tmp_path / "blocker"
    blocker.write_text("")
    return blocker / "tokens.json"


def _messages(caplog: pytest.LogCaptureFixture, fragment: str) -> list[str]:
    return [r.message for r in caplog.records if fragment in r.message]


async def test_memory_cache() -> None:
    cache = MemoryAccessTokenCache()
    token = AccessToken(value="a", expires_at=NOW + DAY, scope=TokenScope.READ)

    await cache.set("sid", token)
    assert await cache.get("sid") == token
    await cache.delete("sid")
    assert await cache.get("sid") is None
    await cache.delete("missing")


async def test_file_cache_round_trip(tmp_path: Path, fake_clock: FakeClock) -> None:
    cache = FileAccessTokenCache(tmp_path / "tokens.json", clock=fake_clock)
    token = AccessToken(value="a", expires_at=int(fake_clock.now) + DAY, scope=TokenScope.WRITE)

    await cache.set("sid", token)

    reopened = FileAccessTokenCache(cache.path, clock=fake_clock)
    assert await reopened.get("sid") == token
    await reopened.delete("sid")
    assert await reopened.get("sid") is None


async def test_file_cache_drops_expired_entries(tmp_path: Path, fake_clock: FakeClock) -> None:
    cache = FileAccessTokenCache(tmp_path / "tokens.json", clock=fake_clock)
    await cache.set(
        "old", AccessToken(value="a", expires_at=int(fake_clock.now) + 10, scope=TokenScope.READ)
    )
    fake_clock.now += DAY
    await cache.set(
        "new", AccessToken(value="b", expires_at=int(fake_clock.now) + DAY, scope=TokenScope.READ)
    )

    document = cast("dict[str, dict[str, object]]", json.loads(cache.path.read_text()))
    assert set(document["access"]) == {"new"}
    assert "dead" not in document


@pytest.mark.parametrize(
    "text",
    [
        "garbage",
        "[]",
        '{"version": 1, "access": 5}',
        '{"version": 2, "access": {}}',
        '{"version": 1, "access": {"good": {"token": "a", "expires_at": 9000000000000, '
        '"scope": "trade-api-read"}, "bad": {"token": 1}}}',
    ],
)
async def test_file_cache_tolerates_corruption(
    tmp_path: Path, text: str, caplog: pytest.LogCaptureFixture
) -> None:
    path = tmp_path / "tokens.json"
    path.write_text(text)

    with caplog.at_level(logging.WARNING, logger="bacsy.auth"):
        assert await FileAccessTokenCache(path).get("good") is None

    assert "fresh token cache" in caplog.text


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions")
async def test_file_cache_writes_owner_only(tmp_path: Path) -> None:
    cache = FileAccessTokenCache(tmp_path / "state" / "tokens.json")
    await cache.set(
        "sid", AccessToken(value="a", expires_at=9_000_000_000_000, scope=TokenScope.READ)
    )

    assert stat.S_IMODE(cache.path.stat().st_mode) == 0o600
    assert stat.S_IMODE(cache.path.parent.stat().st_mode) == 0o700


def test_default_path_follows_the_state_directory(tmp_path: Path) -> None:
    env = {"BACSY_STATE_DIR": str(tmp_path)}

    assert default_token_cache_path(env) == tmp_path / "tokens.json"


async def test_file_cache_raises_when_unwritable(tmp_path: Path) -> None:
    cache = FileAccessTokenCache(_blocked_path(tmp_path))

    with pytest.raises(OSError, match="blocker"):
        await cache.set("sid", _token("a"))


async def test_file_cache_raises_when_unreadable(tmp_path: Path) -> None:
    path = tmp_path / "tokens.json"
    path.mkdir(mode=0o700)

    with pytest.raises(OSError, match=r"tokens\.json"):
        await FileAccessTokenCache(path).get("sid")


async def test_file_cache_treats_invalid_utf8_as_empty(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    path = tmp_path / "tokens.json"
    path.write_bytes(b"\xff\xfe")
    cache = FileAccessTokenCache(path)

    with caplog.at_level(logging.WARNING, logger="bacsy.auth"):
        assert await cache.get("sid") is None
    await cache.set("sid", _token("a"))

    assert "is not valid UTF-8" in caplog.text
    assert await FileAccessTokenCache(path).get("sid") == _token("a")


async def test_default_cache_persists_to_the_file(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    path = tmp_path / "tokens.json"

    with caplog.at_level(logging.WARNING, logger="bacsy.auth"):
        cache = DefaultAccessTokenCache(path)
        await cache.set("sid", _token("a"))
        assert await cache.get("sid") == _token("a")

    assert await FileAccessTokenCache(path).get("sid") == _token("a")
    assert caplog.records == []


async def test_default_cache_reads_what_the_file_holds(tmp_path: Path) -> None:
    path = tmp_path / "tokens.json"
    await FileAccessTokenCache(path).set("sid", _token("a"))

    cache = DefaultAccessTokenCache(path)

    assert await cache.get("sid") == _token("a")
    await cache.delete("sid")
    assert await cache.get("sid") is None
    assert await FileAccessTokenCache(path).get("sid") is None


async def test_default_cache_is_memory_without_a_state_directory(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in ("BACSY_STATE_DIR", "XDG_STATE_HOME", "LOCALAPPDATA", "HOME"):
        monkeypatch.delenv(name, raising=False)

    def _no_home() -> Path:
        msg = "Could not determine home directory."
        raise RuntimeError(msg)

    monkeypatch.setattr(Path, "home", staticmethod(_no_home))

    with caplog.at_level(logging.WARNING, logger="bacsy.auth"):
        cache = DefaultAccessTokenCache()
        await cache.set("sid", _token("a"))
        assert await cache.get("sid") == _token("a")

    assert not (tmp_path / "tokens.json").exists()
    assert _messages(caplog, "no state directory available") == [
        "no state directory available; caching access tokens in memory only"
    ]


async def test_default_cache_is_memory_when_the_file_cannot_be_read(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    path = tmp_path / "tokens.json"
    path.mkdir(mode=0o700)
    cache = DefaultAccessTokenCache(path)

    with caplog.at_level(logging.WARNING, logger="bacsy.auth"):
        assert await cache.get("sid") is None
        await cache.set("sid", _token("a"))
        assert await cache.get("sid") == _token("a")
        await cache.delete("sid")
        assert await cache.get("sid") is None

    assert len(_messages(caplog, "cannot be read")) == 1
    assert path.is_dir()


async def test_default_cache_keeps_new_tokens_in_memory_when_the_file_cannot_be_written(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    path = _blocked_path(tmp_path)
    cache = DefaultAccessTokenCache(path)

    with caplog.at_level(logging.WARNING, logger="bacsy.auth"):
        await cache.set("sid", _token("a"))
        assert await cache.get("sid") == _token("a")
        await cache.set("other", _token("b"))
        assert await cache.get("other") == _token("b")

    (message,) = _messages(caplog, "cannot be written")
    assert "BACSY_STATE_DIR" in message
    assert path.parent.read_text() == ""


async def test_default_cache_still_reads_a_read_only_file(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "tokens.json"
    await FileAccessTokenCache(path).set("stored", _token("a"))
    before = path.read_text()

    def _read_only(path: Path, text: str) -> None:
        raise OSError(errno.EROFS, "Read-only file system", str(path))

    monkeypatch.setattr(cache_module, "write_private_text", _read_only)
    cache = DefaultAccessTokenCache(path)

    with caplog.at_level(logging.WARNING, logger="bacsy.auth"):
        await cache.set("minted", _token("b"))
        assert await cache.get("stored") == _token("a")
        assert await cache.get("minted") == _token("b")

    assert len(_messages(caplog, "cannot be written")) == 1
    assert path.read_text() == before


async def test_default_cache_lets_cancellation_through(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _cancelled(path: Path, text: str) -> None:
        raise asyncio.CancelledError

    monkeypatch.setattr(cache_module, "write_private_text", _cancelled)
    cache = DefaultAccessTokenCache(tmp_path / "tokens.json")

    with pytest.raises(asyncio.CancelledError):
        await cache.set("sid", _token("a"))

    assert await cache.get("sid") == _token("a")


async def test_file_cache_serialises_writers_over_one_path(tmp_path: Path) -> None:
    path = tmp_path / "tokens.json"

    await asyncio.gather(
        FileAccessTokenCache(path).set("first", _token("a")),
        FileAccessTokenCache(path).set("second", _token("b")),
    )

    reader = FileAccessTokenCache(path)
    assert await reader.get("first") == _token("a")
    assert await reader.get("second") == _token("b")


def test_file_cache_survives_successive_event_loops(tmp_path: Path) -> None:
    cache = FileAccessTokenCache(tmp_path / "tokens.json")

    async def burst(run: int) -> None:
        await asyncio.gather(cache.set(f"{run}-a", _token("a")), cache.set(f"{run}-b", _token("b")))

    asyncio.run(burst(1))
    asyncio.run(burst(2))

    document = cast("dict[str, dict[str, object]]", json.loads(cache.path.read_text()))
    assert set(document["access"]) == {"1-a", "1-b", "2-a", "2-b"}


async def test_two_default_caches_share_one_file(tmp_path: Path) -> None:
    path = tmp_path / "tokens.json"

    await asyncio.gather(
        DefaultAccessTokenCache(path).set("first", _token("a")),
        DefaultAccessTokenCache(path).set("second", _token("b")),
    )

    reader = FileAccessTokenCache(path)
    assert await reader.get("first") == _token("a")
    assert await reader.get("second") == _token("b")
