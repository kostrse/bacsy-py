"""Bundled `AccessTokenCache` implementations.

Entries are keyed by the refresh token's `sid`. Expiry is read from the stored token.
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from bacsy._util.files import FileLock, read_private_text, write_private_text
from bacsy._util.paths import state_dir
from bacsy.auth.tokens import AccessToken, TokenScope

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

log = logging.getLogger("bacsy.auth")

TOKEN_CACHE_FILENAME = "tokens.json"
_CACHE_VERSION = 1


class _AccessTokenEntry(BaseModel):
    """One cached access token; field names are the file format."""

    model_config = ConfigDict(strict=True, extra="ignore", frozen=True)

    token: str = Field(repr=False)
    expires_at: int
    scope: TokenScope

    @classmethod
    def of(cls, token: AccessToken) -> _AccessTokenEntry:
        return cls(token=token.value, expires_at=token.expires_at, scope=token.scope)

    def to_token(self) -> AccessToken:
        return AccessToken(value=self.token, expires_at=self.expires_at, scope=self.scope)


class _CacheFile(BaseModel):
    """The `tokens.json` document."""

    model_config = ConfigDict(strict=True, extra="ignore", frozen=True)

    version: int
    access: dict[str, _AccessTokenEntry] = {}


class MemoryAccessTokenCache:
    """Access tokens kept in a dictionary for the lifetime of the process."""

    def __init__(self) -> None:
        self._access: dict[str, AccessToken] = {}

    async def get(self, sid: str) -> AccessToken | None:
        return self._access.get(sid)

    async def set(self, sid: str, token: AccessToken) -> None:
        self._access[sid] = token

    async def delete(self, sid: str) -> None:
        self._access.pop(sid, None)


def default_token_cache_path(env: Mapping[str, str] | None = None) -> Path:
    """Return the path of the token cache file in the state directory for `env`."""
    return state_dir(env) / TOKEN_CACHE_FILENAME


class FileAccessTokenCache:
    """Access tokens in a JSON file with owner-only permissions.

    The file is read on every access and written atomically. Expired entries are dropped
    on every write. A file that does not match the cache layout, has an unsupported
    version, or is not valid JSON or UTF-8, is treated as empty and a warning is logged.
    A file that cannot be read or written raises `OSError`.
    Writers over one file, in this process or another, take turns through a lock file
    beside it; readers never wait.

    Args:
        path: The cache file; defaults to `default_token_cache_path()`.
        clock: Returns the current Unix time, used to drop expired entries.
    """

    def __init__(
        self, path: Path | str | None = None, *, clock: Callable[[], float] = time.time
    ) -> None:
        self._path: Path = Path(path).expanduser() if path else default_token_cache_path()
        self._clock: Callable[[], float] = clock

    @property
    def path(self) -> Path:
        """The cache file."""
        return self._path

    def _fresh(self, why: str) -> dict[str, AccessToken]:
        log.warning("%s %s; starting a fresh token cache", self._path, why)
        return {}

    def _parse(self, text: str) -> dict[str, AccessToken]:
        try:
            document = _CacheFile.model_validate_json(text)
        except ValidationError:
            return self._fresh("cannot be read as a token cache")
        if document.version != _CACHE_VERSION:
            return self._fresh("has an unsupported version")
        return {sid: entry.to_token() for sid, entry in document.access.items()}

    async def _read(self) -> dict[str, AccessToken]:
        try:
            text = await asyncio.to_thread(read_private_text, self._path)
        except UnicodeDecodeError:
            return self._fresh("is not valid UTF-8")
        return {} if text is None else self._parse(text)

    async def _write(self, access: Mapping[str, AccessToken]) -> None:
        now = self._clock()
        document = _CacheFile(
            version=_CACHE_VERSION,
            access={
                sid: _AccessTokenEntry.of(token)
                for sid, token in access.items()
                if token.is_valid(now)
            },
        )
        await asyncio.to_thread(write_private_text, self._path, document.model_dump_json(indent=2))

    async def get(self, sid: str) -> AccessToken | None:
        return (await self._read()).get(sid)

    async def set(self, sid: str, token: AccessToken) -> None:
        async with FileLock(self._path):
            access = await self._read()
            access[sid] = token
            await self._write(access)

    async def delete(self, sid: str) -> None:
        async with FileLock(self._path):
            access = await self._read()
            if access.pop(sid, None) is not None:
                await self._write(access)


def _reason(exc: OSError) -> str:
    return exc.strerror or type(exc).__name__


class DefaultAccessTokenCache:
    """Access tokens kept in memory and in a file in the state directory.

    Tokens are kept in memory for the lifetime of the process and written to the file
    for later processes. When no state directory can be located, or the file cannot be
    read, tokens stay in memory. When the file can be read but not written, the tokens
    already in it are still used and new ones stay in memory. Each condition is logged
    once as a warning; a file that cannot be used never raises.

    Args:
        path: The cache file; defaults to `default_token_cache_path()`.
        clock: Returns the current Unix time, used to drop expired entries from the file.
    """

    def __init__(
        self, path: Path | str | None = None, *, clock: Callable[[], float] = time.time
    ) -> None:
        self._memory = MemoryAccessTokenCache()
        self._file: FileAccessTokenCache | None
        try:
            self._file = FileAccessTokenCache(path, clock=clock)
        except RuntimeError:
            log.warning("no state directory available; caching access tokens in memory only")
            self._file = None
        self._writable = True

    def _stop_reading(self, file: FileAccessTokenCache, exc: OSError) -> None:
        log.warning(
            "%s cannot be read (%s); caching access tokens in memory only",
            file.path,
            _reason(exc),
        )
        self._file = None

    def _stop_writing(self, file: FileAccessTokenCache, exc: OSError) -> None:
        log.warning(
            "%s cannot be written (%s); new access tokens are kept in memory only, "
            "set BACSY_STATE_DIR to a writable directory to persist them",
            file.path,
            _reason(exc),
        )
        self._writable = False

    async def get(self, sid: str) -> AccessToken | None:
        token = await self._memory.get(sid)
        if token is None and (file := self._file) is not None:
            try:
                token = await file.get(sid)
            except OSError as exc:
                self._stop_reading(file, exc)
        return token

    async def set(self, sid: str, token: AccessToken) -> None:
        await self._memory.set(sid, token)
        if (file := self._file) is not None and self._writable:
            try:
                await file.set(sid, token)
            except OSError as exc:
                self._stop_writing(file, exc)

    async def delete(self, sid: str) -> None:
        await self._memory.delete(sid)
        if (file := self._file) is not None and self._writable:
            try:
                await file.delete(sid)
            except OSError as exc:
                self._stop_writing(file, exc)
