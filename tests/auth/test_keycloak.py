"""Refresh-token exchange against the token endpoint."""

from __future__ import annotations

import httpx
import pytest

from bacsy import (
    TOKEN_ENDPOINT_PATH,
    ProtocolError,
    ServerError,
    TokenRefreshError,
    TransportError,
)
from bacsy.auth import TokenScope, classify_refresh_error, exchange_refresh_token
from bacsy.exceptions import TokenRefreshReason


def _client(handler: httpx.MockTransport | httpx.Response) -> httpx.AsyncClient:
    transport = (
        handler
        if isinstance(handler, httpx.MockTransport)
        else httpx.MockTransport(lambda _: handler)
    )
    return httpx.AsyncClient(transport=transport, base_url="https://be.broker.ru")


async def test_successful_exchange() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "access_token": "acc",
                "expires_in": 86400,
                "refresh_token": "ref2",
                "refresh_expires_in": 7776000,
                "not-before-policy": 0,
                "token_type": "bearer",
            },
        )

    async with _client(httpx.MockTransport(handler)) as http:
        tokens = await exchange_refresh_token(
            http,
            token_path=TOKEN_ENDPOINT_PATH,
            scope=TokenScope.WRITE,
            refresh_token="ref",
            now=10.0,
        )

    assert seen[0].url.path == TOKEN_ENDPOINT_PATH
    assert seen[0].headers["Content-Type"] == "application/x-www-form-urlencoded"
    assert seen[0].read() == b"client_id=trade-api-write&grant_type=refresh_token&refresh_token=ref"
    assert tokens.value == "acc"
    assert tokens.expires_at == 86410.0
    assert tokens.scope is TokenScope.WRITE
    assert "ref2" not in repr(tokens)


async def test_response_without_rotated_refresh_token() -> None:
    response = httpx.Response(200, json={"access_token": "acc", "expires_in": 100})
    async with _client(response) as http:
        tokens = await exchange_refresh_token(
            http,
            token_path=TOKEN_ENDPOINT_PATH,
            scope=TokenScope.READ,
            refresh_token="ref",
            now=0.0,
        )

    assert tokens.expires_at == 100.0


@pytest.mark.parametrize(
    ("status", "error", "description", "expected"),
    [
        (400, "invalid_grant", "Token is not active", TokenRefreshReason.EXPIRED),
        (400, "invalid_grant", "Session not active", TokenRefreshReason.REVOKED),
        (
            400,
            "invalid_grant",
            "Invalid refresh token. Token client and authorized client don't match",
            TokenRefreshReason.SCOPE_MISMATCH,
        ),
        (400, "invalid_grant", "Invalid refresh token", TokenRefreshReason.INVALID),
        (400, "invalid_grant", " Session not active\n", TokenRefreshReason.REVOKED),
        (400, "invalid_grant", "Something new", TokenRefreshReason.UNKNOWN),
        (400, "invalid_grant", None, TokenRefreshReason.UNKNOWN),
        (400, "invalid_request", "Session not active", TokenRefreshReason.UNKNOWN),
        (401, "invalid_client", "Invalid client", TokenRefreshReason.UNKNOWN),
    ],
)
def test_classify_refresh_error(
    status: int, error: str, description: str | None, expected: TokenRefreshReason
) -> None:
    assert classify_refresh_error(status, error, description) is expected
    assert expected.is_permanent is (expected is not TokenRefreshReason.UNKNOWN)


async def test_invalid_grant() -> None:
    response = httpx.Response(
        400, json={"error": "invalid_grant", "error_description": "Token is not active"}
    )
    async with _client(response) as http:
        with pytest.raises(TokenRefreshError, match=r"invalid_grant.*Token is not active") as info:
            await exchange_refresh_token(
                http,
                token_path=TOKEN_ENDPOINT_PATH,
                scope=TokenScope.READ,
                refresh_token="r",
                now=0.0,
            )

    assert info.value.error == "invalid_grant"
    assert info.value.response is not None
    assert info.value.response.status_code == 400
    assert info.value.reason is TokenRefreshReason.EXPIRED


async def test_unparsable_400() -> None:
    async with _client(httpx.Response(400, text="<html>")) as http:
        with pytest.raises(TokenRefreshError, match="HTTP 400") as info:
            await exchange_refresh_token(
                http,
                token_path=TOKEN_ENDPOINT_PATH,
                scope=TokenScope.READ,
                refresh_token="r",
                now=0.0,
            )

    assert info.value.reason is TokenRefreshReason.UNKNOWN


async def test_other_errors_map_to_api_errors() -> None:
    async with _client(httpx.Response(503, text="down")) as http:
        with pytest.raises(ServerError):
            await exchange_refresh_token(
                http,
                token_path=TOKEN_ENDPOINT_PATH,
                scope=TokenScope.READ,
                refresh_token="r",
                now=0.0,
            )


async def test_unexpected_success_body() -> None:
    async with _client(httpx.Response(200, json={"hello": 1})) as http:
        with pytest.raises(ProtocolError, match="unexpected body") as info:
            await exchange_refresh_token(
                http,
                token_path=TOKEN_ENDPOINT_PATH,
                scope=TokenScope.READ,
                refresh_token="r",
                now=0.0,
            )

    assert info.value.source == "token endpoint"
    assert info.value.payload == {"hello": 1}


async def test_non_json_success_body() -> None:
    async with _client(httpx.Response(200, text="<html>")) as http:
        with pytest.raises(ProtocolError, match="non-JSON") as info:
            await exchange_refresh_token(
                http,
                token_path=TOKEN_ENDPOINT_PATH,
                scope=TokenScope.READ,
                refresh_token="r",
                now=0.0,
            )

    assert info.value.payload == "<html>"


async def test_transport_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("nope", request=request)

    async with _client(httpx.MockTransport(handler)) as http:
        with pytest.raises(TransportError):
            await exchange_refresh_token(
                http,
                token_path=TOKEN_ENDPOINT_PATH,
                scope=TokenScope.READ,
                refresh_token="r",
                now=0.0,
            )
