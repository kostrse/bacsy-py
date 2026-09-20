"""Per-service limiter behaviour."""

from __future__ import annotations

from typing import TYPE_CHECKING

from bacsy import RateLimitConfig
from bacsy.ratelimit import NoopRateLimiter, ServiceRateLimiter
from bacsy.routes import Service

if TYPE_CHECKING:
    from tests.conftest import FakeClock


async def test_services_have_independent_buckets(fake_clock: FakeClock) -> None:
    config = RateLimitConfig(safety_factor=1.0, overrides={Service.PORTFOLIO: 1.0})
    limiter = ServiceRateLimiter(config, clock=fake_clock, sleep=fake_clock.sleep)

    await limiter.acquire(Service.PORTFOLIO)
    await limiter.acquire(Service.LIMIT)
    await limiter.acquire(Service.LIMIT)
    assert fake_clock.sleeps == []

    await limiter.acquire(Service.PORTFOLIO)
    assert len(fake_clock.sleeps) == 1


async def test_disabled_limiter_never_waits(fake_clock: FakeClock) -> None:
    config = RateLimitConfig(enabled=False, overrides={Service.PORTFOLIO: 0.001})
    limiter = ServiceRateLimiter(config, clock=fake_clock, sleep=fake_clock.sleep)

    for _ in range(5):
        await limiter.acquire(Service.PORTFOLIO)
    limiter.penalize(Service.PORTFOLIO, 100)
    await limiter.acquire(Service.PORTFOLIO)
    assert fake_clock.sleeps == []


async def test_noop_limiter() -> None:
    limiter = NoopRateLimiter()
    await limiter.acquire(Service.PORTFOLIO)
    limiter.penalize(Service.PORTFOLIO, 1.0)
