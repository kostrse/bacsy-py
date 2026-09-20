"""Exchange of a refresh token for an access token at the Keycloak token endpoint."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, cast

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from bacsy.auth.tokens import AccessToken
from bacsy.exceptions import (
    ErrorResponse,
    ProtocolError,
    TokenRefreshError,
    TokenRefreshReason,
    TransportError,
    error_for_response,
)

if TYPE_CHECKING:
    from bacsy._json import JsonValue
    from bacsy.auth.tokens import TokenScope


class _TokenResponse(BaseModel):
    """Successful token endpoint response; field names match the wire format."""

    model_config = ConfigDict(extra="ignore", frozen=True, populate_by_name=True)

    access_token: str
    expires_in: float
    refresh_token: str | None = None
    refresh_expires_in: float | None = None
    token_type: str | None = None
    scope: str | None = None
    session_state: str | None = None
    not_before_policy: int | None = Field(default=None, alias="not-before-policy")


class _ErrorBody(BaseModel):
    """The body the token endpoint returns on a rejected refresh token."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    error: str
    error_description: str | None = None


_DESCRIPTIONS: dict[str, TokenRefreshReason] = {
    "Invalid refresh token. Token client and authorized client don't match": (
        TokenRefreshReason.SCOPE_MISMATCH
    ),
    "Invalid refresh token": TokenRefreshReason.INVALID,
    "Token is not active": TokenRefreshReason.EXPIRED,
    "Session not active": TokenRefreshReason.REVOKED,
}


def classify_refresh_error(
    status_code: int, error: str | None, description: str | None
) -> TokenRefreshReason:
    """Map a token endpoint rejection to a `TokenRefreshReason`.

    Only an HTTP 400 `invalid_grant` with one of the known descriptions is classified;
    everything else is `TokenRefreshReason.UNKNOWN`.
    """
    if status_code != 400 or error != "invalid_grant" or description is None:
        return TokenRefreshReason.UNKNOWN
    return _DESCRIPTIONS.get(description.strip(), TokenRefreshReason.UNKNOWN)


def _refresh_error(response: httpx.Response) -> TokenRefreshError:
    attached = ErrorResponse(status_code=response.status_code, body=response.text)
    try:
        body = _ErrorBody.model_validate(response.json())
    except (ValueError, ValidationError):
        return TokenRefreshError(
            f"token endpoint returned HTTP {response.status_code}", response=attached
        )
    detail = f": {body.error_description}" if body.error_description else ""
    return TokenRefreshError(
        f"token refresh rejected ({body.error}){detail}",
        response=attached,
        error=body.error,
        description=body.error_description,
        reason=classify_refresh_error(response.status_code, body.error, body.error_description),
    )


async def exchange_refresh_token(
    http: httpx.AsyncClient,
    *,
    token_path: str,
    scope: TokenScope,
    refresh_token: str,
    now: float,
) -> AccessToken:
    """POST the refresh-token grant to `token_path` and return the minted `AccessToken`.

    `scope` must match the refresh token's own scope; the endpoint rejects any other
    pairing. The access token's expiry is `now` plus the response's `expires_in`. The
    rotated refresh token in the response is discarded: it carries the same expiry and
    session as the one sent, and the token sent stays valid.

    Raises:
        TokenRefreshError: The endpoint rejected the refresh token (HTTP 400), with the
            classification in `TokenRefreshError.reason`.
        ServerError: The endpoint failed (HTTP 5xx).
        ApiError: Any other unsuccessful status.
        TransportError: The request could not be completed.
        ProtocolError: A successful response is not the documented shape.
    """
    form = {"client_id": scope.value, "grant_type": "refresh_token", "refresh_token": refresh_token}
    try:
        response = await http.post(token_path, data=form, headers={"Accept": "application/json"})
    except httpx.HTTPError as exc:
        raise TransportError(f"token refresh failed: {exc}") from exc

    if response.status_code == 400:
        raise _refresh_error(response)
    if response.is_error:
        raise error_for_response(
            response, message=f"token endpoint returned HTTP {response.status_code}"
        )
    try:
        payload = cast("JsonValue", response.json())
    except ValueError as exc:
        raise ProtocolError(
            "token endpoint returned a non-JSON body",
            source="token endpoint",
            payload=response.text,
        ) from exc
    try:
        parsed = _TokenResponse.model_validate(payload)
    except ValidationError as exc:
        raise ProtocolError(
            f"token endpoint returned an unexpected body: {exc}",
            source="token endpoint",
            payload=payload,
        ) from exc

    expires_at = math.floor(now + parsed.expires_in)
    return AccessToken(value=parsed.access_token, expires_at=expires_at, scope=scope)
