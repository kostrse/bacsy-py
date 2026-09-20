"""Builders for stored credential values: refresh tokens wrapped in token records."""

from __future__ import annotations

from typing import TYPE_CHECKING

from bacsy.accounts import TokenRecord
from bacsy.auth import RefreshToken, TokenScope
from tests.auth.fakes import DAY, make_refresh_token

if TYPE_CHECKING:
    from bacsy.accounts import TokenStatus

NOW = 1_000_000


def make_token(
    *,
    scope: TokenScope = TokenScope.READ,
    exp: int = NOW + 30 * DAY,
    iat: int | None = None,
    agreement_id: str | None = None,
    sid: str | None = None,
    token_id: str | None = None,
    marker: str = "",
) -> RefreshToken:
    """A parsed refresh token, expiring 30 days after `NOW` unless `exp` is given."""
    extra = {} if agreement_id is None else {"agreement_id": agreement_id}
    value = make_refresh_token(
        scope=scope, exp=exp, iat=iat, sid=sid, token_id=token_id, marker=marker, **extra
    )
    return RefreshToken.parse(value)


def make_record(
    token: RefreshToken | None = None,
    *,
    added_at: int = NOW,
    dead: TokenStatus | None = None,
) -> TokenRecord:
    """A stored record around a token, live unless ``dead`` is given."""
    return TokenRecord(
        token=token if token is not None else make_token(), added_at=added_at, dead=dead
    )
