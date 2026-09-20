"""Retry classification by operation idempotency and error class."""

from __future__ import annotations

import pytest

from bacsy import RetryPolicy
from bacsy.exceptions import (
    BacsyError,
    BadRequestError,
    ErrorResponse,
    NotFoundError,
    RateLimitError,
    ServerError,
    TransportError,
)
from bacsy.ratelimit import backoff_delay, decide
from bacsy.routes import Operation, Service

READ = Operation(name="read", service=Service.PORTFOLIO, method="GET", path="/r")
WRITE = Operation(
    name="write", service=Service.OPERATIONS, method="POST", path="/w", idempotent=False
)
POLICY = RetryPolicy(jitter=False)


@pytest.mark.parametrize(
    ("operation", "error", "expected"),
    [
        (READ, TransportError("x"), True),
        (READ, ServerError("x", response=ErrorResponse(status_code=503)), True),
        (READ, ServerError("x", response=ErrorResponse(status_code=501)), False),
        (READ, RateLimitError("x", response=ErrorResponse(status_code=429)), True),
        (READ, NotFoundError("x", response=ErrorResponse(status_code=404)), False),
        (READ, BadRequestError("x", response=ErrorResponse(status_code=400)), False),
        (WRITE, TransportError("x"), False),
        (WRITE, ServerError("x", response=ErrorResponse(status_code=503)), False),
        (WRITE, RateLimitError("x", response=ErrorResponse(status_code=429)), True),
        (None, TransportError("x"), False),
        (None, RateLimitError("x", response=ErrorResponse(status_code=429)), True),
    ],
)
def test_decide(operation: Operation | None, error: BacsyError, expected: bool) -> None:
    assert decide(POLICY, operation, error, 1).retry is expected


def test_no_retry_after_last_attempt() -> None:
    assert not decide(POLICY, READ, TransportError("x"), POLICY.max_attempts).retry


def test_writes_can_opt_out_of_429_retries() -> None:
    policy = RetryPolicy(retry_writes_on_429=False)

    assert not decide(
        policy, WRITE, RateLimitError("x", response=ErrorResponse(status_code=429)), 1
    ).retry
    assert decide(
        policy, READ, RateLimitError("x", response=ErrorResponse(status_code=429)), 1
    ).retry


def test_transport_retries_can_be_disabled() -> None:
    policy = RetryPolicy(retry_transport_errors=False)

    assert not decide(policy, READ, TransportError("x"), 1).retry


def test_backoff_grows_and_caps() -> None:
    policy = RetryPolicy(base_delay=1, multiplier=2, max_delay=5, jitter=False)

    assert [backoff_delay(policy, n) for n in (1, 2, 3, 4)] == [1, 2, 4, 5]


def test_jitter_scales_and_floor_applies() -> None:
    policy = RetryPolicy(base_delay=4, jitter=True)

    assert backoff_delay(policy, 1, rng=lambda: 0.25) == 1.0
    assert backoff_delay(policy, 1, floor=2.0, rng=lambda: 0.25) == 2.0


def test_rate_limit_delay_has_a_floor() -> None:
    policy = RetryPolicy(base_delay=0.1, jitter=True, rate_limit_floor=1.5)

    decision = decide(
        policy,
        READ,
        RateLimitError("x", response=ErrorResponse(status_code=429)),
        1,
        rng=lambda: 0.0,
    )
    assert decision.delay == 1.5
