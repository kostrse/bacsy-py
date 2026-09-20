"""ApiHttpClient: authorization, 401 handling, retries and rate-limit penalties."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

import httpx2
import pytest

from bacsy import DEFAULT_USER_AGENT, ClientConfig, RetryPolicy, new_http_pool
from bacsy.auth import StaticAccessTokenProvider, TokenScope
from bacsy.exceptions import (
    AuthenticationError,
    ProtocolError,
    RateLimitError,
    ServerError,
    TransportError,
)
from bacsy.http import ApiHttpClient
from bacsy.models import RequestModel
from bacsy.ratelimit import NoopRateLimiter
from bacsy.routes import Operation, Service

if TYPE_CHECKING:
    from collections.abc import Callable

    from bacsy.routes import Service as ServiceType
    from tests.conftest import FakeClock

READ = Operation(
    name="portfolio", service=Service.PORTFOLIO, method="GET", path="/api/v1/portfolio"
)
WRITE = Operation(
    name="create",
    service=Service.OPERATIONS,
    method="POST",
    path="/api/v1/orders",
    idempotent=False,
    scope="write",
)


class Body(RequestModel):
    order_quantity: int
    client_order_id: str


class RotatingProvider:
    """Hands out ``t1``, then ``t2`` after invalidation."""

    def __init__(self) -> None:
        self.tokens: list[str] = ["t1", "t2"]
        self.invalidated: list[str] = []
        self.scopes: list[TokenScope] = []

    async def get(self, scope: TokenScope) -> str:
        self.scopes.append(scope)
        return self.tokens[0]

    async def invalidate(self, token: str) -> None:
        self.invalidated.append(token)
        if len(self.tokens) > 1 and self.tokens[0] == token:
            self.tokens.pop(0)


class RecordingLimiter:
    def __init__(self) -> None:
        self.acquired: list[ServiceType] = []
        self.penalties: list[tuple[ServiceType, float]] = []

    async def acquire(self, service: ServiceType) -> None:
        self.acquired.append(service)

    def penalize(self, service: ServiceType, delay: float) -> None:
        self.penalties.append((service, delay))


def _transport(
    handler: Callable[[httpx2.Request], httpx2.Response],
    fake_clock: FakeClock,
    *,
    provider: RotatingProvider | StaticAccessTokenProvider | None = None,
    limiter: RecordingLimiter | None = None,
    retry: RetryPolicy | None = None,
) -> tuple[ApiHttpClient, httpx2.AsyncClient]:
    http = httpx2.AsyncClient(
        transport=httpx2.MockTransport(handler), base_url="https://be.broker.ru"
    )
    transport = ApiHttpClient(
        provider or StaticAccessTokenProvider("t1"),
        http=http,
        config=ClientConfig(retry=retry or RetryPolicy(jitter=False, base_delay=1, multiplier=1)),
        rate_limiter=limiter or NoopRateLimiter(),
        sleep=fake_clock.sleep,
        rng=lambda: 1.0,
    )
    return transport, http


async def test_call_sends_body_and_decodes_decimals(fake_clock: FakeClock) -> None:
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(200, text='{"price": 10.10}')

    transport, http = _transport(handler, fake_clock)
    async with http:
        payload = await transport.call(WRITE, body=Body(order_quantity=1, client_order_id="c"))

    assert payload == {"price": Decimal("10.10")}
    assert seen[0].method == "POST"
    assert seen[0].url.path == "/trade-api-bff-operations/api/v1/orders"
    assert seen[0].headers["Content-Type"] == "application/json"
    assert seen[0].read() == b'{"orderQuantity":1,"clientOrderId":"c"}'


async def test_request_sends_decimals_as_numbers_and_decodes_them(fake_clock: FakeClock) -> None:
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(200, text='{"price": 10.10}')

    transport, http = _transport(handler, fake_clock)
    async with http:
        payload = await transport.request(
            "post",
            "/trade-api-bff-operations/api/v1/orders",
            params={"limit": 5},
            json={"price": Decimal("10.50"), "quantity": Decimal("2"), "note": "x"},
        )

    assert payload == {"price": Decimal("10.10")}
    assert seen[0].method == "POST"
    assert seen[0].url.params["limit"] == "5"
    assert seen[0].headers["Content-Type"] == "application/json"
    assert seen[0].read() == b'{"price":10.5,"quantity":2,"note":"x"}'


async def test_request_rejects_a_body_it_cannot_encode(fake_clock: FakeClock) -> None:
    transport, http = _transport(lambda _: httpx2.Response(200), fake_clock)
    async with http:
        with pytest.raises(TypeError, match="not JSON serializable"):
            await transport.request(
                "POST", "/trade-api-bff-limit/api/v1/limits", json={"a": object()}
            )


async def test_request_returns_none_for_empty_body(fake_clock: FakeClock) -> None:
    transport, http = _transport(lambda _: httpx2.Response(200), fake_clock)
    async with http:
        assert await transport.request("GET", "/trade-api-bff-limit/api/v1/limits") is None


async def test_request_rejects_non_json_success(fake_clock: FakeClock) -> None:
    transport, http = _transport(lambda _: httpx2.Response(200, text="<html>"), fake_clock)
    async with http:
        with pytest.raises(ProtocolError) as info:
            await transport.request("GET", "/trade-api-bff-limit/api/v1/limits")

    assert info.value.source == "GET /trade-api-bff-limit/api/v1/limits"
    assert info.value.payload == "<html>"


async def test_call_returns_none_for_empty_body(fake_clock: FakeClock) -> None:
    transport, http = _transport(lambda _: httpx2.Response(200), fake_clock)
    async with http:
        assert await transport.call(READ) is None


async def test_call_rejects_non_json_success(fake_clock: FakeClock) -> None:
    transport, http = _transport(lambda _: httpx2.Response(200, text="<html>"), fake_clock)
    async with http:
        with pytest.raises(ProtocolError, match="non-JSON") as info:
            await transport.call(READ)
    assert info.value.source == READ.name
    assert info.value.payload == "<html>"


async def test_401_refreshes_once_and_resends(fake_clock: FakeClock) -> None:
    seen: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        token = request.headers["Authorization"]
        seen.append(token)
        return httpx2.Response(401 if token == "Bearer t1" else 200, json={})

    provider = RotatingProvider()
    transport, http = _transport(handler, fake_clock, provider=provider)
    async with http:
        await transport.call(READ)

    assert seen == ["Bearer t1", "Bearer t2"]
    assert provider.invalidated == ["t1"]
    assert provider.scopes == [TokenScope.READ, TokenScope.READ]
    assert fake_clock.sleeps == []


async def test_write_operations_request_a_write_token(fake_clock: FakeClock) -> None:
    provider = RotatingProvider()
    transport, http = _transport(
        lambda _: httpx2.Response(200, json={}), fake_clock, provider=provider
    )
    async with http:
        await transport.call(WRITE, body=Body(order_quantity=1, client_order_id="c"))
        await transport.request("GET", "/unknown-service/api/v1/thing")

    assert provider.scopes == [TokenScope.WRITE, TokenScope.READ]


async def test_second_401_raises(fake_clock: FakeClock) -> None:
    calls = 0

    def handler(request: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        calls += 1
        return httpx2.Response(401, json={"type": "UNAUTHORIZED"})

    transport, http = _transport(handler, fake_clock, provider=RotatingProvider())
    async with http:
        with pytest.raises(AuthenticationError):
            await transport.call(WRITE, body=Body(order_quantity=1, client_order_id="c"))

    assert calls == 2
    assert fake_clock.sleeps == []


async def test_static_token_401_is_not_resent(fake_clock: FakeClock) -> None:
    calls = 0

    def handler(request: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        calls += 1
        return httpx2.Response(401)

    transport, http = _transport(handler, fake_clock)
    async with http:
        with pytest.raises(AuthenticationError):
            await transport.call(READ)

    assert calls == 1


async def test_idempotent_read_retries_server_errors(fake_clock: FakeClock) -> None:
    responses = [httpx2.Response(503), httpx2.Response(502), httpx2.Response(200, json={"ok": 1})]

    transport, http = _transport(lambda _: responses.pop(0), fake_clock)
    async with http:
        assert await transport.call(READ) == {"ok": 1}

    assert fake_clock.sleeps == [1.0, 1.0]


async def test_read_gives_up_after_max_attempts(fake_clock: FakeClock) -> None:
    calls = 0

    def handler(request: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        calls += 1
        raise httpx2.ReadTimeout("slow", request=request)

    transport, http = _transport(handler, fake_clock)
    async with http:
        with pytest.raises(TransportError):
            await transport.call(READ)

    assert calls == 3


async def test_write_is_never_retried_on_server_or_transport_errors(
    fake_clock: FakeClock,
) -> None:
    calls = 0

    def handler(request: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        calls += 1
        return httpx2.Response(500)

    transport, http = _transport(handler, fake_clock)
    async with http:
        with pytest.raises(ServerError):
            await transport.call(WRITE, body=Body(order_quantity=1, client_order_id="c"))

    assert calls == 1
    assert fake_clock.sleeps == []


async def test_429_retries_writes_and_penalizes_the_service(fake_clock: FakeClock) -> None:
    responses = [httpx2.Response(429), httpx2.Response(200, json={"status": "OK"})]
    limiter = RecordingLimiter()

    transport, http = _transport(lambda _: responses.pop(0), fake_clock, limiter=limiter)
    async with http:
        assert await transport.call(WRITE, body=Body(order_quantity=1, client_order_id="c")) == {
            "status": "OK"
        }

    assert limiter.acquired == [Service.OPERATIONS, Service.OPERATIONS]
    assert limiter.penalties == [(Service.OPERATIONS, 1.0)]
    assert fake_clock.sleeps == [1.0]


async def test_429_with_writes_opted_out(fake_clock: FakeClock) -> None:
    transport, http = _transport(
        lambda _: httpx2.Response(429), fake_clock, retry=RetryPolicy(retry_writes_on_429=False)
    )
    async with http:
        with pytest.raises(RateLimitError):
            await transport.call(WRITE, body=Body(order_quantity=1, client_order_id="c"))


async def test_new_http_pool_carries_config() -> None:
    config = ClientConfig(user_agent="bacsy-tests/1.0", timeout_seconds=5.0)

    async with new_http_pool(config) as pool:
        assert str(pool.base_url) == config.rest_base_url
        assert pool.timeout == httpx2.Timeout(5.0)
        assert pool.headers["User-Agent"] == "bacsy-tests/1.0"


async def test_created_pool_sends_library_user_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    pools: list[httpx2.AsyncClient] = []

    def spy(config: ClientConfig) -> httpx2.AsyncClient:
        pools.append(new_http_pool(config))
        return pools[-1]

    monkeypatch.setattr("bacsy.http.new_http_pool", spy)
    async with ApiHttpClient(StaticAccessTokenProvider("t1")):
        assert pools[0].headers["User-Agent"] == DEFAULT_USER_AGENT
        assert DEFAULT_USER_AGENT.startswith("bacsy/")
    assert pools[0].is_closed
