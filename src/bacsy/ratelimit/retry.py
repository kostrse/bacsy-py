"""Decide whether a failed request may be retried, and how long to wait first."""

from __future__ import annotations

import random
from typing import TYPE_CHECKING, NamedTuple, Protocol

from bacsy.exceptions import ApiError, RateLimitError, ServerError, TransportError

if TYPE_CHECKING:
    from collections.abc import Callable

    from bacsy.config import RetryPolicy
    from bacsy.routes import Operation


class BackoffPolicy(Protocol):
    """The fields `backoff_delay` reads.

    `RetryPolicy` and `ReconnectPolicy` satisfy it.
    """

    @property
    def base_delay(self) -> float: ...
    @property
    def max_delay(self) -> float: ...
    @property
    def multiplier(self) -> float: ...
    @property
    def jitter(self) -> bool: ...


class RetryDecision(NamedTuple):
    """Whether to retry and how long to wait first."""

    retry: bool
    delay: float


NO_RETRY = RetryDecision(retry=False, delay=0.0)


def backoff_delay(
    policy: BackoffPolicy,
    attempt: int,
    *,
    floor: float = 0.0,
    rng: Callable[[], float] = random.random,
) -> float:
    """Return the exponential backoff delay for the `attempt`-th failure (1-based).

    The delay is `base_delay * multiplier ** (attempt - 1)`, capped at `max_delay`.
    With `jitter` enabled it is multiplied by `rng()`, expected to be uniform in
    `[0, 1)`. The result is never below `floor`.
    """
    delay = min(policy.max_delay, policy.base_delay * policy.multiplier ** (attempt - 1))
    if policy.jitter:
        delay *= rng()
    return max(floor, delay)


def decide(
    policy: RetryPolicy,
    operation: Operation | None,
    error: Exception,
    attempt: int,
    *,
    rng: Callable[[], float] = random.random,
) -> RetryDecision:
    """Decide whether `error` after `attempt` attempts of `operation` warrants a retry.

    Nothing is retried once `attempt` reaches `policy.max_attempts`. Idempotent
    operations are retried after transport failures (unless disabled by the policy) and
    after HTTP errors whose status is in `policy.retry_statuses`. A `RateLimitError`
    whose status is in `policy.retry_statuses` is retried for every operation, with the
    delay floored at `policy.rate_limit_floor`, unless the operation is not idempotent
    and `policy.retry_writes_on_429` is off. Nothing else is retried. A `None` operation
    is treated as not idempotent.
    """
    if attempt >= policy.max_attempts:
        return NO_RETRY
    idempotent = operation.idempotent if operation is not None else False

    if isinstance(error, RateLimitError):
        if not idempotent and not policy.retry_writes_on_429:
            return NO_RETRY
        if error.response is None or error.response.status_code not in policy.retry_statuses:
            return NO_RETRY
        return RetryDecision(
            retry=True, delay=backoff_delay(policy, attempt, floor=policy.rate_limit_floor, rng=rng)
        )
    if not idempotent:
        return NO_RETRY
    if isinstance(error, ServerError | ApiError):
        if error.response is not None and error.response.status_code in policy.retry_statuses:
            return RetryDecision(retry=True, delay=backoff_delay(policy, attempt, rng=rng))
        return NO_RETRY
    if isinstance(error, TransportError) and error.transient:
        if not policy.retry_transport_errors:
            return NO_RETRY
        return RetryDecision(retry=True, delay=backoff_delay(policy, attempt, rng=rng))
    return NO_RETRY
