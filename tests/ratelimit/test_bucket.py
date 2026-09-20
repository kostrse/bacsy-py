"""Token bucket pacing with a fake clock."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from bacsy.ratelimit import TokenBucket

if TYPE_CHECKING:
    from tests.conftest import FakeClock


async def test_burst_then_pace(fake_clock: FakeClock) -> None:
    bucket = TokenBucket(2.0, clock=fake_clock, sleep=fake_clock.sleep)

    for _ in range(2):
        await bucket.acquire()
    assert fake_clock.sleeps == []

    await bucket.acquire()
    assert fake_clock.sleeps == [pytest.approx(0.5)]
    await bucket.acquire()
    assert fake_clock.sleeps == [pytest.approx(0.5), pytest.approx(0.5)]


async def test_refills_over_time(fake_clock: FakeClock) -> None:
    bucket = TokenBucket(2.0, clock=fake_clock, sleep=fake_clock.sleep)
    await bucket.acquire()
    await bucket.acquire()
    fake_clock.now += 10

    await bucket.acquire()
    await bucket.acquire()
    assert fake_clock.sleeps == []


async def test_penalize_blocks_everyone(fake_clock: FakeClock) -> None:
    bucket = TokenBucket(10.0, clock=fake_clock, sleep=fake_clock.sleep)
    bucket.penalize(3.0)

    await bucket.acquire()
    assert fake_clock.sleeps == [pytest.approx(3.0)]


def test_rejects_non_positive_rate() -> None:
    with pytest.raises(ValueError, match="positive"):
        TokenBucket(0)
