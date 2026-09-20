"""The view models: the status vocabulary shared by the STATUS and LIVE columns."""

from __future__ import annotations

import pytest

from bacsy.accounts import Account, TokenStatus, VerifyResult
from bacsy.cli._views import EXPIRING_WITHIN_SECONDS, STATUS_STYLES, Status
from bacsy.exceptions import BacsyError, TokenRefreshReason
from tests.accounts.fakes import make_record, make_token

NOW = 1_800_000_000
DAY = 86400


def _result(
    reason: TokenRefreshReason | None = None, error: BacsyError | None = None
) -> VerifyResult:
    token = make_token(exp=NOW + 30 * DAY, sid="s")
    return VerifyResult(account=Account(name="main"), token=token, reason=reason, error=error)


def test_of_record_reads_expiry_then_the_dead_mark() -> None:
    assert Status.of_record(make_record(make_token(exp=NOW + 8 * DAY)), NOW) is Status.OK
    assert Status.of_record(make_record(make_token(exp=NOW + 6 * DAY)), NOW) is Status.EXPIRING
    assert Status.of_record(make_record(make_token(exp=NOW - 1)), NOW) is Status.EXPIRED

    revoked = make_record(
        make_token(exp=NOW + 8 * DAY),
        dead=TokenStatus(reason=TokenRefreshReason.REVOKED, at=NOW),
    )
    assert Status.of_record(revoked, NOW) is Status.REVOKED  # the mark wins over the expiry


def test_expiring_threshold_is_exact() -> None:
    at_threshold = make_record(make_token(exp=NOW + int(EXPIRING_WITHIN_SECONDS)))
    inside = make_record(make_token(exp=NOW + int(EXPIRING_WITHIN_SECONDS) - 1))

    assert Status.of_record(at_threshold, NOW) is Status.OK
    assert Status.of_record(inside, NOW) is Status.EXPIRING


def test_of_result_maps_every_reason_and_keeps_errors_apart() -> None:
    assert Status.of_result(_result()) is Status.OK
    assert Status.of_result(_result(error=BacsyError("down"))) is Status.ERROR
    assert Status.of_result(_result(TokenRefreshReason.UNKNOWN)) is Status.ERROR
    assert Status.of_result(_result(TokenRefreshReason.EXPIRED)) is Status.EXPIRED
    assert Status.of_result(_result(TokenRefreshReason.REVOKED)) is Status.REVOKED
    assert Status.of_result(_result(TokenRefreshReason.INVALID)) is Status.INVALID
    assert Status.of_result(_result(TokenRefreshReason.SCOPE_MISMATCH)) is Status.SCOPE_MISMATCH


@pytest.mark.parametrize("reason", list(TokenRefreshReason))
def test_a_rejection_is_named_the_same_stored_as_live(reason: TokenRefreshReason) -> None:
    """The STATUS column of a marked record reads exactly as the LIVE column that marked it."""
    record = make_record(make_token(exp=NOW + 30 * DAY), dead=TokenStatus(reason=reason, at=NOW))

    assert Status.of_record(record, NOW) is Status.of_result(_result(reason))


def test_dead_covers_the_permanent_refusals_only() -> None:
    dead = {status for status in Status if status.dead}

    assert dead == {Status.EXPIRED, Status.REVOKED, Status.SCOPE_MISMATCH, Status.INVALID}
    assert not Status.EXPIRING.dead  # still usable, only close to its expiry
    assert not Status.ERROR.dead  # the check failed, the token may be fine


def test_every_status_has_a_style() -> None:
    assert set(STATUS_STYLES) == set(Status)
