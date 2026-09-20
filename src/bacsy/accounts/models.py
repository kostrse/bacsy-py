"""Value types of the credential layer.

An `Account` is a named alias for one brokerage account and holds any number of refresh
tokens. Each token is held as a `TokenRecord`: the token with its decoded claims, when it
was added, and whether the token endpoint has declared it dead. Within an account a token
is identified by `RefreshToken.token_id`, which is unique per account.

Timestamps are whole Unix seconds.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, override

from bacsy.exceptions import AccountError, TokenRefreshReason

if TYPE_CHECKING:
    from collections.abc import Mapping

    from bacsy.auth.tokens import RefreshToken
    from bacsy.exceptions import BacsyError


@dataclass(frozen=True, slots=True, kw_only=True)
class TokenStatus:
    """Why and when a token was marked dead.

    Attributes:
        reason: The rejection reported by the token endpoint.
        at: Unix timestamp of when the mark was recorded.
    """

    reason: TokenRefreshReason
    at: int

    def to_dict(self) -> dict[str, str | int]:
        """Return the JSON-serialisable form."""
        return {"reason": self.reason.value, "at": self.at}

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> TokenStatus:
        """Build a status from its dictionary form.

        Raises:
            ValueError: ``data`` lacks a field or holds one of the wrong type or value.
        """
        reason = data.get("reason")
        at = data.get("at")
        if not isinstance(reason, str) or isinstance(at, bool) or not isinstance(at, int | float):
            msg = "malformed token status entry"
            raise ValueError(msg)
        return cls(reason=TokenRefreshReason(reason), at=int(at))


@dataclass(frozen=True, slots=True, kw_only=True)
class TokenRecord:
    """One stored refresh token: the token, when it was added, and its status.

    Attributes:
        token: The refresh token and the claims decoded from it.
        added_at: Unix timestamp of when the token was added.
        dead: The rejection that marked the token dead, or ``None`` while it is not
            marked.
    """

    token: RefreshToken
    added_at: int
    dead: TokenStatus | None = None

    @property
    def live(self) -> bool:
        """Whether the token has not been marked dead."""
        return self.dead is None

    @override
    def __repr__(self) -> str:
        return f"TokenRecord(token={self.token!r}, added_at={self.added_at!r}, dead={self.dead!r})"


@dataclass(frozen=True, slots=True, kw_only=True)
class Account:
    """A named brokerage account and the refresh tokens stored for it.

    Raises:
        AccountError: on construction, when the tokens were issued for different
            brokerage accounts or two of them share a token id.
    """

    name: str
    label: str | None = None
    tokens: tuple[TokenRecord, ...] = ()

    def __post_init__(self) -> None:
        agreements = {record.token.agreement_id for record in self.tokens}
        if len(agreements) > 1:
            first = self.tokens[0].token.agreement_id
            other = next(i for i, r in enumerate(self.tokens) if r.token.agreement_id != first)
            msg = (
                f"account {self.name!r}: tokens 1 and {other + 1} were issued for different "
                "brokerage accounts"
            )
            raise AccountError(msg, name=self.name)
        seen: dict[str, int] = {}
        for index, record in enumerate(self.tokens, start=1):
            token_id = record.token.token_id
            if token_id in seen:
                msg = (
                    f"account {self.name!r}: tokens {seen[token_id]} and {index} share the "
                    f"token id {token_id!r}"
                )
                raise AccountError(msg, name=self.name)
            seen[token_id] = index

    @property
    def agreement_id(self) -> str | None:
        """The brokerage account identifier shared by every token, or ``None`` when the
        account holds no tokens."""
        return self.tokens[0].token.agreement_id if self.tokens else None

    @property
    def live_tokens(self) -> tuple[RefreshToken, ...]:
        """The tokens not marked dead, in stored order."""
        return tuple(record.token for record in self.tokens if record.live)

    @override
    def __repr__(self) -> str:
        return f"Account(name={self.name!r}, label={self.label!r}, tokens={self.tokens!r})"


@dataclass(frozen=True, slots=True, kw_only=True)
class VerifyResult:
    """Outcome of checking one token against the token endpoint.

    Attributes:
        account: The account the token is stored under.
        token: The token that was checked.
        reason: Why the endpoint rejected the token, or ``None`` if it did not.
        error: A failure that did not classify the token, such as a transport error.
    """

    account: Account
    token: RefreshToken
    reason: TokenRefreshReason | None = None
    error: BacsyError | None = None

    @property
    def ok(self) -> bool:
        """Whether the endpoint accepted the token."""
        return self.reason is None and self.error is None
