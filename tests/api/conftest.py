"""Fixtures for service tests: a recording transport over a mock HTTP client."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

import httpx2
import pytest

from bacsy import ClientConfig
from bacsy.auth import StaticAccessTokenProvider
from bacsy.http import ApiHttpClient
from bacsy.ratelimit import NoopRateLimiter

if TYPE_CHECKING:
    from bacsy._json import JsonValue

Responder = Callable[[httpx2.Request], httpx2.Response]


@dataclass
class Recorder:
    """Scripts responses and records the requests a service sends."""

    requests: list[httpx2.Request] = field(default_factory=list)
    responses: list[httpx2.Response | Responder] = field(default_factory=list)

    def reply(self, payload: object, status: int = 200) -> None:
        """Queue a JSON response (``payload`` is serialised unless it is already a string)."""
        text = payload if isinstance(payload, str) else json.dumps(payload)
        self.responses.append(httpx2.Response(status, text=text))

    def respond(self, responder: Responder) -> None:
        """Queue a callable that builds the response from the request."""
        self.responses.append(responder)

    def handle(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        if not self.responses:
            msg = f"unexpected request {request.method} {request.url}"
            raise AssertionError(msg)
        response = self.responses.pop(0)
        return response(request) if callable(response) else response

    @property
    def last(self) -> httpx2.Request:
        return self.requests[-1]

    def last_json(self) -> JsonValue:
        return cast("JsonValue", json.loads(self.last.read()))


@pytest.fixture
def recorder() -> Recorder:
    return Recorder()


@pytest.fixture
async def transport(recorder: Recorder) -> AsyncIterator[ApiHttpClient]:
    http = httpx2.AsyncClient(
        transport=httpx2.MockTransport(recorder.handle), base_url="https://be.broker.ru"
    )
    async with http:
        yield ApiHttpClient(
            StaticAccessTokenProvider("t"),
            http=http,
            config=ClientConfig(),
            rate_limiter=NoopRateLimiter(),
        )
