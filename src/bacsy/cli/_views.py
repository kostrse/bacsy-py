"""View models shared by the table and the JSON renderings of accounts and tokens.

Every displayed value of a token is computed once here, so its table row and JSON
object agree.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from itertools import groupby
from typing import TYPE_CHECKING

from bacsy.cli._format import (
    DAY,
    Cell,
    Section,
    Style,
    days_left,
    format_iso,
    format_local,
)
from bacsy.exceptions import TokenRefreshReason

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence
    from datetime import tzinfo

    from bacsy.accounts import Account, TokenRecord, VerifyResult
    from bacsy.auth import RefreshToken
    from bacsy.cli._console import Console, Json
    from bacsy.cli._format import Align

TOKEN_HEADERS = ("token", "id", "scope", "valid until", "days", "status")
TOKEN_ALIGN: tuple[Align, ...] = ("<", "<", "<", "<", ">", "<")
NO_TOKENS = "(no tokens)"
"""Note shown in place of the rows of an account that holds no tokens."""

REVOKE_NOTE = "removing tokens here does not revoke them; delete them in the BCS web terminal too"

EXPIRING_WITHIN_DAYS = 7
EXPIRING_WITHIN_SECONDS = EXPIRING_WITHIN_DAYS * DAY
"""Remaining lifetime below which a token's status is `EXPIRING`."""


def account_key(name: str) -> tuple[str, str]:
    """Return a sort key ordering accounts by case-insensitive name, then by exact name."""
    return (name.casefold(), name)


def token_key(token: RefreshToken) -> tuple[int, int, str]:
    """Return a sort key ordering tokens read before write, then by nearest expiry.

    Privilege is measured by the number of scopes a token serves; the token ID breaks
    ties so that the order is stable.
    """
    return (len(token.scope.capabilities), token.expires_at, token.token_id)


def account_heading(name: str, label: str | None) -> list[Cell]:
    """Return the heading cells of one account: its name, then its label when set."""
    if label is None:
        return [Cell(name, Style.BOLD)]
    return [Cell(name, Style.BOLD), Cell(f" \u00b7 {label}", Style.DIM)]


def token_sections(rows: Iterable[tuple[TokenView, list[Cell]]]) -> list[Section]:
    """Return one section per account from rows already ordered by account."""
    return [
        Section(heading=account_heading(*key), rows=[row for _, row in group])
        for key, group in groupby(rows, key=lambda pair: (pair[0].account, pair[0].label))
    ]


class Status(StrEnum):
    """Token status vocabulary shared by the `STATUS` and `LIVE` columns.

    `STATUS` is determined offline from the token's expiry and the dead mark on its
    record; `LIVE` is the token endpoint's answer from `tokens verify`. `EXPIRING` is
    reported only offline and `ERROR` only by a live check.
    """

    OK = "ok"
    EXPIRING = "expiring"
    """Valid, but for fewer than `EXPIRING_WITHIN_DAYS` days."""
    EXPIRED = "expired"
    REVOKED = "revoked"
    SCOPE_MISMATCH = "scope-mismatch"
    INVALID = "invalid"
    ERROR = "error"
    """The check failed (network, server); says nothing about the token."""

    @property
    def dead(self) -> bool:
        """Whether the token can no longer be exchanged."""
        return self in _DEAD

    @classmethod
    def of_reason(cls, reason: TokenRefreshReason) -> Status:
        """Return the status a token endpoint rejection reason maps to."""
        return _BY_REASON[reason]

    @classmethod
    def of_record(cls, record: TokenRecord, now: float) -> Status:
        """Return the offline status of a stored record."""
        if record.dead is not None:
            return cls.of_reason(record.dead.reason)
        token = record.token
        if token.is_expired(now):
            return cls.EXPIRED
        if token.expires_in(now) < EXPIRING_WITHIN_SECONDS:
            return cls.EXPIRING
        return cls.OK

    @classmethod
    def of_result(cls, result: VerifyResult) -> Status:
        """Return the live status of one `tokens verify` result."""
        if result.error is not None:
            return cls.ERROR
        if result.reason is None:
            return cls.OK
        return cls.of_reason(result.reason)


_BY_REASON: dict[TokenRefreshReason, Status] = {
    TokenRefreshReason.EXPIRED: Status.EXPIRED,
    TokenRefreshReason.REVOKED: Status.REVOKED,
    TokenRefreshReason.SCOPE_MISMATCH: Status.SCOPE_MISMATCH,
    TokenRefreshReason.INVALID: Status.INVALID,
    TokenRefreshReason.UNKNOWN: Status.ERROR,
}

_DEAD = frozenset({Status.EXPIRED, Status.REVOKED, Status.SCOPE_MISMATCH, Status.INVALID})

STATUS_STYLES: dict[Status, Style] = {
    Status.OK: Style.GREEN,
    Status.EXPIRING: Style.YELLOW,
    Status.EXPIRED: Style.RED,
    Status.REVOKED: Style.RED,
    Status.SCOPE_MISMATCH: Style.RED,
    Status.INVALID: Style.RED,
    Status.ERROR: Style.RED,
}


@dataclass(frozen=True, slots=True, kw_only=True)
class TokenView:
    """One stored token with every displayed value already formatted."""

    account: str
    label: str | None
    scope: str
    short: str
    token_id: str
    sid: str
    valid_until: str
    days: int
    status: Status
    issued_at: str
    expires_at: str
    added_at: str

    @classmethod
    def build(
        cls, account: Account, record: TokenRecord, *, now: float, tz: tzinfo | None
    ) -> TokenView:
        token = record.token
        return cls(
            account=account.name,
            label=account.label,
            scope=token.scope.short_name,
            short=token.short,
            token_id=token.token_id,
            sid=token.sid,
            valid_until=format_local(token.expires_at, tz),
            days=days_left(token.expires_at, now),
            status=Status.of_record(record, now),
            issued_at=format_iso(token.issued_at, tz),
            expires_at=format_iso(token.expires_at, tz),
            added_at=format_iso(record.added_at, tz),
        )

    def row(self) -> list[Cell]:
        return [
            Cell(self.short),
            Cell(self.token_id),
            Cell(self.scope),
            Cell(self.valid_until),
            Cell(str(self.days)),
            Cell(self.status.value, STATUS_STYLES[self.status]),
        ]

    def to_json(self) -> dict[str, Json]:
        return {
            "token_id": self.token_id,
            "scope": self.scope,
            "short": self.short,
            "sid": self.sid,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "added_at": self.added_at,
            "days_left": self.days,
            "status": self.status.value,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class AccountView:
    """One account and its tokens, read before write and nearest expiry first."""

    name: str
    label: str | None
    agreement_id: str | None
    tokens: tuple[TokenView, ...]

    @classmethod
    def build(cls, account: Account, *, now: float, tz: tzinfo | None) -> AccountView:
        records = sorted(account.tokens, key=lambda r: token_key(r.token))
        return cls(
            name=account.name,
            label=account.label,
            agreement_id=account.agreement_id,
            tokens=tuple(TokenView.build(account, r, now=now, tz=tz) for r in records),
        )

    def section(self) -> Section:
        """Return the account's heading and the rows of its tokens."""
        return Section(
            heading=account_heading(self.name, self.label),
            rows=[token.row() for token in self.tokens],
            note=NO_TOKENS,
        )

    def to_json(self) -> dict[str, Json]:
        return {
            "name": self.name,
            "label": self.label,
            "agreement_id": self.agreement_id,
            "tokens": [token.to_json() for token in self.tokens],
        }


def render_accounts(console: Console, accounts: Sequence[AccountView]) -> None:
    """Write the grouped token table of `accounts`, or a line saying there are none."""
    if not accounts:
        console.result("no accounts saved")
        return
    console.sections(TOKEN_HEADERS, [account.section() for account in accounts], align=TOKEN_ALIGN)


@dataclass(frozen=True, slots=True, kw_only=True)
class VerifiedToken:
    """A token together with the token endpoint's verdict on it."""

    view: TokenView
    live: Status
    error: str | None

    def row(self) -> list[Cell]:
        return [*self.view.row(), Cell(self.live.value, STATUS_STYLES[self.live])]

    def to_json(self) -> dict[str, Json]:
        return {
            "account": self.view.account,
            "token": self.view.to_json(),
            "live": self.live.value,
            "error": self.error,
        }
