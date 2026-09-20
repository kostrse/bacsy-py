"""Reconnection, buffering and pacing of WebSocketConnection."""

from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest

from bacsy import ReconnectPolicy, StreamOptions
from bacsy.auth import StaticAccessTokenProvider, TokenScope
from bacsy.exceptions import (
    AuthenticationError,
    ErrorResponse,
    WebSocketClosedError,
    WebSocketConnectError,
)
from bacsy.models.ws import Reconnected
from bacsy.ws import ConnectionState, WebSocketConnection
from tests.ws.fakes import FakeConnector, FakeWebSocket

if TYPE_CHECKING:
    from tests.conftest import FakeClock

URL = "wss://ws.broker.ru/x"


class RotatingProvider:
    def __init__(self) -> None:
        self.tokens = ["t1", "t2"]
        self.invalidated: list[str] = []
        self.scopes: list[TokenScope] = []

    async def get(self, scope: TokenScope) -> str:
        self.scopes.append(scope)
        return self.tokens[0]

    async def invalidate(self, token: str) -> None:
        self.invalidated.append(token)
        if len(self.tokens) > 1 and self.tokens[0] == token:
            self.tokens.pop(0)

    async def aclose(self) -> None:
        return None


def make(
    connector: FakeConnector,
    fake_clock: FakeClock,
    *,
    reconnect: ReconnectPolicy | None = None,
    options: StreamOptions | None = None,
    provider: StaticAccessTokenProvider | RotatingProvider | None = None,
) -> WebSocketConnection:
    return WebSocketConnection(
        URL,
        token_provider=provider or StaticAccessTokenProvider("tok"),
        connector=connector,
        reconnect=reconnect or ReconnectPolicy(jitter=False, base_delay=1, multiplier=2),
        options=options or StreamOptions(send_rate=1000),
        clock=fake_clock,
        sleep=fake_clock.sleep,
    )


async def settle() -> None:
    for _ in range(5):
        await asyncio.sleep(0)


async def test_connects_with_bearer_header_and_decodes_frames(fake_clock: FakeClock) -> None:
    connector = FakeConnector()
    connection = make(connector, fake_clock)
    await connection.start()
    connector.current.push({"price": 1.10})

    frame = await connection.next_frame()

    assert connector.calls[0] == (URL, {"Authorization": "Bearer tok"})
    assert frame == {"price": Decimal("1.10")}
    assert connection.state is ConnectionState.OPEN
    await connection.aclose()
    assert connection.state is ConnectionState.CLOSED
    with pytest.raises(StopAsyncIteration):
        await connection.next_frame()


async def test_first_connect_failure_raises(fake_clock: FakeClock) -> None:
    connector = FakeConnector(outcomes=[WebSocketConnectError("refused")])
    connection = make(connector, fake_clock)

    with pytest.raises(WebSocketConnectError):
        await connection.start()


async def test_401_on_handshake_refreshes_once(fake_clock: FakeClock) -> None:
    provider = RotatingProvider()
    connector = FakeConnector(
        outcomes=[AuthenticationError("no", response=ErrorResponse(status_code=401))]
    )
    connection = make(connector, fake_clock, provider=provider)

    await connection.start()

    assert [h["Authorization"] for _, h in connector.calls] == ["Bearer t1", "Bearer t2"]
    assert provider.invalidated == ["t1"]
    assert provider.scopes == [TokenScope.READ, TokenScope.READ]
    await connection.aclose()


async def test_reconnects_with_backoff_and_emits_marker(fake_clock: FakeClock) -> None:
    connector = FakeConnector(
        outcomes=[FakeWebSocket(), WebSocketConnectError("x"), FakeWebSocket()]
    )
    opened: list[int] = []

    async def on_open(_: WebSocketConnection) -> None:
        opened.append(1)

    connection = make(connector, fake_clock)
    connection._on_open = on_open  # pyright: ignore[reportPrivateUsage]
    await connection.start()
    connector.sockets[0].push({"n": 1})
    connector.sockets[0].drop()

    first = await connection.next_frame()
    marker = await connection.next_frame()
    connector.current.push({"n": 2})
    second = await connection.next_frame()

    assert first == {"n": 1}
    assert isinstance(marker, Reconnected)
    assert marker.attempt == 2
    assert fake_clock.sleeps == [1.0, 2.0]
    assert marker.downtime == pytest.approx(3.0)
    assert second == {"n": 2}
    assert len(opened) == 2
    await connection.aclose()


async def test_gives_up_after_max_attempts(fake_clock: FakeClock) -> None:
    connector = FakeConnector(
        outcomes=[FakeWebSocket(), WebSocketConnectError("a"), WebSocketConnectError("b")]
    )
    connection = make(
        connector, fake_clock, reconnect=ReconnectPolicy(max_attempts=2, jitter=False)
    )
    await connection.start()
    connector.sockets[0].drop()

    with pytest.raises(WebSocketClosedError) as info:
        await connection.next_frame()

    assert info.value.attempts == 2
    assert isinstance(info.value.last_error, WebSocketConnectError)
    assert connection.state is ConnectionState.CLOSED
    await connection.aclose()


async def test_reconnect_disabled(fake_clock: FakeClock) -> None:
    connector = FakeConnector()
    connection = make(connector, fake_clock, reconnect=ReconnectPolicy(enabled=False))
    await connection.start()
    connector.current.drop()

    with pytest.raises(WebSocketClosedError):
        await connection.next_frame()
    assert len(connector.calls) == 1


async def test_auth_failure_during_reconnect_is_fatal(fake_clock: FakeClock) -> None:
    connector = FakeConnector(
        outcomes=[
            FakeWebSocket(),
            AuthenticationError("x", response=ErrorResponse(status_code=401)),
        ]
    )
    connection = make(connector, fake_clock)
    await connection.start()
    connector.sockets[0].drop()

    with pytest.raises(WebSocketClosedError, match="rejected"):
        await connection.next_frame()


async def test_close_during_backoff_stops_reconnecting(fake_clock: FakeClock) -> None:
    async def slow_sleep(seconds: float) -> None:
        await asyncio.sleep(0.05)

    connector = FakeConnector(outcomes=[FakeWebSocket()])
    connection = WebSocketConnection(
        URL,
        token_provider=StaticAccessTokenProvider("tok"),
        connector=connector,
        reconnect=ReconnectPolicy(jitter=False),
        options=StreamOptions(),
        sleep=slow_sleep,
    )
    await connection.start()
    connector.current.drop()
    await settle()
    assert connection.state is ConnectionState.RECONNECTING

    await connection.aclose()

    assert connection.state is ConnectionState.CLOSED
    assert len(connector.calls) == 1
    with pytest.raises(StopAsyncIteration):
        await connection.next_frame()


async def test_drop_oldest_overflow(fake_clock: FakeClock) -> None:
    connector = FakeConnector()
    connection = make(connector, fake_clock, options=StreamOptions(queue_size=2, send_rate=1000))
    await connection.start()
    for n in range(4):
        connector.current.push({"n": n})
    await settle()

    assert await connection.next_frame() == {"n": 2}
    assert await connection.next_frame() == {"n": 3}
    assert connection.dropped_frames == 2
    await connection.aclose()


async def test_block_overflow_applies_backpressure(fake_clock: FakeClock) -> None:
    connector = FakeConnector()
    options = StreamOptions(queue_size=1, overflow="block", send_rate=1000)
    connection = make(connector, fake_clock, options=options)
    await connection.start()
    for n in range(3):
        connector.current.push({"n": n})
    await settle()

    assert connection.dropped_frames == 0
    assert [await connection.next_frame() for _ in range(3)] == [{"n": 0}, {"n": 1}, {"n": 2}]
    await connection.aclose()


async def test_non_json_frames_are_skipped(fake_clock: FakeClock) -> None:
    connector = FakeConnector()
    connection = make(connector, fake_clock)
    await connection.start()
    connector.current.push("not json")
    connector.current.push({"ok": True})

    assert await connection.next_frame() == {"ok": True}
    await connection.aclose()


async def test_send_is_paced_and_skipped_while_down(fake_clock: FakeClock) -> None:
    connector = FakeConnector()
    connection = make(connector, fake_clock, options=StreamOptions(send_rate=2))
    await connection.start()

    assert await connection.send_json('{"a":1}')
    assert await connection.send_json('{"a":2}')
    assert await connection.send_json('{"a":3}')
    assert connector.current.sent == ['{"a":1}', '{"a":2}', '{"a":3}']
    assert fake_clock.sleeps == [pytest.approx(0.5)]

    await connection.aclose()
    assert not await connection.send_json('{"a":4}')
