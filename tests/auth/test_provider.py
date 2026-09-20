"""Access-token providers: token selection, caching, failover and single-flight refresh."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import pytest

from bacsy.auth import (
    AccessToken,
    MemoryAccessTokenCache,
    RefreshingAccessTokenProvider,
    RefreshToken,
    StaticAccessTokenProvider,
    TokenScope,
)
from bacsy.exceptions import (
    AuthError,
    ConfigurationError,
    NoUsableTokenError,
    ServerError,
    TokenRefreshError,
    TokenRefreshReason,
    TransportError,
)
from tests.auth.fakes import DAY, Keycloak, make_refresh_token

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Sequence

    import httpx2

    from tests.conftest import FakeClock


@pytest.fixture
def keycloak(fake_clock: FakeClock) -> Keycloak:
    return Keycloak(clock=fake_clock)


@pytest.fixture
async def http(keycloak: Keycloak) -> AsyncIterator[httpx2.AsyncClient]:
    async with keycloak.http() as client:
        yield client


def _token(
    fake_clock: FakeClock, *, scope: TokenScope = TokenScope.READ, days: int = 30, sid: str
) -> RefreshToken:
    return RefreshToken.parse(
        make_refresh_token(scope=scope, exp=int(fake_clock.now) + days * DAY, sid=sid)
    )


class Rejections:
    """Records what the provider reports through ``on_rejected``."""

    def __init__(self) -> None:
        self.seen: dict[str, TokenRefreshReason] = {}

    async def __call__(self, token: RefreshToken, reason: TokenRefreshReason) -> None:
        self.seen[token.sid] = reason


def _provider(
    http: httpx2.AsyncClient,
    fake_clock: FakeClock,
    tokens: Sequence[RefreshToken],
    cache: MemoryAccessTokenCache | None = None,
    on_rejected: Rejections | None = None,
) -> tuple[RefreshingAccessTokenProvider, MemoryAccessTokenCache]:
    cache = cache or MemoryAccessTokenCache()
    provider = RefreshingAccessTokenProvider(
        tokens,
        http=http,
        cache=cache,
        on_rejected=on_rejected,
        access_skew_seconds=60,
        clock=fake_clock,
    )
    return provider, cache


async def test_static_provider_ignores_scope() -> None:
    provider = StaticAccessTokenProvider("t")

    assert await provider.get(TokenScope.WRITE) == "t"
    await provider.invalidate("t")
    assert await provider.get(TokenScope.READ) == "t"


async def test_first_call_exchanges_with_matching_client_and_caches_by_session(
    http: httpx2.AsyncClient, fake_clock: FakeClock, keycloak: Keycloak
) -> None:
    account = (_token(fake_clock, sid="s1"),)
    provider, cache = _provider(http, fake_clock, account)

    first = await provider.get(TokenScope.READ)
    second = await provider.get(TokenScope.READ)

    assert first == second == "acc1"
    assert keycloak.client_ids() == ["trade-api-read"]
    cached = await cache.get("s1")
    assert cached is not None
    assert cached.value == "acc1"
    assert provider.current[TokenScope.READ][0].sid == "s1"


async def test_expiry_triggers_a_new_exchange(
    http: httpx2.AsyncClient, fake_clock: FakeClock, keycloak: Keycloak
) -> None:
    account = (_token(fake_clock, sid="s1"),)
    provider, _ = _provider(http, fake_clock, account)

    await provider.get(TokenScope.READ)
    fake_clock.now += DAY - 30

    assert await provider.get(TokenScope.READ) == "acc2"
    assert len(keycloak.calls) == 2


async def test_reuses_a_cached_access_token_from_a_previous_process(
    http: httpx2.AsyncClient, fake_clock: FakeClock, keycloak: Keycloak
) -> None:
    cache = MemoryAccessTokenCache()
    await cache.set(
        "s1", AccessToken(value="old", expires_at=int(fake_clock.now) + 3600, scope=TokenScope.READ)
    )
    account = (_token(fake_clock, sid="s1"),)
    provider, _ = _provider(http, fake_clock, account, cache)

    assert await provider.get(TokenScope.READ) == "old"
    assert keycloak.calls == []


async def test_read_prefers_the_read_token_and_write_uses_the_write_token(
    http: httpx2.AsyncClient, fake_clock: FakeClock, keycloak: Keycloak
) -> None:
    account = (
        _token(fake_clock, scope=TokenScope.WRITE, sid="w"),
        _token(fake_clock, sid="r"),
    )
    provider, _ = _provider(http, fake_clock, account)

    read = await provider.get(TokenScope.READ)
    write = await provider.get(TokenScope.WRITE)

    assert read != write
    assert keycloak.client_ids() == ["trade-api-read", "trade-api-write"]
    assert provider.current[TokenScope.READ][0].sid == "r"
    assert provider.current[TokenScope.WRITE][0].sid == "w"


async def test_write_only_account_serves_both_scopes_with_one_exchange(
    http: httpx2.AsyncClient, fake_clock: FakeClock, keycloak: Keycloak
) -> None:
    account = (_token(fake_clock, scope=TokenScope.WRITE, sid="w"),)
    provider, _ = _provider(http, fake_clock, account)

    read = await provider.get(TokenScope.READ)
    write = await provider.get(TokenScope.WRITE)

    assert read == write == "acc1"
    assert keycloak.client_ids() == ["trade-api-write"]


async def test_revoked_token_is_reported_and_skipped(
    http: httpx2.AsyncClient,
    fake_clock: FakeClock,
    keycloak: Keycloak,
    caplog: pytest.LogCaptureFixture,
) -> None:
    revoked = _token(fake_clock, days=80, sid="revoked")
    backup = _token(fake_clock, days=20, sid="backup")
    keycloak.revoked.add("revoked")
    rejections = Rejections()
    provider, _ = _provider(http, fake_clock, (revoked, backup), on_rejected=rejections)

    with caplog.at_level(logging.WARNING, logger="bacsy.auth"):
        token = await provider.get(TokenScope.READ)

    assert token == "acc1"
    assert len(keycloak.calls) == 2
    assert rejections.seen == {"revoked": TokenRefreshReason.REVOKED}
    assert provider.rejected == {"revoked": TokenRefreshReason.REVOKED}
    assert provider.current[TokenScope.READ][0].sid == "backup"
    assert revoked.short in caplog.text
    assert revoked.value not in caplog.text

    await provider.get(TokenScope.READ)
    assert len(keycloak.calls) == 2


async def test_server_side_expiry_is_reported(
    http: httpx2.AsyncClient, fake_clock: FakeClock, keycloak: Keycloak
) -> None:
    stale = _token(fake_clock, days=1, sid="stale")
    fresh = _token(fake_clock, scope=TokenScope.WRITE, days=50, sid="fresh")
    rejections = Rejections()
    provider, _ = _provider(http, fake_clock, (stale, fresh), on_rejected=rejections)
    # The read token is tried first; the server clock runs ahead and rejects it as expired
    # while the provider still believes it is valid.
    keycloak.clock = lambda: fake_clock.now + 2 * DAY

    await provider.get(TokenScope.READ)

    assert rejections.seen == {"stale": TokenRefreshReason.EXPIRED}
    assert provider.current[TokenScope.READ][0].sid == "fresh"


async def test_invalid_token_is_reported_and_skipped_for_the_process(
    http: httpx2.AsyncClient, fake_clock: FakeClock, keycloak: Keycloak
) -> None:
    bad = _token(fake_clock, days=80, sid="bad")
    good = _token(fake_clock, days=20, sid="good")
    keycloak.invalid.add(bad.value)
    rejections = Rejections()
    provider, _ = _provider(http, fake_clock, (bad, good), on_rejected=rejections)

    assert await provider.get(TokenScope.READ) == "acc1"
    assert rejections.seen == {"bad": TokenRefreshReason.INVALID}
    assert provider.current[TokenScope.READ][0].sid == "good"
    assert len(keycloak.calls) == 2
    await provider.invalidate("acc1")
    await provider.get(TokenScope.READ)
    assert len(keycloak.calls) == 3  # the invalid token is not retried


async def test_unknown_rejection_raises_without_marking(
    fake_clock: FakeClock,
) -> None:
    import httpx2

    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            400, json={"error": "invalid_grant", "error_description": "Something new"}
        )

    account = (_token(fake_clock, sid="s1"),)
    async with httpx2.AsyncClient(
        transport=httpx2.MockTransport(handler), base_url="https://be.broker.ru"
    ) as http:
        rejections = Rejections()
        provider, _ = _provider(http, fake_clock, account, on_rejected=rejections)
        with pytest.raises(TokenRefreshError) as info:
            await provider.get(TokenScope.READ)

    assert info.value.reason is TokenRefreshReason.UNKNOWN
    assert rejections.seen == {}
    assert provider.rejected == {}


@pytest.mark.parametrize("failure", ["transport", "server"])
async def test_transport_and_server_errors_propagate(fake_clock: FakeClock, failure: str) -> None:
    import httpx2

    def handler(request: httpx2.Request) -> httpx2.Response:
        if failure == "transport":
            raise httpx2.ConnectError("down", request=request)
        return httpx2.Response(503, text="down")

    account = (_token(fake_clock, sid="s1"),)
    async with httpx2.AsyncClient(
        transport=httpx2.MockTransport(handler), base_url="https://be.broker.ru"
    ) as http:
        provider, _ = _provider(http, fake_clock, account)
        with pytest.raises(TransportError if failure == "transport" else ServerError):
            await provider.get(TokenScope.READ)


async def test_exhausted_account_raises_a_redacted_summary(
    http: httpx2.AsyncClient, fake_clock: FakeClock, keycloak: Keycloak
) -> None:
    expired = _token(fake_clock, days=-1, sid="expired")
    revoked = _token(fake_clock, scope=TokenScope.WRITE, days=10, sid="revoked")
    read_only = _token(fake_clock, days=10, sid="read")
    keycloak.revoked.add("revoked")
    provider, _ = _provider(http, fake_clock, (expired, revoked, read_only))

    with pytest.raises(NoUsableTokenError, match="no usable write token") as info:
        await provider.get(TokenScope.WRITE)

    message = str(info.value)
    assert "1 expired" in message
    assert "1 revoked" in message
    assert "1 read-only" in message
    assert revoked.value not in message
    error = info.value
    assert isinstance(error, AuthError)
    assert error.scope is TokenScope.WRITE
    assert error.expired == 1
    assert error.read_only == 1
    assert error.rejected == {TokenRefreshReason.REVOKED: 1}


async def test_read_only_tokens_cannot_serve_a_write(
    http: httpx2.AsyncClient, fake_clock: FakeClock, keycloak: Keycloak
) -> None:
    provider, _ = _provider(http, fake_clock, (_token(fake_clock, days=10, sid="read"),))

    with pytest.raises(NoUsableTokenError, match=r"\(1 read-only\)") as info:
        await provider.get(TokenScope.WRITE)

    assert info.value.scope is TokenScope.WRITE
    assert (info.value.expired, info.value.read_only, info.value.rejected) == (0, 1, {})
    assert keycloak.calls == []


async def test_empty_account_raises(http: httpx2.AsyncClient, fake_clock: FakeClock) -> None:
    provider, _ = _provider(http, fake_clock, ())

    with pytest.raises(NoUsableTokenError, match="no refresh tokens configured") as info:
        await provider.get(TokenScope.READ)

    assert info.value.scope is TokenScope.READ
    assert (info.value.expired, info.value.read_only, info.value.rejected) == (0, 0, {})


async def test_concurrent_callers_share_one_exchange(
    http: httpx2.AsyncClient, fake_clock: FakeClock, keycloak: Keycloak
) -> None:
    keycloak.delay = 0.01
    account = (_token(fake_clock, scope=TokenScope.WRITE, sid="w"),)
    provider, _ = _provider(http, fake_clock, account)

    scopes = [TokenScope.READ, TokenScope.WRITE] * 10
    tokens = await asyncio.gather(*(provider.get(s) for s in scopes))

    assert set(tokens) == {"acc1"}
    assert len(keycloak.calls) == 1


async def test_invalidate_drops_the_cache_entry_and_remints(
    http: httpx2.AsyncClient, fake_clock: FakeClock, keycloak: Keycloak
) -> None:
    account = (_token(fake_clock, sid="s1"),)
    provider, cache = _provider(http, fake_clock, account)
    token = await provider.get(TokenScope.READ)

    await provider.invalidate("other")
    assert await provider.get(TokenScope.READ) == token
    await provider.invalidate(token)

    assert await cache.get("s1") is None
    assert await provider.get(TokenScope.READ) == "acc2"


async def test_lazy_tokens_are_resolved_once(
    http: httpx2.AsyncClient, fake_clock: FakeClock
) -> None:
    resolutions = 0
    tokens = (_token(fake_clock, sid="s1"),)

    async def resolve() -> tuple[RefreshToken, ...]:
        nonlocal resolutions
        resolutions += 1
        return tokens

    provider = RefreshingAccessTokenProvider(resolve, http=http, clock=fake_clock)
    token = await provider.get(TokenScope.READ)
    await provider.invalidate(token)
    await provider.get(TokenScope.READ)

    assert resolutions == 1
    assert (await provider.tokens()) == tokens


async def test_lazy_tokens_failure_propagates(
    http: httpx2.AsyncClient, fake_clock: FakeClock
) -> None:
    async def resolve() -> tuple[RefreshToken, ...]:
        raise ConfigurationError("no account")

    provider = RefreshingAccessTokenProvider(resolve, http=http, clock=fake_clock)

    with pytest.raises(ConfigurationError, match="no account"):
        await provider.get(TokenScope.READ)


@pytest.mark.parametrize(("days", "warned"), [(3, True), (30, False)])
async def test_warns_once_when_the_chosen_token_expires_soon(
    http: httpx2.AsyncClient,
    fake_clock: FakeClock,
    caplog: pytest.LogCaptureFixture,
    days: int,
    warned: bool,
) -> None:
    token = _token(fake_clock, days=days, sid="s1")
    provider, _ = _provider(http, fake_clock, (token,))

    with caplog.at_level(logging.WARNING, logger="bacsy.auth"):
        first = await provider.get(TokenScope.READ)
        await provider.invalidate(first)
        await provider.get(TokenScope.READ)

    messages = [r.getMessage() for r in caplog.records if "expires in" in r.getMessage()]
    assert (len(messages) == 1) is warned
    if warned:
        assert token.short in messages[0]
        assert token.value not in messages[0]
