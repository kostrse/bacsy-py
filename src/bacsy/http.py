"""The API HTTP client: bearer authentication, rate limits, retries and JSON decoding.

`ApiHttpClient` sits between an `httpx.AsyncClient` and the typed services. An
`Operation` determines the service to pace, whether a retry is safe, and the token scope
to present: `call` takes one from the caller, `request` classifies one from the path,
and a path with an unknown service prefix has none.
"""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Mapping
from typing import TYPE_CHECKING, Self

import httpx

from bacsy._json import dumps_json, dumps_request, loads_decimal
from bacsy.auth.tokens import TokenScope
from bacsy.config import ClientConfig
from bacsy.exceptions import (
    BacsyError,
    ProtocolError,
    RateLimitError,
    TransportError,
    error_for_response,
)
from bacsy.ratelimit.limiter import ServiceRateLimiter
from bacsy.ratelimit.retry import decide
from bacsy.routes import operation_for_raw_request

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from types import TracebackType

    from pydantic import BaseModel

    from bacsy._json import JsonValue
    from bacsy.auth.protocols import AccessTokenProvider
    from bacsy.ratelimit.limiter import RateLimiter
    from bacsy.routes import Operation

log = logging.getLogger("bacsy.http")

QueryValue = str | int | float | bool
type QueryParams = Mapping[str, QueryValue | list[QueryValue]]
"""Query string parameters. A list value repeats its key once per item."""


def new_http_pool(config: ClientConfig) -> httpx.AsyncClient:
    """Return a connection pool with the REST base URL, timeout and `User-Agent` from `config`.

    This is the pool the library creates when none is injected.
    """
    return httpx.AsyncClient(
        base_url=config.rest_base_url,
        timeout=httpx.Timeout(config.timeout_seconds),
        headers={"User-Agent": config.user_agent},
    )


class ApiHttpClient:
    """Send authorized requests, honouring the per-service rate limits and retry policy.

    Every request carries a bearer token from `token_provider` and `Accept:
    application/json`. A 401 is handled by invalidating the token with the provider
    and, when the provider then yields a different token, resending once; this does not
    count as a retry attempt. `request` sends a raw request whose semantics are
    classified from its path; `call` executes an `Operation` the caller supplies. Both
    return the decoded JSON body with numbers as `Decimal`.

    Args:
        token_provider: The source of access tokens, asked for the scope each
            operation needs.
        http: The connection pool to send through. When omitted, one is created from
            `config` and closed by `aclose`; an injected pool is left open.
        config: The client configuration; defaults to `ClientConfig()`.
        rate_limiter: The limiter that paces requests per service; defaults to a
            `ServiceRateLimiter` built from `config.rate_limit`.
        sleep: The coroutine function awaited between retry attempts.
        rng: The source of jitter for retry delays, returning a float in [0, 1).

    Example:
        >>> async with ApiHttpClient(StaticAccessTokenProvider(token)) as http:  # doctest: +SKIP
        ...     portfolio = await http.request("GET", "/trade-api-bff-portfolio/api/v1/portfolio")
    """

    def __init__(
        self,
        token_provider: AccessTokenProvider,
        *,
        http: httpx.AsyncClient | None = None,
        config: ClientConfig | None = None,
        rate_limiter: RateLimiter | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        rng: Callable[[], float] = random.random,
    ) -> None:
        self._config: ClientConfig = config or ClientConfig()
        self._owns_http: bool = http is None
        self._http: httpx.AsyncClient = http or new_http_pool(self._config)
        self._provider: AccessTokenProvider = token_provider
        self._limiter: RateLimiter = rate_limiter or ServiceRateLimiter(self._config.rate_limit)
        self._sleep: Callable[[float], Awaitable[None]] = sleep
        self._rng: Callable[[], float] = rng

    @property
    def config(self) -> ClientConfig:
        """The client configuration."""
        return self._config

    @property
    def token_provider(self) -> AccessTokenProvider:
        """The provider supplying bearer tokens."""
        return self._provider

    def _headers(self, token: str, extra: Mapping[str, str] | None) -> dict[str, str]:
        headers: dict[str, str] = {
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
        }
        if extra:
            headers.update(extra)
        return headers

    async def _send_once(
        self,
        method: str,
        url: str,
        *,
        params: QueryParams | None,
        content: bytes | None,
        headers: Mapping[str, str] | None,
        scope: TokenScope,
    ) -> httpx.Response:
        token = await self._provider.get(scope)
        response = await self._http.request(
            method, url, params=params, content=content, headers=self._headers(token, headers)
        )
        if response.status_code != 401:
            return response
        await self._provider.invalidate(token)
        fresh = await self._provider.get(scope)
        if fresh == token:
            return response
        log.debug("access token rejected; retrying %s %s with a fresh token", method, url)
        return await self._http.request(
            method, url, params=params, content=content, headers=self._headers(fresh, headers)
        )

    async def _send(
        self,
        method: str,
        url: str,
        *,
        operation: Operation | None,
        params: QueryParams | None,
        content: bytes | None,
        headers: Mapping[str, str] | None,
    ) -> httpx.Response:
        """Send a request, pacing and retrying per `operation`, and return a successful response.

        `None` for `operation` means an unknown service: no pacing, no retries, and a
        read token. Errors raised by the token provider propagate unchanged.
        """
        label = f"{method} {url}"
        policy = self._config.retry
        service = operation.service if operation is not None else None
        scope = TokenScope.parse(operation.scope) if operation is not None else TokenScope.READ
        attempt = 0
        while True:
            attempt += 1
            if service is not None:
                await self._limiter.acquire(service)
            error: BacsyError
            try:
                response = await self._send_once(
                    method, url, params=params, content=content, headers=headers, scope=scope
                )
            except httpx.HTTPError as exc:
                error = TransportError(f"{label} failed: {exc}")
                error.__cause__ = exc
            else:
                if not response.is_error:
                    return response
                error = error_for_response(
                    response, message=f"{label} returned HTTP {response.status_code}"
                )
            decision = decide(policy, operation, error, attempt, rng=self._rng)
            if not decision.retry:
                raise error
            if isinstance(error, RateLimitError) and service is not None:
                self._limiter.penalize(service, decision.delay)
            log.debug(
                "%s failed (%s); retry %d/%d in %.2fs",
                label,
                error,
                attempt,
                policy.max_attempts,
                decision.delay,
            )
            await self._sleep(decision.delay)

    @staticmethod
    def _decode(response: httpx.Response, *, source: str) -> JsonValue:
        if not response.content:
            return None
        try:
            return loads_decimal(response.text)
        except ValueError as exc:
            raise ProtocolError(
                f"{source} returned a non-JSON body", source=source, payload=response.text
            ) from exc

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: QueryParams | None = None,
        json: object | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> JsonValue:
        """Send an authorized raw request and return the decoded JSON body.

        `path` is relative to the pool's base URL and starts with the service prefix,
        for example `/trade-api-bff-portfolio/api/v1/portfolio`. A recognised prefix
        selects the service to pace; only a `GET` is treated as idempotent, and only a
        `POST` to the operations service presents a write token. An unknown prefix gets
        no pacing, no retries and a read token. `json` is encoded as the request body
        with `Decimal` values as numbers. `headers` are added to the generated ones and
        may override them. Numbers in the reply are decoded as `Decimal`; an empty body
        decodes to `None`.

        Raises:
            TransportError: The request failed at the transport level.
            ServerError: The response status is 5xx.
            AuthError: The response status is 401 or 403.
            ApiError: The response status is any other error.
            ProtocolError: A successful response is not JSON; `payload` is
                the raw text.
        """
        method = method.upper()
        content: bytes | None = None
        request_headers = dict(headers) if headers else {}
        if json is not None:
            content = dumps_json(json)
            request_headers.setdefault("Content-Type", "application/json")
        response = await self._send(
            method,
            path,
            operation=operation_for_raw_request(method, path),
            params=params,
            content=content,
            headers=request_headers or None,
        )
        return self._decode(response, source=f"{method} {path}")

    async def call(
        self,
        operation: Operation,
        *,
        path_params: Mapping[str, str] | None = None,
        params: QueryParams | None = None,
        body: BaseModel | None = None,
    ) -> JsonValue:
        """Execute `operation` and return the decoded JSON body.

        `operation` supplies the service to pace, whether a retry is safe and the token
        scope. `path_params` fill the placeholders in its path and `body` is serialized
        with the API's field aliases. Numbers in the reply are decoded as `Decimal`; an
        empty body decodes to `None`.

        Raises:
            TransportError: The request failed at the transport level.
            ServerError: The response status is 5xx.
            AuthError: The response status is 401 or 403.
            ApiError: The response status is any other error.
            ProtocolError: A successful response is not JSON; `payload` is
                the raw text.
        """
        url = operation.url(**(path_params or {}))
        content = dumps_request(body) if body is not None else None
        headers = {"Content-Type": "application/json"} if content is not None else None
        response = await self._send(
            operation.method,
            url,
            operation=operation,
            params=params,
            content=content,
            headers=headers,
        )
        return self._decode(response, source=operation.name)

    async def aclose(self) -> None:
        """Close the connection pool if this client created it."""
        if self._owns_http:
            await self._http.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.aclose()
