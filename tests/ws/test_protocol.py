"""The default `websockets`-backed connector."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from websockets.datastructures import Headers
from websockets.exceptions import InvalidHandshake, InvalidStatus
from websockets.http11 import Response

from bacsy import DEFAULT_USER_AGENT, StreamOptions
from bacsy.exceptions import AuthenticationError, StreamLimitError, WebSocketConnectError
from bacsy.ws.protocol import MAX_MESSAGE_BYTES, default_connector
from tests.ws.fakes import FakeWebSocket

if TYPE_CHECKING:
    from collections.abc import Callable

URL = "wss://ws.example/stream"
HEADERS = {"Authorization": "Bearer tok"}


class FakeConnect:
    """Stands in for `websockets.asyncio.client.connect` and records its keywords."""

    def __init__(self, outcome: FakeWebSocket | BaseException | None = None) -> None:
        self.outcome: FakeWebSocket | BaseException = outcome or FakeWebSocket()
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def __call__(self, url: str, **kwargs: object) -> FakeWebSocket:
        self.calls.append((url, kwargs))
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


@pytest.fixture
def install_connect(monkeypatch: pytest.MonkeyPatch) -> Callable[[FakeConnect], FakeConnect]:
    def install(fake: FakeConnect) -> FakeConnect:
        monkeypatch.setattr("bacsy.ws.protocol.connect", fake)
        return fake

    return install


async def test_default_connector_passes_headers_options_and_user_agent(
    install_connect: Callable[[FakeConnect], FakeConnect],
) -> None:
    connect = install_connect(FakeConnect())
    options = StreamOptions(ping_interval=7.0, ping_timeout=3.0)

    socket = await default_connector(options)(URL, HEADERS)

    assert socket is connect.outcome
    assert connect.calls == [
        (
            URL,
            {
                "additional_headers": HEADERS,
                "user_agent_header": DEFAULT_USER_AGENT,
                "ping_interval": 7.0,
                "ping_timeout": 3.0,
                "max_size": MAX_MESSAGE_BYTES,
            },
        )
    ]


async def test_default_connector_sends_configured_user_agent(
    install_connect: Callable[[FakeConnect], FakeConnect],
) -> None:
    connect = install_connect(FakeConnect())

    await default_connector(StreamOptions(), user_agent="bacsy-tests/1.0")(URL, HEADERS)

    assert connect.calls[0][1]["user_agent_header"] == "bacsy-tests/1.0"


def _rejected(status: int) -> InvalidStatus:
    return InvalidStatus(Response(status, "Rejected", Headers()))


async def test_default_connector_maps_401_to_authentication_error(
    install_connect: Callable[[FakeConnect], FakeConnect],
) -> None:
    install_connect(FakeConnect(_rejected(401)))

    with pytest.raises(AuthenticationError) as info:
        await default_connector(StreamOptions())(URL, HEADERS)

    assert info.value.response is not None
    assert info.value.response.status_code == 401


async def test_default_connector_maps_429_to_stream_limit_error(
    install_connect: Callable[[FakeConnect], FakeConnect],
) -> None:
    install_connect(FakeConnect(_rejected(429)))

    with pytest.raises(StreamLimitError, match="too many connections") as info:
        await default_connector(StreamOptions())(URL, HEADERS)

    assert info.value.response is not None
    assert info.value.response.status_code == 429


@pytest.mark.parametrize(
    "failure", [_rejected(503), InvalidHandshake("bad upgrade"), OSError("refused"), TimeoutError()]
)
async def test_default_connector_maps_other_failures_to_connect_error(
    install_connect: Callable[[FakeConnect], FakeConnect], failure: BaseException
) -> None:
    install_connect(FakeConnect(failure))

    with pytest.raises(WebSocketConnectError):
        await default_connector(StreamOptions())(URL, HEADERS)
