"""Exception hierarchy raised by bacsy.

Every error derives from `BacsyError` and belongs to exactly one of four categories:

- `TransportError`: the server could not be reached or talked to.
- `ConfigurationError`: nothing was sent because the setup is wrong.
- `AuthError`: the server does not accept the credentials.
- `ApiError`: the server rejected the operation.

An error raised for an HTTP response carries it as `response`, an `ErrorResponse`.
`BacsyError.transient` says whether the same call may succeed later without a change
on the caller's side.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, override

from bacsy._json import loads_decimal
from bacsy.models.enums import ApiErrorType
from bacsy.models.errors import ApiErrorBody, ApiFieldError

if TYPE_CHECKING:
    from collections.abc import Mapping

    import httpx2

    from bacsy._json import JsonValue
    from bacsy.auth.tokens import TokenScope


@dataclass(frozen=True, slots=True, kw_only=True)
class ErrorResponse:
    """An unsuccessful HTTP response, attached to the error raised for it.

    Attributes:
        status_code: The HTTP status.
        body: The raw response text, when available.
        error: The parsed body, when it has the documented error shape.
    """

    status_code: int
    body: str | None = None
    error: ApiErrorBody | None = None

    @property
    def error_type(self) -> ApiErrorType | None:
        """The API's error classification, when the body could be parsed."""
        return self.error.type if self.error is not None else None

    @property
    def trace_id(self) -> str | None:
        """Server-side trace identifier to quote when contacting support."""
        return self.error.trace_id if self.error is not None else None

    @property
    def field_errors(self) -> list[ApiFieldError]:
        """Per-field validation errors, empty when the body carried none."""
        return list(self.error.errors) if self.error is not None else []

    @property
    def text(self) -> str | None:
        """The server's human-readable message, `displayOptions.text`, when present.

        Written by the API for display to its users, often in Russian, and may name
        account data.
        """
        options = self.error.display_options if self.error is not None else None
        text = options.get("text") if options is not None else None
        return text if isinstance(text, str) and text else None

    def describe(self, message: str) -> str:
        """Return `message` followed by the response's text, error type and trace id."""
        if self.text is not None:
            message = f"{message}: {self.text}"
        details = [f"type={self.error_type.value}" if self.error_type is not None else None]
        details.append(f"trace_id={self.trace_id}" if self.trace_id is not None else None)
        suffix = ", ".join(detail for detail in details if detail is not None)
        return f"{message} [{suffix}]" if suffix else message


class BacsyError(Exception):
    """Base class for every error raised by this library."""

    @property
    def transient(self) -> bool:
        """Whether the same call may succeed later without a change on the caller's side."""
        return False


class TransportError(BacsyError):
    """The server could not be reached or talked to.

    Raised directly when no response arrived: a connection failure, a timeout or a
    protocol error. `ServerError` and `ProtocolError` derive from it.
    """

    @property
    @override
    def transient(self) -> bool:
        return True


class ServerError(TransportError):
    """The server failed to process the request (HTTP 5xx)."""

    def __init__(self, message: str, *, response: ErrorResponse) -> None:
        super().__init__(message)
        self.response: ErrorResponse = response

    @override
    def __str__(self) -> str:
        return self.response.describe(super().__str__())


class ProtocolError(TransportError):
    """A reply that is not JSON or does not match the documented shape.

    `source` names the operation, endpoint or stream; `payload` is the decoded JSON,
    or the raw text when it was not JSON. `transient` is false.
    """

    def __init__(self, message: str, *, source: str, payload: JsonValue) -> None:
        super().__init__(message)
        self.source: str = source
        self.payload: JsonValue = payload

    @property
    @override
    def transient(self) -> bool:
        return False


class WebSocketConnectError(TransportError):
    """The WebSocket handshake failed."""


class WebSocketClosedError(TransportError):
    """The connection was lost and could not be re-established."""

    def __init__(
        self, message: str, *, attempts: int, last_error: BaseException | None = None
    ) -> None:
        super().__init__(message)
        self.attempts: int = attempts
        self.last_error: BaseException | None = last_error


class ConfigurationError(BacsyError):
    """Nothing was sent because the setup is wrong.

    Raised directly when a client factory is given no account name or no refresh token.
    `InvalidTokenError` and the `AccountError` family derive from it.
    """


class InvalidTokenError(ConfigurationError):
    """A value is not a refresh token: not a JWT, wrong type, or a required claim missing."""


class AccountError(ConfigurationError):
    """Base class for failures of the account store; `name` is the account concerned."""

    def __init__(self, message: str, *, name: str | None = None) -> None:
        super().__init__(message)
        self.name: str | None = name


class AccountNotFoundError(AccountError):
    """No account of that name exists."""


class AccountExistsError(AccountError):
    """An account of that name already exists."""


class AccountStoreError(AccountError):
    """The accounts file cannot be read or does not hold what it should."""


class AuthError(BacsyError):
    """The server does not accept the credentials.

    `response` is the server's answer, or `None` when the error was raised without one.
    """

    def __init__(self, message: str, *, response: ErrorResponse | None = None) -> None:
        super().__init__(message)
        self.response: ErrorResponse | None = response

    @override
    def __str__(self) -> str:
        message = super().__str__()
        return self.response.describe(message) if self.response is not None else message


class AuthenticationError(AuthError):
    """The access token was refused (HTTP 401)."""


class PermissionDeniedError(AuthError):
    """The token does not grant the rights the operation requires (HTTP 403)."""


class TokenRefreshReason(StrEnum):
    """Why the token endpoint refused a refresh token.

    Classified from the `error_description` of an HTTP 400 `invalid_grant` response:

    - `"Token is not active"`: `EXPIRED`. The server checks expiry first, so an expired
      token never reports another reason.
    - `"Session not active"`: `REVOKED`. The token was deleted in the web terminal.
    - `"Invalid refresh token. Token client and authorized client don't match"`:
      `SCOPE_MISMATCH`. The `client_id` did not match the token's `azp` claim.
    - `"Invalid refresh token"`: `INVALID`. The token is malformed, tampered with or
      empty.
    - Any other description, body or status: `UNKNOWN`, to be treated as transient.
    """

    EXPIRED = "expired"
    REVOKED = "revoked"
    SCOPE_MISMATCH = "scope_mismatch"
    INVALID = "invalid"
    UNKNOWN = "unknown"

    @property
    def is_permanent(self) -> bool:
        """Whether the token is permanently refused; every reason except `UNKNOWN`."""
        return self is not TokenRefreshReason.UNKNOWN


class TokenRefreshError(AuthError):
    """The token endpoint refused to exchange the refresh token.

    `reason` classifies the refusal; `error` and `description` are the OAuth fields of
    the reply, when present. `transient` is true only when `reason` is `UNKNOWN`.
    """

    def __init__(
        self,
        message: str,
        *,
        response: ErrorResponse | None = None,
        error: str | None = None,
        description: str | None = None,
        reason: TokenRefreshReason = TokenRefreshReason.UNKNOWN,
    ) -> None:
        super().__init__(message, response=response)
        self.error: str | None = error
        self.description: str | None = description
        self.reason: TokenRefreshReason = reason

    @property
    @override
    def transient(self) -> bool:
        return self.reason is TokenRefreshReason.UNKNOWN


class NoUsableTokenError(AuthError):
    """No refresh token held can serve the requested scope.

    Every token held is expired, was rejected by the token endpoint, or does not grant
    `scope`. `expired`, `rejected` and `read_only` count the tokens in each state and
    add up to the number held; all zero means none is held.
    """

    def __init__(
        self,
        message: str,
        *,
        scope: TokenScope,
        expired: int = 0,
        read_only: int = 0,
        rejected: Mapping[TokenRefreshReason, int] | None = None,
    ) -> None:
        super().__init__(message)
        self.scope: TokenScope = scope
        self.expired: int = expired
        self.read_only: int = read_only
        self.rejected: dict[TokenRefreshReason, int] = dict(rejected or {})


class ApiError(BacsyError):
    """The server rejected the operation.

    `response` is the server's answer, or `None` when the error was raised without one.
    """

    def __init__(self, message: str, *, response: ErrorResponse | None = None) -> None:
        super().__init__(message)
        self.response: ErrorResponse | None = response

    @override
    def __str__(self) -> str:
        message = super().__str__()
        return self.response.describe(message) if self.response is not None else message


class BadRequestError(ApiError):
    """The request was malformed (HTTP 400)."""


class RequestValidationError(BadRequestError):
    """The API rejected one or more request fields (HTTP 400/422, `VALIDATION_ERROR`)."""


class NotFoundError(ApiError):
    """The requested resource does not exist (HTTP 404)."""


class ConflictError(ApiError):
    """The request conflicts with the current state of the resource (HTTP 409)."""


class RateLimitError(ApiError):
    """A documented rate limit was exceeded (HTTP 429)."""

    @property
    @override
    def transient(self) -> bool:
        return True


class StreamLimitError(ApiError):
    """A documented connection or subscription limit was reached.

    Raised without a `response` when the client's own count of open connections or
    subscriptions reaches the limit, and with one when the server refuses a WebSocket
    handshake with HTTP 429.
    """


type _StatusErrorClass = (
    type[ApiError] | type[ServerError] | type[AuthenticationError] | type[PermissionDeniedError]
)

_ERROR_TYPE_CLASSES: dict[ApiErrorType, _StatusErrorClass] = {
    ApiErrorType.VALIDATION_ERROR: RequestValidationError,
    ApiErrorType.BAD_REQUEST: BadRequestError,
    ApiErrorType.RESOURCE_EXHAUSTED: RateLimitError,
    ApiErrorType.USER_BLOCKED: PermissionDeniedError,
    ApiErrorType.FORBIDDEN: PermissionDeniedError,
    ApiErrorType.NOT_FOUND: NotFoundError,
    ApiErrorType.USER_NOT_FOUND: NotFoundError,
    ApiErrorType.UNAUTHORIZED: AuthenticationError,
    ApiErrorType.SESSION_NOT_FOUND_ERROR: AuthenticationError,
    ApiErrorType.SESSION_EXPIRED_ERROR: AuthenticationError,
    ApiErrorType.SESSION_FAILED_ERROR: AuthenticationError,
    ApiErrorType.CONFLICT: ConflictError,
    ApiErrorType.INTERNAL_SERVER_ERROR: ServerError,
    ApiErrorType.CANDLE_LIMIT_EXCEEDED: RequestValidationError,
}


def _class_for_status(status_code: int) -> _StatusErrorClass:
    match status_code:
        case 400:
            return BadRequestError
        case 401:
            return AuthenticationError
        case 403:
            return PermissionDeniedError
        case 404:
            return NotFoundError
        case 409:
            return ConflictError
        case 422:
            return RequestValidationError
        case 429:
            return RateLimitError
        case _ if status_code >= 500:
            return ServerError
        case _:
            return ApiError


def error_for_status(
    status_code: int,
    *,
    message: str,
    body: str | None = None,
    error: ApiErrorBody | None = None,
) -> BacsyError:
    """Return the error for an unsuccessful `status_code`, with the response attached.

    The status selects the class: 5xx is `ServerError`, 401 is `AuthenticationError`,
    403 is `PermissionDeniedError`, and the remaining statuses are `ApiError` members.
    For 400, 422 and unmapped statuses, a recognised `error.type` selects the class
    instead.
    """
    cls = _class_for_status(status_code)
    if cls in (ApiError, BadRequestError, RequestValidationError) and error is not None:
        cls = _ERROR_TYPE_CLASSES.get(error.type, cls) if error.type is not None else cls
    return cls(message, response=ErrorResponse(status_code=status_code, body=body, error=error))


def parse_error_body(text: str) -> ApiErrorBody | None:
    """Parse an API error body, returning `None` when it is not the documented shape."""
    try:
        payload = loads_decimal(text)
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    try:
        return ApiErrorBody.model_validate(payload)
    except ValueError:
        return None


def error_for_response(response: httpx2.Response, *, message: str) -> BacsyError:
    """Build the error for an unsuccessful `response`."""
    text = response.text
    return error_for_status(
        response.status_code, message=message, body=text, error=parse_error_body(text)
    )
