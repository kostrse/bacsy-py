"""The exception hierarchy and the mapping of HTTP responses onto it."""

from __future__ import annotations

import httpx2
import pytest

from bacsy.exceptions import (
    AccountError,
    AccountExistsError,
    AccountNotFoundError,
    AccountStoreError,
    ApiError,
    AuthenticationError,
    AuthError,
    BacsyError,
    BadRequestError,
    ConfigurationError,
    ConflictError,
    ErrorResponse,
    InvalidTokenError,
    NotFoundError,
    NoUsableTokenError,
    PermissionDeniedError,
    ProtocolError,
    RateLimitError,
    RequestValidationError,
    ServerError,
    StreamLimitError,
    TokenRefreshError,
    TokenRefreshReason,
    TransportError,
    WebSocketClosedError,
    WebSocketConnectError,
    error_for_response,
    error_for_status,
    parse_error_body,
)
from bacsy.models import ApiErrorType

CATEGORIES = (TransportError, ConfigurationError, AuthError, ApiError)

MEMBERS: dict[type[BacsyError], tuple[type[BacsyError], ...]] = {
    TransportError: (ServerError, ProtocolError, WebSocketConnectError, WebSocketClosedError),
    ConfigurationError: (
        InvalidTokenError,
        AccountError,
        AccountNotFoundError,
        AccountExistsError,
        AccountStoreError,
    ),
    AuthError: (AuthenticationError, PermissionDeniedError, TokenRefreshError, NoUsableTokenError),
    ApiError: (
        BadRequestError,
        RequestValidationError,
        NotFoundError,
        ConflictError,
        RateLimitError,
        StreamLimitError,
    ),
}


@pytest.mark.parametrize(
    ("cls", "category"), [(cls, cat) for cat, members in MEMBERS.items() for cls in members]
)
def test_every_error_belongs_to_exactly_one_category(
    cls: type[BacsyError], category: type[BacsyError]
) -> None:
    assert issubclass(cls, category)
    assert issubclass(cls, BacsyError)
    assert [c for c in CATEGORIES if issubclass(cls, c)] == [category]


@pytest.mark.parametrize("cls", CATEGORIES)
def test_categories_are_siblings(cls: type[BacsyError]) -> None:
    assert cls.__bases__ == (BacsyError,)


@pytest.mark.parametrize(
    ("status_code", "expected"),
    [
        (401, AuthenticationError),
        (403, PermissionDeniedError),
        (404, NotFoundError),
        (429, RateLimitError),
        (500, ServerError),
        (503, ServerError),
        (400, BadRequestError),
        (409, ConflictError),
        (422, RequestValidationError),
        (418, ApiError),
    ],
)
def test_error_for_status(status_code: int, expected: type[BacsyError]) -> None:
    error = error_for_status(status_code, message="boom", body="{}")

    assert type(error) is expected
    assert isinstance(error, ApiError | ServerError | AuthError)
    assert error.response is not None
    assert error.response.status_code == status_code
    assert error.response.body == "{}"
    assert str(error) == "boom"


@pytest.mark.parametrize(
    ("error", "transient"),
    [
        (TransportError("x"), True),
        (ServerError("x", response=ErrorResponse(status_code=503)), True),
        (WebSocketClosedError("x", attempts=3), True),
        (ProtocolError("x", source="s", payload=None), False),
        (RateLimitError("x", response=ErrorResponse(status_code=429)), True),
        (NotFoundError("x", response=ErrorResponse(status_code=404)), False),
        (StreamLimitError("x"), False),
        (AuthenticationError("x", response=ErrorResponse(status_code=401)), False),
        (TokenRefreshError("x"), True),
        (TokenRefreshError("x", reason=TokenRefreshReason.REVOKED), False),
        (ConfigurationError("x"), False),
        (InvalidTokenError("x"), False),
    ],
)
def test_transient(error: BacsyError, transient: bool) -> None:
    assert error.transient is transient


@pytest.mark.parametrize("cls", [AccountNotFoundError, AccountExistsError, AccountStoreError])
def test_account_errors_carry_the_account_name(cls: type[AccountError]) -> None:
    assert cls("boom", name="main").name == "main"
    assert cls("boom").name is None
    assert str(cls("boom", name="main")) == "boom"


def test_locally_raised_members_have_no_response() -> None:
    assert StreamLimitError("boom").response is None
    assert TokenRefreshError("boom").response is None
    assert str(StreamLimitError("boom")) == "boom"


def test_parse_error_body_reads_documented_shape() -> None:
    body = parse_error_body(
        '{"type":"VALIDATION_ERROR","errors":[{"field":"price","type":"min"}],'
        '"timestamp":1730278860000,"traceId":"abc"}'
    )

    assert body is not None
    assert body.type is ApiErrorType.VALIDATION_ERROR
    assert body.errors[0].field == "price"
    assert body.trace_id == "abc"
    assert body.timestamp is not None
    assert body.timestamp.isoformat() == "2024-10-30T09:01:00+00:00"


@pytest.mark.parametrize("text", ["", "not json", "[1, 2]", "42"])
def test_parse_error_body_tolerates_garbage(text: str) -> None:
    assert parse_error_body(text) is None


def test_unknown_error_type_is_kept() -> None:
    body = parse_error_body('{"type":"BRAND_NEW"}')

    assert body is not None
    assert body.type is not None
    assert body.type.value == "BRAND_NEW"
    assert not body.type.is_known


@pytest.mark.parametrize(
    ("status_code", "error_type", "expected"),
    [
        (400, "VALIDATION_ERROR", RequestValidationError),
        (400, "RESOURCE_EXHAUSTED", RateLimitError),
        (400, "USER_NOT_FOUND", NotFoundError),
        (400, "SESSION_EXPIRED_ERROR", AuthenticationError),
        (400, "INTERNAL_SERVER_ERROR", ServerError),
        (400, "BRAND_NEW", BadRequestError),
        (418, "CONFLICT", ConflictError),
        (401, "VALIDATION_ERROR", AuthenticationError),
        (500, "NOT_FOUND", ServerError),
    ],
)
def test_error_for_response_refines_by_type(
    status_code: int, error_type: str, expected: type[BacsyError]
) -> None:
    response = httpx2.Response(status_code, json={"type": error_type, "traceId": "t-1"})

    error = error_for_response(response, message="boom")

    assert type(error) is expected
    assert isinstance(error, ApiError | ServerError | AuthError)
    assert error.response is not None
    assert error.response.status_code == status_code
    assert error.response.trace_id == "t-1"
    assert str(error) == f"boom [type={error_type}, trace_id=t-1]"


def test_display_text_is_exposed_and_shown() -> None:
    response = httpx2.Response(
        404,
        json={
            "type": "NOT_FOUND",
            "traceId": "t-1",
            "displayOptions": {"text": "dailyScheduleLine is empty"},
        },
    )

    error = error_for_response(response, message="boom")

    assert isinstance(error, NotFoundError)
    assert error.response is not None
    assert error.response.text == "dailyScheduleLine is empty"
    assert str(error) == "boom: dailyScheduleLine is empty [type=NOT_FOUND, trace_id=t-1]"


@pytest.mark.parametrize("display_options", [None, {}, {"text": ""}, {"text": 7}, {"title": "x"}])
def test_display_text_is_absent_when_not_a_string(display_options: object) -> None:
    body: dict[str, object] = {"type": "NOT_FOUND"}
    if display_options is not None:
        body["displayOptions"] = display_options

    error = error_for_response(httpx2.Response(404, json=body), message="boom")

    assert isinstance(error, NotFoundError)
    assert error.response is not None
    assert error.response.text is None
    assert str(error) == "boom [type=NOT_FOUND]"


def test_error_for_response_without_parsable_body() -> None:
    error = error_for_response(httpx2.Response(503, text="<html>"), message="boom")

    assert type(error) is ServerError
    assert error.response.body == "<html>"
    assert error.response.error is None
    assert error.response.error_type is None
    assert error.response.field_errors == []
    assert str(error) == "boom"
