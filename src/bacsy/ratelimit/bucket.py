"""Token bucket with an injectable clock and sleep."""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


class TokenBucket:
    """Allow `rate` operations per second with bursts of up to `capacity`.

    `capacity` defaults to `max(1.0, rate)`. `acquire` waits while holding a lock, so
    waiters are served in order. `penalize` blocks every caller for a period.

    Raises:
        ValueError: If `rate` is not positive.
    """

    def __init__(
        self,
        rate: float,
        capacity: float | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if rate <= 0:
            msg = "rate must be positive"
            raise ValueError(msg)
        self._rate: float = rate
        self._capacity: float = capacity if capacity is not None else max(1.0, rate)
        self._tokens: float = self._capacity
        self._clock: Callable[[], float] = clock
        self._sleep: Callable[[float], Awaitable[None]] = sleep
        self._updated: float = clock()
        self._blocked_until: float = self._updated
        self._lock = asyncio.Lock()

    def _refill(self, now: float) -> None:
        elapsed = max(0.0, now - self._updated)
        self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
        self._updated = now

    async def acquire(self) -> None:
        """Wait until one operation may proceed."""
        async with self._lock:
            now = self._clock()
            if now < self._blocked_until:
                await self._sleep(self._blocked_until - now)
                now = self._clock()
            self._refill(now)
            if self._tokens < 1.0:
                await self._sleep((1.0 - self._tokens) / self._rate)
                self._refill(self._clock())
            self._tokens -= 1.0

    def penalize(self, delay: float) -> None:
        """Block every caller for `delay` seconds from now.

        An earlier, longer block is kept.
        """
        self._blocked_until = max(self._blocked_until, self._clock() + delay)
