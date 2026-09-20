"""Per-service rate limiters."""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Protocol

from bacsy.ratelimit.bucket import TokenBucket

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from bacsy.config import RateLimitConfig
    from bacsy.routes import Service


class RateLimiter(Protocol):
    """Paces requests per service."""

    async def acquire(self, service: Service) -> None:
        """Wait until one request to `service` may proceed."""
        ...

    def penalize(self, service: Service, delay: float) -> None:
        """Block requests to `service` for `delay` seconds."""
        ...


class NoopRateLimiter:
    """A `RateLimiter` that never waits and ignores penalties."""

    async def acquire(self, service: Service) -> None:
        return None

    def penalize(self, service: Service, delay: float) -> None:
        return None


class ServiceRateLimiter:
    """One `TokenBucket` per service, sized from `RateLimitConfig`.

    When the configuration is disabled, `acquire` returns immediately and `penalize`
    has no effect.
    """

    def __init__(
        self,
        config: RateLimitConfig,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._config: RateLimitConfig = config
        self._clock: Callable[[], float] = clock
        self._sleep: Callable[[float], Awaitable[None]] = sleep
        self._buckets: dict[Service, TokenBucket] = {}

    def bucket(self, service: Service) -> TokenBucket:
        """Return the bucket for `service`, creating it on first use."""
        bucket = self._buckets.get(service)
        if bucket is None:
            rate = self._config.rate_for(service)
            bucket = TokenBucket(rate, clock=self._clock, sleep=self._sleep)
            self._buckets[service] = bucket
        return bucket

    async def acquire(self, service: Service) -> None:
        if self._config.enabled:
            await self.bucket(service).acquire()

    def penalize(self, service: Service, delay: float) -> None:
        if self._config.enabled:
            self.bucket(service).penalize(delay)
