"""What to do next about the stored refresh tokens.

`advise` reduces the token statuses of every account to at most one `Advice`, the most
pressing kind any of them needs; `render_advice` writes it to a `Console`.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from bacsy.cli._format import plural
from bacsy.cli._views import EXPIRING_WITHIN_DAYS, Status

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from bacsy.accounts import Account
    from bacsy.cli._console import Console
    from bacsy.cli._views import VerifiedToken


class AdviceKind(StrEnum):
    """What the stored accounts need.

    Members are declared most pressing first: `advise` returns the first kind that any
    account needs, so the declaration order is the priority order.
    """

    SETUP = "setup"
    """Nothing is saved yet."""
    ADD_FRESH = "add-fresh"
    """Every token of the account is dead, so it cannot mint access tokens."""
    ADD_SOON = "add-soon"
    """Every usable token expires within `EXPIRING_WITHIN_DAYS`."""
    PRUNE = "prune"
    """Dead tokens are stored beside healthy ones."""
    ADD_FIRST = "add-first"
    """The account holds no tokens."""


@dataclass(frozen=True, slots=True, kw_only=True)
class Advice:
    """A suggested next action."""

    kind: AdviceKind
    account: str = ""
    """The account the suggestion concerns; empty for `AdviceKind.SETUP`."""
    dead_tokens: int = 0
    """Dead tokens across every account; rendered only for `AdviceKind.PRUNE`."""


def _kind_of(statuses: Sequence[Status]) -> AdviceKind | None:
    """Return what the account holding `statuses` needs, or `None` when it needs nothing.

    A status is usable when it is not `Status.dead`, and healthy when it is usable and
    not `Status.EXPIRING`. `Status.ERROR` is neither dead nor expiring, so a token whose
    check failed counts as healthy.
    """
    if not statuses:
        return AdviceKind.ADD_FIRST
    usable = [status for status in statuses if not status.dead]
    if not usable:
        return AdviceKind.ADD_FRESH
    if all(status is Status.EXPIRING for status in usable):
        return AdviceKind.ADD_SOON
    if len(usable) < len(statuses):
        return AdviceKind.PRUNE
    return None


def advise(accounts: Iterable[tuple[str, Sequence[Status]]]) -> Advice | None:
    """Return the most pressing advice for `accounts`, or `None` when none is needed.

    Each item pairs an account name with the statuses of the tokens it holds. The result
    names the first account, in iteration order, that needs the winning `AdviceKind`. An
    empty `accounts` yields `AdviceKind.SETUP`.
    """
    needs: dict[AdviceKind, str] = {}
    dead = 0
    empty = True
    for name, statuses in accounts:
        empty = False
        dead += sum(1 for status in statuses if status.dead)
        kind = _kind_of(statuses)
        if kind is not None:
            needs.setdefault(kind, name)
    if empty:
        return Advice(kind=AdviceKind.SETUP)
    for kind in AdviceKind:
        account = needs.get(kind)
        if account is not None:
            return Advice(kind=kind, account=account, dead_tokens=dead)
    return None


def advise_stored(accounts: Iterable[Account], *, now: float) -> Advice | None:
    """Return the advice for `accounts`, from their tokens' offline status at `now`."""
    return advise(
        (account.name, [Status.of_record(record, now) for record in account.tokens])
        for account in accounts
    )


def advise_verified(items: Iterable[VerifiedToken]) -> Advice | None:
    """Return the advice for tokens checked against the token endpoint.

    A token is classified by its live verdict unless that verdict is `Status.OK`, in
    which case its stored status is used, since a live verdict never reports
    `Status.EXPIRING`. Tokens are grouped by the account they are stored under.
    """
    by_account: dict[str, list[Status]] = {}
    for item in items:
        effective = item.view.status if item.live is Status.OK else item.live
        by_account.setdefault(item.view.account, []).append(effective)
    return advise(by_account.items())


def render_advice(console: Console, advice: Advice | None) -> None:
    """Write `advice` to `console`, or nothing when it is `None`.

    `AdviceKind.ADD_FRESH` and `AdviceKind.ADD_SOON` are written as warnings and the
    remaining kinds as hints. Each is set apart from preceding output by a blank line.
    """
    if advice is None:
        return
    match advice.kind:
        case AdviceKind.SETUP:
            console.hint(
                "create an account, then add an API token issued in the BCS web terminal:\n"
                "  bacsy accounts add main\n"
                "  bacsy tokens add main",
                block=True,
            )
        case AdviceKind.ADD_FRESH:
            console.warning(
                f"account {advice.account!r} has no usable token\n"
                "issue an API token in the BCS web terminal and run: "
                f"bacsy tokens add {advice.account}",
                block=True,
            )
        case AdviceKind.ADD_SOON:
            console.warning(
                f"every token of account {advice.account!r} expires within "
                f"{plural(EXPIRING_WITHIN_DAYS, 'day')}\n"
                "issue a new one in the web terminal and run: "
                f"bacsy tokens add {advice.account}",
                block=True,
            )
        case AdviceKind.PRUNE:
            console.hint(
                f"{plural(advice.dead_tokens, 'token is', 'tokens are')} expired or "
                "revoked; run: bacsy tokens prune",
                block=True,
            )
        case AdviceKind.ADD_FIRST:
            console.hint(
                f"account {advice.account!r} holds no tokens yet; "
                f"run: bacsy tokens add {advice.account}",
                block=True,
            )
