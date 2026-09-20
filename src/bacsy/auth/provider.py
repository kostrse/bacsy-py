"""Bundled `AccessTokenProvider` implementations."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import replace
from typing import TYPE_CHECKING

from bacsy.auth.cache import MemoryAccessTokenCache
from bacsy.auth.keycloak import exchange_refresh_token
from bacsy.auth.tokens import AccessToken, TokenScope, select_refresh_tokens
from bacsy.config import TOKEN_ENDPOINT_PATH
from bacsy.exceptions import NoUsableTokenError, TokenRefreshError, TokenRefreshReason

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Mapping, Sequence

    import httpx2

    from bacsy.auth.protocols import AccessTokenCache
    from bacsy.auth.tokens import RefreshToken

log = logging.getLogger("bacsy.auth")

type RefreshTokenSource = Sequence[RefreshToken] | Callable[[], Awaitable[Sequence[RefreshToken]]]
"""Refresh tokens given up front, or an async callable resolved once on first use."""

type RejectionHook = Callable[[RefreshToken, TokenRefreshReason], Awaitable[None]]
"""Called when the token endpoint rejects a refresh token for a known reason."""


class StaticAccessTokenProvider:
    """A fixed access token. `get` ignores the scope and `invalidate` has no effect."""

    def __init__(self, access_token: str) -> None:
        self._token: str = access_token

    async def get(self, scope: TokenScope) -> str:
        return self._token

    async def invalidate(self, token: str) -> None:
        return None


class RefreshingAccessTokenProvider:
    """Mints access tokens from refresh tokens at the token endpoint.

    For each requested scope the provider picks the least-privileged, longest-lived
    refresh token able to serve it, reuses a cached access token while it is valid, and
    otherwise exchanges the refresh token. A refresh token the endpoint rejects for a
    known reason is logged, dropped from the cache, skipped for the rest of the process
    and passed to `on_rejected`; a rejection with an unknown reason is raised. Exchanges
    are serialised: concurrent callers wait for the exchange in progress, whatever scope
    they asked for.

    Args:
        tokens: The refresh tokens to choose from, or an async callable that returns
            them, called once on first use.
        http: The client used to reach the token endpoint.
        cache: Where minted access tokens are kept; a `MemoryAccessTokenCache` by
            default.
        on_rejected: Called with the refresh token and the reason when the endpoint
            rejects it for a known reason.
        token_path: The token endpoint path, relative to `http`'s base URL.
        access_skew_seconds: How many seconds before its expiry an access token or
            refresh token is treated as expired.
        clock: Returns the current Unix time.
        expiry_warning_seconds: A warning is logged once per refresh token when the
            token chosen for a scope expires within this many seconds.

    Example:
        >>> provider = RefreshingAccessTokenProvider(  # doctest: +SKIP
        ...     [RefreshToken.parse(secret)], http=pool, cache=MemoryAccessTokenCache()
        ... )
    """

    def __init__(
        self,
        tokens: RefreshTokenSource,
        *,
        http: httpx2.AsyncClient,
        cache: AccessTokenCache | None = None,
        on_rejected: RejectionHook | None = None,
        token_path: str = TOKEN_ENDPOINT_PATH,
        access_skew_seconds: float = 60.0,
        clock: Callable[[], float] = time.time,
        expiry_warning_seconds: float = 7 * 24 * 3600.0,
    ) -> None:
        self._source: RefreshTokenSource = tokens
        self._tokens: tuple[RefreshToken, ...] | None = None
        self._http: httpx2.AsyncClient = http
        self._cache: AccessTokenCache = cache if cache is not None else MemoryAccessTokenCache()
        self._on_rejected: RejectionHook | None = on_rejected
        self._token_path: str = token_path
        self._skew: float = access_skew_seconds
        self._clock: Callable[[], float] = clock
        self._warn_within: float = expiry_warning_seconds
        self._hot: dict[TokenScope, tuple[RefreshToken, AccessToken]] = {}
        self._rejected: dict[str, TokenRefreshReason] = {}
        self._warned: set[str] = set()
        self._lock = asyncio.Lock()

    async def tokens(self) -> tuple[RefreshToken, ...]:
        """Return the refresh tokens to choose from, resolving the source on first call."""
        if self._tokens is None:
            source = self._source
            resolved = await source() if callable(source) else source
            self._tokens = tuple(resolved)
        return self._tokens

    @property
    def current(self) -> Mapping[TokenScope, tuple[RefreshToken, AccessToken]]:
        """The refresh and access token currently serving each scope."""
        return dict(self._hot)

    @property
    def rejected(self) -> Mapping[str, TokenRefreshReason]:
        """Session ids the endpoint rejected in this process, with the reason."""
        return dict(self._rejected)

    async def get(self, scope: TokenScope) -> str:
        """Return an access token able to serve `scope`.

        Raises:
            NoUsableTokenError: No refresh token held can serve `scope`.
            TokenRefreshError: The endpoint rejected a refresh token for an unknown
                reason, or returned an unexpected body.
            ServerError: The endpoint failed (HTTP 5xx).
            ApiError: The endpoint answered with another unsuccessful status.
            TransportError: The endpoint could not be reached.
        """
        hot = self._hot.get(scope)
        if hot is not None and hot[1].is_valid(self._clock(), skew=self._skew):
            return hot[1].value
        async with self._lock:
            now = self._clock()
            hot = self._hot.get(scope)
            if hot is not None and hot[1].is_valid(now, skew=self._skew):
                return hot[1].value
            tokens = await self.tokens()
            candidates = select_refresh_tokens(
                tokens, scope, now=now, skew=self._skew, exclude=self._rejected
            )
            for token in candidates:
                minted = await self._obtain(token, now)
                if minted is not None:
                    self._adopt(scope, token, minted, now)
                    return minted.value
            raise _exhausted(tokens, scope, now, self._skew, self._rejected)

    async def _obtain(self, token: RefreshToken, now: float) -> AccessToken | None:
        cached = await self._cache.get(token.sid)
        if cached is not None and cached.is_valid(now, skew=self._skew):
            return cached
        try:
            minted = await exchange_refresh_token(
                self._http,
                token_path=self._token_path,
                scope=token.scope,
                refresh_token=token.value,
                now=now,
            )
        except TokenRefreshError as exc:
            if exc.reason is TokenRefreshReason.UNKNOWN:
                raise
            log.warning("refresh token %s rejected: %s", token.short, exc.reason.value)
            self._rejected[token.sid] = exc.reason
            await self._cache.delete(token.sid)
            if self._on_rejected is not None:
                await self._on_rejected(token, exc.reason)
            return None
        await self._cache.set(token.sid, minted)
        return minted

    def _adopt(
        self, scope: TokenScope, token: RefreshToken, access: AccessToken, now: float
    ) -> None:
        self._hot[scope] = (token, access)
        remaining = token.expires_in(now)
        if remaining < self._warn_within and token.sid not in self._warned:
            self._warned.add(token.sid)
            log.warning(
                "refresh token %s expires in %d day(s); issue a new one in the web terminal",
                token.short,
                max(0, int(remaining // 86400)),
            )

    async def invalidate(self, token: str) -> None:
        """Expire the access token `token` for every scope it serves and drop it from the cache.

        A token that is not currently serving a scope is ignored.
        """
        async with self._lock:
            for scope, (refresh, access) in list(self._hot.items()):
                if access.value == token:
                    await self._cache.delete(refresh.sid)
                    self._hot[scope] = (refresh, replace(access, expires_at=0))


def _exhausted(
    tokens: Sequence[RefreshToken],
    scope: TokenScope,
    now: float,
    skew: float,
    rejected: Mapping[str, TokenRefreshReason],
) -> NoUsableTokenError:
    """Build the error for a `scope` no held token can serve, counting the reasons."""
    if not tokens:
        return NoUsableTokenError(
            "no refresh tokens configured; issue one in the BCS web terminal and add it",
            scope=scope,
        )
    expired = read_only = 0
    by_reason: dict[TokenRefreshReason, int] = {}
    for token in tokens:
        # The same tests, in the same order, that select_refresh_tokens applies.
        if token.is_expired(now, skew=skew):
            expired += 1
        elif token.sid in rejected:
            reason = rejected[token.sid]
            by_reason[reason] = by_reason.get(reason, 0) + 1
        else:
            read_only += 1
    counts = [(expired, "expired"), *((n, r.value) for r, n in by_reason.items())]
    counts.append((read_only, "read-only"))
    detail = ", ".join(f"{n} {label}" for n, label in counts if n)
    return NoUsableTokenError(
        f"no usable {scope.short_name} token ({detail}); issue a new refresh token in "
        "the BCS web terminal and add it",
        scope=scope,
        expired=expired,
        read_only=read_only,
        rejected=by_reason,
    )
