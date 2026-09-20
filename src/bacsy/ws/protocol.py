"""The socket interface used by the streams, and the default connector."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from websockets.asyncio.client import connect
from websockets.exceptions import InvalidHandshake, InvalidStatus

from bacsy.config import DEFAULT_USER_AGENT
from bacsy.exceptions import (
    AuthenticationError,
    ErrorResponse,
    StreamLimitError,
    WebSocketConnectError,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Mapping

    from bacsy.config import StreamOptions


class WebSocketLike(Protocol):
    """A connected socket. `websockets` client connections satisfy it."""

    async def recv(self) -> str | bytes: ...

    async def send(self, message: str) -> None: ...

    async def close(self, code: int = 1000, reason: str = "") -> None: ...


type WebSocketConnector = Callable[[str, Mapping[str, str]], Awaitable[WebSocketLike]]
"""Callable opening a socket to a URL with the given request headers."""

MAX_MESSAGE_BYTES = 4 * 1024 * 1024


def default_connector(
    options: StreamOptions, *, user_agent: str = DEFAULT_USER_AGENT
) -> WebSocketConnector:
    """Return a connector backed by the `websockets` library.

    The connector applies the ping settings from `options`, caps incoming messages at
    `MAX_MESSAGE_BYTES` and sends `user_agent` on the handshake unless the headers it is
    given already carry a `User-Agent`. A handshake rejected with HTTP 401 raises
    `AuthenticationError`; any other handshake or connection failure raises
    `WebSocketConnectError`. Server pings are answered by `websockets` only while
    frames are being read.
    """

    async def connector(url: str, headers: Mapping[str, str]) -> WebSocketLike:
        try:
            return await connect(
                url,
                additional_headers=dict(headers),
                user_agent_header=user_agent,
                ping_interval=options.ping_interval,
                ping_timeout=options.ping_timeout,
                max_size=MAX_MESSAGE_BYTES,
            )
        except InvalidStatus as exc:
            status = exc.response.status_code
            if status == 401:
                raise AuthenticationError(
                    f"websocket handshake to {url} rejected: HTTP 401",
                    response=ErrorResponse(status_code=401),
                ) from exc
            if status == 429:
                raise StreamLimitError(
                    f"websocket handshake to {url} refused: HTTP 429, too many connections",
                    response=ErrorResponse(status_code=429),
                ) from exc
            raise WebSocketConnectError(
                f"websocket handshake to {url} failed: HTTP {status}"
            ) from exc
        except (InvalidHandshake, OSError, TimeoutError) as exc:
            raise WebSocketConnectError(f"websocket connection to {url} failed: {exc}") from exc

    return connector
