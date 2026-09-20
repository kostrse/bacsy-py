"""The Account, TokenRecord, TokenStatus and VerifyResult value types."""

from __future__ import annotations

import pytest

from bacsy.accounts import Account, TokenStatus
from bacsy.exceptions import AccountError, TokenRefreshReason
from tests.accounts.fakes import NOW, make_record, make_token
from tests.auth.fakes import OTHER_AGREEMENT


def test_account_rejects_tokens_of_different_brokerage_accounts() -> None:
    with pytest.raises(AccountError, match="tokens 1 and 2") as info:
        Account(
            name="x",
            tokens=(make_record(), make_record(make_token(agreement_id=OTHER_AGREEMENT))),
        )

    assert OTHER_AGREEMENT not in str(info.value)
    assert info.value.name == "x"


def test_agreement_id_is_none_for_an_empty_account() -> None:
    record = make_record()

    assert Account(name="x").agreement_id is None
    assert Account(name="x", tokens=(record,)).agreement_id == record.token.agreement_id


def test_account_repr_hides_token_values() -> None:
    record = make_record()

    assert record.token.value not in repr(Account(name="x", tokens=(record,)))
    assert record.token.value not in repr(record)


def test_live_tokens_skip_records_marked_dead() -> None:
    live = make_record(make_token(sid="live"))
    dead = make_record(
        make_token(sid="dead"), dead=TokenStatus(reason=TokenRefreshReason.REVOKED, at=NOW)
    )
    account = Account(name="x", tokens=(live, dead))

    assert account.live_tokens == (live.token,)
    assert live.live
    assert not dead.live


def test_token_status_round_trips_through_a_dict() -> None:
    status = TokenStatus(reason=TokenRefreshReason.EXPIRED, at=NOW)

    assert TokenStatus.from_dict(status.to_dict()) == status
    assert status.to_dict()["at"] == NOW


@pytest.mark.parametrize(
    "data",
    [{"reason": "expired"}, {"at": 1}, {"reason": 1, "at": 1}, {"reason": "expired", "at": True}],
)
def test_a_malformed_token_status_is_rejected(data: dict[str, object]) -> None:
    with pytest.raises(ValueError, match="malformed token status entry"):
        TokenStatus.from_dict(data)


def test_a_fractional_recorded_time_is_narrowed_to_seconds() -> None:
    assert TokenStatus.from_dict({"reason": "revoked", "at": 5.9}).at == 5
