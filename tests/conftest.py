"""Shared pytest fixtures."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

import httpx2
import pytest

from bacsy import ApiHttpClient, ClientConfig, TradeApiClient
from bacsy.auth import StaticAccessTokenProvider
from bacsy.ratelimit import NoopRateLimiter

if TYPE_CHECKING:
    from pathlib import Path

    from bacsy.auth import AccessTokenProvider
    from bacsy.ratelimit import RateLimiter

Handler = Callable[[httpx2.Request], httpx2.Response]


class ClientFactory(Protocol):
    def __call__(
        self,
        handler: Handler,
        /,
        *,
        access_token: str = "test-token",
        token_provider: AccessTokenProvider | None = None,
        config: ClientConfig | None = None,
        rate_limiter: RateLimiter | None = None,
    ) -> TradeApiClient: ...


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Keep tests away from the developer's real environment and credential files."""
    for name in (
        "BACSY_REFRESH_TOKEN",
        "BACSY_ACCOUNT",
        "NO_COLOR",
        "FORCE_COLOR",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("BACSY_STATE_DIR", str(tmp_path))


@pytest.fixture
async def make_client() -> AsyncIterator[ClientFactory]:
    """Build clients over a mock transport and close the pools after the test.

    Each client is a ``TradeApiClient`` over an ``ApiHttpClient`` that uses a static
    token provider and an ``httpx2.MockTransport`` pool, so no credentials are resolved.
    """
    pools: list[httpx2.AsyncClient] = []

    def factory(
        handler: Handler,
        /,
        *,
        access_token: str = "test-token",
        token_provider: AccessTokenProvider | None = None,
        config: ClientConfig | None = None,
        rate_limiter: RateLimiter | None = None,
    ) -> TradeApiClient:
        config = config or ClientConfig()
        pool = httpx2.AsyncClient(
            transport=httpx2.MockTransport(handler), base_url=config.rest_base_url
        )
        pools.append(pool)
        http = ApiHttpClient(
            token_provider or StaticAccessTokenProvider(access_token),
            http=pool,
            config=config,
            rate_limiter=rate_limiter or NoopRateLimiter(),
        )
        return TradeApiClient(http)

    yield factory

    for pool in pools:
        await pool.aclose()


@dataclass
class FakeClock:
    """A manual clock whose ``sleep`` advances time instead of waiting."""

    now: float = 1_000_000.0
    sleeps: list[float] = field(default_factory=list)

    def __call__(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


@pytest.fixture
def fake_clock() -> FakeClock:
    return FakeClock()
