"""Reading JWT claims: segment splitting, payload decoding and typed claim access."""

from __future__ import annotations

import pytest

from bacsy.auth import RefreshToken, decode_jwt_claims
from bacsy.auth._jwt import nested_str_claim, str_claim, timestamp_claim
from bacsy.exceptions import InvalidTokenError
from tests.auth.fakes import make_jwt, make_refresh_token

NOW = 1_000_000


def test_decode_keeps_unknown_claims() -> None:
    claims = decode_jwt_claims(make_refresh_token(exp=NOW))

    assert claims["typ"] == "Refresh"
    assert claims["scope"] == "openid"


def test_decode_ignores_the_signature_and_strips_whitespace() -> None:
    assert decode_jwt_claims(f"  {make_jwt({'a': 1}, signature='whatever')}\n") == {"a": 1}


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ("only.two", "three dot-separated segments"),
        ("a..c", "three dot-separated segments"),
        ("a.b.c.d", "three dot-separated segments"),
        ("aGVhZGVy.!!!.c2ln", "not valid base64url"),
        (make_jwt([1, 2]), "not a JSON object"),
        (make_jwt("text"), "not a JSON object"),
        (make_jwt({}, header="aGVhZGVy"), "JWT header is not valid"),
        (make_jwt({}, header="W10"), "JWT header is not a JSON object"),
        (make_jwt({}, header="=e30"), "not valid base64url"),
        (make_jwt({}, header="e30=="), "not valid base64url"),
        (make_jwt({}, signature="a"), "not valid base64url"),
        (make_jwt({}, signature="c=2ln"), "not valid base64url"),
    ],
)
def test_decode_rejects_malformed_tokens(value: str, message: str) -> None:
    with pytest.raises(InvalidTokenError, match=message):
        decode_jwt_claims(value)


def test_str_claim() -> None:
    assert str_claim({"sid": "s"}, "sid") == "s"


def test_valid_padding_preserves_the_token() -> None:
    value = make_refresh_token(exp=NOW)
    padded = ".".join(segment + "=" * (-len(segment) % 4) for segment in value.split("."))
    assert decode_jwt_claims(padded) == decode_jwt_claims(value)
    assert RefreshToken.parse(padded).value == padded


@pytest.mark.parametrize("claims", [{}, {"sid": ""}, {"sid": 3}, {"sid": None}])
def test_str_claim_rejects_anything_but_a_non_empty_string(claims: dict[str, object]) -> None:
    with pytest.raises(InvalidTokenError, match="'sid' is missing or not a string"):
        str_claim(claims, "sid")


@pytest.mark.parametrize(("value", "expected"), [(1, 1), (1.5, 1), (0, 0), (-1.5, -2)])
def test_timestamp_claim_is_whole_seconds(value: float, expected: int) -> None:
    """A fractional NumericDate is floored, so an expiry is never read as later."""
    result = timestamp_claim({"exp": value}, "exp")

    assert result == expected
    assert isinstance(result, int)


@pytest.mark.parametrize("claims", [{}, {"exp": "1"}, {"exp": True}, {"exp": None}])
def test_timestamp_claim_rejects_anything_but_a_number(claims: dict[str, object]) -> None:
    with pytest.raises(InvalidTokenError, match="'exp' is missing or not a number"):
        timestamp_claim(claims, "exp")


def test_nested_str_claim_walks_the_path() -> None:
    claims = {"extra_claims": {"external": {"jtiTradeApi": "00002tst"}}}

    assert nested_str_claim(claims, "extra_claims", "external", "jtiTradeApi") == "00002tst"
    assert nested_str_claim(claims, "extra_claims") is None


@pytest.mark.parametrize(
    "claims",
    [
        {},
        {"extra_claims": {}},
        {"extra_claims": "not an object"},
        {"extra_claims": {"external": {"other": "x"}}},
        {"extra_claims": {"external": {"jtiTradeApi": ""}}},
        {"extra_claims": {"external": {"jtiTradeApi": 7}}},
    ],
)
def test_nested_str_claim_is_optional(claims: dict[str, object]) -> None:
    assert nested_str_claim(claims, "extra_claims", "external", "jtiTradeApi") is None
