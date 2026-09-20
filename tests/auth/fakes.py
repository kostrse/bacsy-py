"""Scripted doubles: fake web-issued refresh tokens and a fake token endpoint.

The token endpoint fake answers with the exact ``error_description`` strings the live
endpoint uses and checks them in the same order: expiry, then client match, then session.
All identifiers are placeholders.
"""

from __future__ import annotations

import asyncio
import base64
import json
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from urllib.parse import parse_qs

import httpx

from bacsy.auth import RefreshToken, TokenScope
from bacsy.exceptions import InvalidTokenError

if TYPE_CHECKING:
    from collections.abc import Callable

AGREEMENT = "00000000-0000-4000-8000-000000000001"
OTHER_AGREEMENT = "00000000-0000-4000-8000-000000000002"
FEDERATION = "00000000-0000-4000-8000-0000000000aa"
DAY = 86400
NINETY_DAYS = 90 * DAY

MISMATCH = "Invalid refresh token. Token client and authorized client don't match"


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def make_jwt(payload: object, *, header: str = "e30", signature: str = "c2ln") -> str:
    """A three-segment token carrying an arbitrary payload, for parser tests."""
    return f"{header}.{_b64url(json.dumps(payload).encode())}.{signature}"


def make_refresh_token(
    *,
    scope: TokenScope = TokenScope.READ,
    exp: int,
    iat: int | None = None,
    agreement_id: str = AGREEMENT,
    sid: str | None = None,
    token_id: str | None = None,
    typ: str = "Refresh",
    marker: str = "",
) -> str:
    """Build an unsigned JWT shaped like a BCS refresh token."""
    header = {"alg": "HS512", "typ": "JWT"}
    payload: dict[str, object] = {
        "exp": exp,
        "iat": iat if iat is not None else exp - NINETY_DAYS,
        "iss": "https://example.invalid/realms/tradeapi",
        "sub": f"f:{FEDERATION}:{agreement_id}",
        "typ": typ,
        "azp": scope.value,
        "sid": sid or str(uuid.uuid4()),
        "scope": "openid",
    }
    if token_id is not None:
        payload["extra_claims"] = {"external": {"jtiTradeApi": token_id}}
    # A per-token signature keeps the short forms (first and last four characters) distinct.
    signature = f"sig:{payload['sid']}:{marker}"
    return ".".join(
        [
            _b64url(json.dumps(header).encode()),
            _b64url(json.dumps(payload).encode()),
            _b64url(signature.encode()),
        ]
    )


def _invalid_grant(description: str) -> httpx.Response:
    return httpx.Response(400, json={"error": "invalid_grant", "error_description": description})


@dataclass
class Keycloak:
    """Scripted token endpoint.

    ``revoked`` lists session ids deleted in the web terminal, ``invalid`` lists raw token
    values to reject as malformed. Every accepted exchange mints ``acc{n}``.
    """

    clock: Callable[[], float]
    revoked: set[str] = field(default_factory=set)
    invalid: set[str] = field(default_factory=set)
    calls: list[dict[str, list[str]]] = field(default_factory=list)
    counter: int = 0
    delay: float = 0.0
    access_lifetime: float = DAY

    def handler(self, request: httpx.Request) -> httpx.Response:
        form = parse_qs(request.read().decode())
        self.calls.append(form)
        client_id = form.get("client_id", [""])[0]
        value = form.get("refresh_token", [""])[0]
        if client_id not in {s.value for s in TokenScope}:
            return httpx.Response(
                401,
                json={
                    "error": "invalid_client",
                    "error_description": "Invalid client or Invalid client credentials",
                },
            )
        if value in self.invalid:
            return _invalid_grant("Invalid refresh token")
        try:
            token = RefreshToken.parse(value)
        except InvalidTokenError:
            return _invalid_grant("Invalid refresh token")
        if token.is_expired(self.clock()):
            return _invalid_grant("Token is not active")
        if client_id != token.scope.value:
            return _invalid_grant(MISMATCH)
        if token.sid in self.revoked:
            return _invalid_grant("Session not active")
        self.counter += 1
        return httpx.Response(
            200,
            json={
                "access_token": f"acc{self.counter}",
                "expires_in": self.access_lifetime,
                "refresh_token": value,
                "refresh_expires_in": token.expires_at - self.clock(),
                "token_type": "bearer",
            },
        )

    async def async_handler(self, request: httpx.Request) -> httpx.Response:
        if self.delay:
            await asyncio.sleep(self.delay)
        return self.handler(request)

    def http(self, base_url: str = "https://be.broker.ru") -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.MockTransport(self.async_handler), base_url=base_url
        )

    def client_ids(self) -> list[str]:
        return [call["client_id"][0] for call in self.calls]
