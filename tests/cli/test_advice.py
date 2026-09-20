"""The one hint a run may print: which one wins, and how it reads."""

from __future__ import annotations

import io

import pytest

from bacsy.accounts import Account, TokenRecord, TokenStatus
from bacsy.auth import RefreshToken
from bacsy.cli._advice import Advice, AdviceKind, advise, advise_stored, render_advice
from bacsy.cli._console import Console
from bacsy.cli._views import Status
from bacsy.exceptions import TokenRefreshReason
from tests.auth.fakes import DAY, make_refresh_token

NOW = 1_800_000_000

OK = Status.OK
EXPIRING = Status.EXPIRING
REVOKED = Status.REVOKED
EXPIRED = Status.EXPIRED


def test_nothing_saved_asks_for_the_whole_setup() -> None:
    assert advise([]) == Advice(kind=AdviceKind.SETUP)


@pytest.mark.parametrize(
    ("statuses", "expected"),
    [
        ((), AdviceKind.ADD_FIRST),
        ((REVOKED, EXPIRED), AdviceKind.ADD_FRESH),
        ((EXPIRING,), AdviceKind.ADD_SOON),
        ((EXPIRING, REVOKED), AdviceKind.ADD_SOON),
        ((OK, REVOKED), AdviceKind.PRUNE),
        ((OK, EXPIRING, REVOKED), AdviceKind.PRUNE),
        ((OK,), None),
        ((OK, EXPIRING), None),
        ((Status.ERROR,), None),
    ],
)
def test_what_one_account_needs(statuses: tuple[Status, ...], expected: AdviceKind | None) -> None:
    advice = advise([("a", statuses)])

    assert (advice.kind if advice is not None else None) == expected


def test_the_most_pressing_account_wins_and_only_it_is_named() -> None:
    advice = advise(
        [
            ("tidy", (OK, REVOKED)),  # PRUNE
            ("empty", ()),  # ADD_FIRST
            ("soon", (EXPIRING,)),  # ADD_SOON
            ("stopped", (REVOKED,)),  # ADD_FRESH
        ]
    )

    assert advice == Advice(kind=AdviceKind.ADD_FRESH, account="stopped", dead_tokens=2)


def test_the_first_account_needing_the_winning_advice_is_named() -> None:
    advice = advise([("healthy", (OK,)), ("a", ()), ("b", ())])

    assert advice is not None
    assert advice.account == "a"


def test_advise_stored_reads_the_offline_status_of_each_record() -> None:
    def record(days: int, *, dead: bool = False) -> TokenRecord:
        token = RefreshToken.parse(make_refresh_token(exp=NOW + days * DAY))
        status = TokenStatus(reason=TokenRefreshReason.REVOKED, at=NOW) if dead else None
        return TokenRecord(token=token, added_at=NOW, dead=status)

    accounts = [
        Account(name="main", tokens=(record(60), record(60, dead=True))),
        Account(name="spare"),
    ]

    advice = advise_stored(accounts, now=NOW)

    assert advice == Advice(kind=AdviceKind.PRUNE, account="main", dead_tokens=1)


@pytest.mark.parametrize(
    ("advice", "expected"),
    [
        (None, ""),
        (
            Advice(kind=AdviceKind.SETUP),
            "hint: create an account, then add an API token issued in the BCS web terminal:\n"
            "        bacsy accounts add main\n"
            "        bacsy tokens add main\n",
        ),
        (
            Advice(kind=AdviceKind.ADD_FRESH, account="main"),
            "warning: account 'main' has no usable token\n"
            "         issue an API token in the BCS web terminal and run: "
            "bacsy tokens add main\n",
        ),
        (
            Advice(kind=AdviceKind.ADD_SOON, account="main"),
            "warning: every token of account 'main' expires within 7 days\n"
            "         issue a new one in the web terminal and run: "
            "bacsy tokens add main\n",
        ),
        (
            Advice(kind=AdviceKind.PRUNE, account="main", dead_tokens=1),
            "hint: 1 token is expired or revoked; run: bacsy tokens prune\n",
        ),
        (
            Advice(kind=AdviceKind.PRUNE, account="main", dead_tokens=2),
            "hint: 2 tokens are expired or revoked; run: bacsy tokens prune\n",
        ),
        (
            Advice(kind=AdviceKind.ADD_FIRST, account="spare"),
            "hint: account 'spare' holds no tokens yet; run: bacsy tokens add spare\n",
        ),
    ],
)
def test_render_advice(advice: Advice | None, expected: str) -> None:
    out, err = io.StringIO(), io.StringIO()

    render_advice(Console(out, err, color_out=False, color_err=False), advice)

    assert err.getvalue() == expected
    assert out.getvalue() == ""
