"""Token value types: scopes, refresh tokens, access tokens and token selection.

A BCS refresh token is a JWT whose claims carry the scope, the expiry, a session id, and
the brokerage account the token belongs to. `RefreshToken.parse` decodes those claims
once and, in the same pass, computes the display label and, when the token has no
`jtiTradeApi` claim, the derived token id. `AccessToken` is the token minted from a
refresh token at the token endpoint. JWT decoding lives in `bacsy.auth._jwt`; the
meaning of the claims lives here.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, override

from bacsy.auth._jwt import decode_jwt_claims, nested_str_claim, str_claim, timestamp_claim
from bacsy.exceptions import InvalidTokenError

if TYPE_CHECKING:
    from collections.abc import Collection, Iterable

    from bacsy.routes import ScopeName


class TokenScope(StrEnum):
    """The Keycloak client a refresh token was issued for.

    The value is the `client_id` sent to the token endpoint and equals the token's `azp`
    claim; the endpoint rejects any other pairing.
    """

    READ = "trade-api-read"
    WRITE = "trade-api-write"

    @classmethod
    def parse(cls, value: TokenScope | str) -> TokenScope:
        """Return the scope named by a member, its value, or `read`, `ro`, `write`, `rw`.

        Matching is case-insensitive and ignores surrounding whitespace.

        Raises:
            InvalidTokenError: `value` names no scope.
        """
        if isinstance(value, TokenScope):
            return value
        normalized = value.strip().lower()
        match normalized:
            case "read" | "ro" | "trade-api-read":
                return cls.READ
            case "write" | "rw" | "trade-api-write":
                return cls.WRITE
            case _:
                msg = f"unknown token scope {value!r}; expected 'read' or 'write'"
                raise InvalidTokenError(msg)

    @property
    def short_name(self) -> ScopeName:
        """`read` or `write`."""
        return "read" if self is TokenScope.READ else "write"

    @property
    def capabilities(self) -> frozenset[TokenScope]:
        """Scopes a token of this kind can serve; a write token also serves reads."""
        if self is TokenScope.WRITE:
            return frozenset({TokenScope.READ, TokenScope.WRITE})
        return frozenset({TokenScope.READ})


def short_token(value: str) -> str:
    """Return the redacted form the BCS web terminal shows, e.g. `eyJh**********lCGA`.

    The result is a display label and does not identify a token: the first four
    characters are the same for every JWT. Values shorter than 12 characters are fully
    redacted.
    """
    value = value.strip()
    if len(value) < 12:
        return "**********"
    return f"{value[:4]}**********{value[-4:]}"


def derived_token_id(value: str) -> str:
    """Return the id for a token that carries no `jtiTradeApi` claim.

    The id is the first eight hex digits of the SHA-256 of the token string. It is stable
    for a given token, distinguishable from the mixed-case ids the web terminal issues,
    and reveals nothing about the token.
    """
    return hashlib.sha256(value.strip().encode()).hexdigest()[:8]


@dataclass(frozen=True, slots=True, kw_only=True)
class RefreshToken:
    """A refresh token and the claims decoded from it.

    Parsing populates the token metadata, identifier, and redacted display label, which
    are stored as immutable fields. `repr()` omits the token value and the account.

    Attributes:
        value: The token itself; a long-lived credential.
        short: The redacted display label from `short_token`. It identifies nothing.
        scope: The client the token was issued for, from the `azp` claim.
        issued_at: Unix timestamp of issue (`iat`).
        expires_at: Unix timestamp from which the endpoint rejects the token (`exp`);
            90 days after `issued_at`.
        sid: The `sid` claim; unique per issued token and unchanged by rotation.
        agreement_id: The brokerage account the token belongs to, from the last segment
            of `sub`. An account identifier; do not log or publish it.
        token_id: The id the token is referred to by: the `jtiTradeApi` claim, which is
            the `ID` the web terminal lists, or `derived_token_id` when that claim is
            absent.
    """

    value: str
    short: str
    scope: TokenScope
    issued_at: int
    expires_at: int
    sid: str
    agreement_id: str
    token_id: str

    @classmethod
    def parse(cls, value: str) -> RefreshToken:
        """Decode a refresh token.

        Surrounding whitespace is stripped from `value`.

        Raises:
            InvalidTokenError: `value` is not a JWT, is an access token, has an
                unexpected `typ`, or lacks a required claim.
        """
        claims = decode_jwt_claims(value)
        typ = claims.get("typ")
        if typ == "Bearer":
            msg = "this is an access token, not a refresh token"
            raise InvalidTokenError(msg)
        if typ not in ("Refresh", "Offline"):
            msg = f"unexpected JWT type {typ!r}; expected a refresh token"
            raise InvalidTokenError(msg)
        subject = str_claim(claims, "sub")
        web_id = nested_str_claim(claims, "extra_claims", "external", "jtiTradeApi")
        value = value.strip()
        return cls(
            value=value,
            short=short_token(value),
            scope=TokenScope.parse(str_claim(claims, "azp")),
            issued_at=timestamp_claim(claims, "iat"),
            expires_at=timestamp_claim(claims, "exp"),
            sid=str_claim(claims, "sid"),
            agreement_id=subject.rsplit(":", 1)[-1],
            token_id=web_id if web_id is not None else derived_token_id(value),
        )

    @property
    def capabilities(self) -> frozenset[TokenScope]:
        """Scopes an access token minted from this token can serve."""
        return self.scope.capabilities

    def grants(self, scope: TokenScope) -> bool:
        """Return whether an access token minted from this token can serve `scope`."""
        return scope in self.capabilities

    def is_expired(self, now: float, *, skew: float = 0.0) -> bool:
        """Return whether the token is expired at `now`, counting `skew` seconds early."""
        return now + skew >= self.expires_at

    def expires_in(self, now: float) -> float:
        """Return the seconds until expiry; negative once expired."""
        return self.expires_at - now

    @override
    def __repr__(self) -> str:
        return (
            f"RefreshToken(short={self.short!r}, scope={self.scope!r}, "
            f"expires_at={self.expires_at!r}, token_id={self.token_id!r})"
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class AccessToken:
    """An access token minted by the token endpoint.

    `repr()` omits the token value.

    Attributes:
        value: The bearer token.
        expires_at: Unix timestamp from which the token is no longer valid; the endpoint
            issues access tokens valid for 24 hours.
        scope: The scope of the refresh token it was minted from.
    """

    value: str
    expires_at: int
    scope: TokenScope

    def is_valid(self, now: float, *, skew: float = 0.0) -> bool:
        """Return whether the token is valid at `now`, counting it expired `skew` seconds early."""
        return now + skew < self.expires_at

    @override
    def __repr__(self) -> str:
        return f"AccessToken(value='***', expires_at={self.expires_at!r}, scope={self.scope!r})"


def select_refresh_tokens(
    tokens: Iterable[RefreshToken],
    scope: TokenScope,
    *,
    now: float,
    skew: float = 0.0,
    exclude: Collection[str] = (),
) -> list[RefreshToken]:
    """Return the tokens able to serve `scope`, best first.

    Tokens expired at `now` (counting `skew` seconds early) and tokens whose `sid` is in
    `exclude` are omitted. The rest are ordered least-privileged first, then latest
    expiry first.
    """
    usable = [
        token
        for token in tokens
        if not token.is_expired(now, skew=skew) and token.sid not in exclude and token.grants(scope)
    ]
    return sorted(usable, key=lambda t: (len(t.capabilities), -t.expires_at))


_TOKEN_SEPARATORS = re.compile(r"[\s,]+")


def parse_refresh_tokens(raw: str, *, source: str) -> tuple[RefreshToken, ...]:
    """Decode one or more whitespace- or comma-separated refresh tokens.

    Raises:
        InvalidTokenError: a value is not a refresh token. The message names `source`
            and the token's redacted form, not the value.
    """
    tokens: list[RefreshToken] = []
    for value in _TOKEN_SEPARATORS.split(raw):
        if not value:
            continue
        try:
            tokens.append(RefreshToken.parse(value))
        except InvalidTokenError as exc:
            msg = f"{source} ({short_token(value)}): {exc}"
            raise InvalidTokenError(msg) from exc
    return tuple(tokens)
