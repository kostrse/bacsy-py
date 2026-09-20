"""Refresh-token decoding, access tokens and token selection."""

from __future__ import annotations

import hashlib
from dataclasses import replace

import pytest

from bacsy.auth import (
    AccessToken,
    RefreshToken,
    TokenScope,
    derived_token_id,
    parse_refresh_tokens,
    select_refresh_tokens,
    short_token,
)
from bacsy.exceptions import InvalidTokenError
from tests.auth.fakes import AGREEMENT, DAY, NINETY_DAYS, make_jwt, make_refresh_token

NOW = 1_000_000


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("read", TokenScope.READ),
        ("WRITE", TokenScope.WRITE),
        ("rw", TokenScope.WRITE),
        ("trade-api-read", TokenScope.READ),
        (TokenScope.WRITE, TokenScope.WRITE),
    ],
)
def test_scope_parse(value: str | TokenScope, expected: TokenScope) -> None:
    assert TokenScope.parse(value) is expected


def test_scope_parse_rejects_unknown() -> None:
    with pytest.raises(InvalidTokenError, match="unknown token scope"):
        TokenScope.parse("admin")


def test_scope_capabilities() -> None:
    assert TokenScope.READ.capabilities == {TokenScope.READ}
    assert TokenScope.WRITE.capabilities == {TokenScope.READ, TokenScope.WRITE}


def test_parse_reads_every_claim() -> None:
    value = make_refresh_token(
        scope=TokenScope.WRITE, exp=NOW + NINETY_DAYS, sid="sid-1", token_id="00002tst"
    )

    token = RefreshToken.parse(f"  {value}\n")

    assert token.value == value
    assert token.scope is TokenScope.WRITE
    assert token.expires_at == NOW + NINETY_DAYS
    assert token.issued_at == NOW
    assert token.sid == "sid-1"
    assert token.agreement_id == AGREEMENT
    assert token.token_id == "00002tst"
    assert token.short == short_token(value)
    assert token.grants(TokenScope.READ)
    assert token.grants(TokenScope.WRITE)


def test_parse_without_web_terminal_id_derives_one() -> None:
    value = make_refresh_token(exp=NOW)
    token = RefreshToken.parse(value)

    assert token.token_id == derived_token_id(value)
    assert token.token_id == hashlib.sha256(value.encode()).hexdigest()[:8]
    assert RefreshToken.parse(f" {value}\n").token_id == token.token_id
    assert RefreshToken.parse(make_refresh_token(exp=NOW, marker="2")).token_id != token.token_id
    assert token.scope is TokenScope.READ
    assert not token.grants(TokenScope.WRITE)


def test_derived_token_id_is_short_hex_and_reveals_nothing() -> None:
    token_id = derived_token_id("eyJhbGciOiJIUzUxMiJ9.payload.signature")

    assert len(token_id) == 8
    assert all(c in "0123456789abcdef" for c in token_id)
    assert token_id not in "eyJhbGciOiJIUzUxMiJ9.payload.signature"


def test_short_form_matches_the_web_terminal() -> None:
    assert short_token("eyJhbGciOiJIUzUxMiJ9.payload.signaturelCGA") == "eyJh**********lCGA"
    assert short_token("tiny") == "**********"


def test_the_display_label_is_settled_at_parse_and_never_recomputed() -> None:
    """A token whose value is replaced keeps the label it was parsed with."""
    token = RefreshToken.parse(make_refresh_token(exp=NOW, token_id="00002tst"))

    encrypted = replace(token, value="opaque-ciphertext")

    assert encrypted.short == token.short
    assert short_token(encrypted.value) != encrypted.short
    assert encrypted.short in repr(encrypted)


def test_repr_hides_value_and_agreement() -> None:
    value = make_refresh_token(exp=NOW, token_id="00002tst")
    text = repr(RefreshToken.parse(value))

    assert value not in text
    assert AGREEMENT not in text
    assert "eyJh**********" in text
    assert "00002tst" in text


def test_expiry_with_skew() -> None:
    token = RefreshToken.parse(make_refresh_token(exp=NOW + 100))

    assert not token.is_expired(NOW)
    assert token.is_expired(NOW + 100)
    assert token.is_expired(NOW + 50, skew=60)
    assert token.expires_in(NOW) == 100


@pytest.mark.parametrize(
    ("value", "message"),
    [
        (make_jwt({"typ": "Bearer", "azp": "trade-api-read"}), "access token"),
        (make_jwt({"typ": "ID"}), "unexpected JWT type"),
        (
            make_jwt({"typ": "Refresh", "azp": "trade-api-admin", "sub": "f:a:b"}),
            "unknown token scope",
        ),
        ("only.two", "three dot-separated segments"),
    ],
)
def test_parse_rejects_malformed_tokens(value: str, message: str) -> None:
    with pytest.raises(InvalidTokenError, match=message):
        RefreshToken.parse(value)


def test_parse_rejects_missing_claims() -> None:
    payload = {"typ": "Refresh", "azp": "trade-api-read", "sub": "f:a:b", "exp": 1, "iat": 0}
    with pytest.raises(InvalidTokenError, match="'sid' is missing"):
        RefreshToken.parse(make_jwt(payload))
    payload["sid"] = "s"
    payload["exp"] = True
    with pytest.raises(InvalidTokenError, match="'exp' is missing"):
        RefreshToken.parse(make_jwt(payload))


def test_access_token_validity_and_repr() -> None:
    token = AccessToken(value="secret-access", expires_at=NOW + 100, scope=TokenScope.READ)

    assert token.is_valid(NOW)
    assert not token.is_valid(NOW + 50, skew=60)
    assert "secret-access" not in repr(token)


def _refresh(**kwargs: object) -> RefreshToken:
    exp = kwargs.pop("exp", NOW + 30 * DAY)
    return RefreshToken.parse(make_refresh_token(exp=int(str(exp)), **kwargs))  # pyright: ignore[reportArgumentType]


def test_select_prefers_least_privilege_then_latest_expiry() -> None:
    read_short = _refresh(exp=NOW + 10 * DAY, sid="r-short")
    read_long = _refresh(exp=NOW + 80 * DAY, sid="r-long")
    write_short = _refresh(scope=TokenScope.WRITE, exp=NOW + 10 * DAY, sid="w-short")
    write_long = _refresh(scope=TokenScope.WRITE, exp=NOW + 80 * DAY, sid="w-long")
    tokens = (write_short, read_short, write_long, read_long)

    read_order = [t.sid for t in select_refresh_tokens(tokens, TokenScope.READ, now=NOW)]
    write_order = [t.sid for t in select_refresh_tokens(tokens, TokenScope.WRITE, now=NOW)]

    assert read_order == ["r-long", "r-short", "w-long", "w-short"]
    assert write_order == ["w-long", "w-short"]


def test_select_filters_expired_excluded_and_skew() -> None:
    expired = _refresh(exp=NOW - 1, sid="expired")
    dead = _refresh(exp=NOW + DAY, sid="dead")
    soon = _refresh(exp=NOW + 30, sid="soon")
    fine = _refresh(exp=NOW + DAY, sid="fine")

    picked = select_refresh_tokens(
        (expired, dead, soon, fine), TokenScope.READ, now=NOW, skew=60, exclude={"dead"}
    )

    assert [t.sid for t in picked] == ["fine"]


def test_parse_refresh_tokens_splits_and_redacts() -> None:
    read = make_refresh_token(exp=NOW + DAY)
    write = make_refresh_token(scope=TokenScope.WRITE, exp=NOW + DAY)

    tokens = parse_refresh_tokens(f" {read},\n{write} ", source="X")
    assert [t.scope for t in tokens] == [TokenScope.READ, TokenScope.WRITE]
    assert parse_refresh_tokens("", source="X") == ()

    with pytest.raises(InvalidTokenError, match=r"X \(") as info:
        parse_refresh_tokens("garbage-token-value", source="X")
    assert "garbage-token-value" not in str(info.value)
