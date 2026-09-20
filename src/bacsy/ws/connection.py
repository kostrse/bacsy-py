"""A WebSocket connection that reconnects, buffers frames and paces outgoing messages."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import random
import time
from enum import Enum
from typing import TYPE_CHECKING

from bacsy._json import loads_decimal
from bacsy.auth.tokens import TokenScope
from bacsy.exceptions import AuthenticationError, WebSocketClosedError
from bacsy.models.ws import Reconnected
from bacsy.ratelimit.bucket import TokenBucket
from bacsy.ratelimit.retry import backoff_delay

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from bacsy._json import JsonValue
    from bacsy.auth.protocols import AccessTokenProvider
    from bacsy.config import ReconnectPolicy, StreamOptions
    from bacsy.ws.protocol import WebSocketConnector, WebSocketLike

log = logging.getLogger("bacsy.ws")

type Frame = JsonValue | Reconnected


class ConnectionState(Enum):
    """Lifecycle state of a `WebSocketConnection`."""

    IDLE = "idle"
    CONNECTING = "connecting"
    OPEN = "open"
    RECONNECTING = "reconnecting"
    CLOSED = "closed"


class _Closed:
    """Queue sentinel marking the end of the connection, with an error or by request."""

    def __init__(self, error: WebSocketClosedError | None) -> None:
        self.error: WebSocketClosedError | None = error


class WebSocketConnection:
    """Owns one socket to `url` and keeps it alive.

    A reader task always awaits the socket so server pings are answered; frames are
    decoded with Decimal-preserving JSON and queued for `next_frame`. Frames that are
    not JSON are dropped. When the queue is full, `StreamOptions.overflow` decides
    whether the oldest frame is evicted (counted in `dropped_frames`) or the reader
    waits. When the socket drops, the connection reconnects with exponential backoff
    when `reconnect.enabled` is set, calls `on_open` after every successful connection,
    and queues a `Reconnected` marker after each reconnect.

    The token provider is asked for a read-scoped access token before each connection.
    A handshake rejected as unauthenticated invalidates that token and is retried once
    with a fresh one.
    """

    def __init__(
        self,
        url: str,
        *,
        token_provider: AccessTokenProvider,
        connector: WebSocketConnector,
        reconnect: ReconnectPolicy,
        options: StreamOptions,
        on_open: Callable[[WebSocketConnection], Awaitable[None]] | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        rng: Callable[[], float] = random.random,
    ) -> None:
        self._url: str = url
        self._provider: AccessTokenProvider = token_provider
        self._connector: WebSocketConnector = connector
        self._reconnect: ReconnectPolicy = reconnect
        self._options: StreamOptions = options
        self._on_open: Callable[[WebSocketConnection], Awaitable[None]] | None = on_open
        self._clock: Callable[[], float] = clock
        self._sleep: Callable[[float], Awaitable[None]] = sleep
        self._rng: Callable[[], float] = rng
        self._ws: WebSocketLike | None = None
        self._task: asyncio.Task[None] | None = None
        self._queue: asyncio.Queue[Frame | _Closed] = asyncio.Queue(maxsize=options.queue_size)
        self._send_bucket = TokenBucket(options.send_rate, clock=clock, sleep=sleep)
        self._closing: bool = False
        self.state: ConnectionState = ConnectionState.IDLE
        self.dropped_frames: int = 0

    @property
    def url(self) -> str:
        return self._url

    @property
    def is_open(self) -> bool:
        return self.state is ConnectionState.OPEN

    async def _connect(self) -> None:
        self.state = ConnectionState.CONNECTING
        token = await self._provider.get(TokenScope.READ)
        try:
            ws = await self._connector(self._url, {"Authorization": f"Bearer {token}"})
        except AuthenticationError:
            await self._provider.invalidate(token)
            fresh = await self._provider.get(TokenScope.READ)
            if fresh == token:
                raise
            ws = await self._connector(self._url, {"Authorization": f"Bearer {fresh}"})
        self._ws = ws
        self.state = ConnectionState.OPEN
        if self._on_open is not None:
            await self._on_open(self)

    async def start(self) -> None:
        """Connect and start the reader task.

        The first connection attempt raises on failure. Calling again after a
        successful start has no effect.
        """
        if self._task is not None:
            return
        await self._connect()
        self._task = asyncio.create_task(self._run(), name=f"bacsy-ws {self._url}")

    def _push(self, item: Frame | _Closed) -> None:
        """Queue `item` without waiting, evicting the oldest frames when full."""
        while self._queue.full():
            with contextlib.suppress(asyncio.QueueEmpty):
                self._queue.get_nowait()
                self.dropped_frames += 1
        self._queue.put_nowait(item)

    async def _read_until_closed(self) -> None:
        ws = self._ws
        if ws is None:
            return
        try:
            while True:
                raw = await ws.recv()
                try:
                    frame = loads_decimal(raw)
                except ValueError:
                    log.warning("dropping non-JSON frame from %s", self._url)
                    continue
                if self._options.overflow == "block":
                    await self._queue.put(frame)
                else:
                    self._push(frame)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if not self._closing:
                log.info("connection to %s lost: %s", self._url, exc)
        finally:
            self._ws = None

    async def _run(self) -> None:
        try:
            while True:
                await self._read_until_closed()
                if self._closing:
                    self._finish(None)
                    return
                if not self._reconnect.enabled:
                    self._finish(
                        WebSocketClosedError("connection closed", attempts=0, last_error=None)
                    )
                    return
                await self._reconnect_loop()
                if self.state is not ConnectionState.OPEN:
                    return
        except asyncio.CancelledError:
            self._finish(None)
            raise

    async def _reconnect_loop(self) -> None:
        self.state = ConnectionState.RECONNECTING
        disconnected_at = self._clock()
        attempt = 0
        last_error: BaseException | None = None
        while True:
            attempt += 1
            limit = self._reconnect.max_attempts
            if limit is not None and attempt > limit:
                self._finish(
                    WebSocketClosedError(
                        f"gave up reconnecting to {self._url} after {limit} attempts",
                        attempts=limit,
                        last_error=last_error,
                    )
                )
                return
            delay = backoff_delay(self._reconnect, attempt, rng=self._rng)
            log.info("reconnecting to %s in %.1fs (attempt %d)", self._url, delay, attempt)
            await self._sleep(delay)
            if self._closing:
                self._finish(None)
                return
            try:
                await self._connect()
            except AuthenticationError as exc:
                self._finish(
                    WebSocketClosedError(
                        f"reconnect to {self._url} rejected: {exc}",
                        attempts=attempt,
                        last_error=exc,
                    )
                )
                return
            except Exception as exc:
                last_error = exc
                log.info("reconnect to %s failed: %s", self._url, exc)
                continue
            self._push(Reconnected(attempt=attempt, downtime=self._clock() - disconnected_at))
            return

    def _finish(self, error: WebSocketClosedError | None) -> None:
        self.state = ConnectionState.CLOSED
        self._push(_Closed(error))

    async def next_frame(self) -> Frame:
        """Wait for the next decoded frame or `Reconnected` marker.

        Raises:
            WebSocketClosedError: The connection ended and will not reconnect.
            StopAsyncIteration: The connection was closed with `aclose`.
        """
        item = await self._queue.get()
        if isinstance(item, _Closed):
            self._queue.put_nowait(item)  # Later calls see the same end marker.
            if item.error is not None:
                raise item.error
            raise StopAsyncIteration
        return item

    async def send_json(self, payload: str) -> bool:
        """Send `payload` if the socket is open and return whether it was sent.

        Messages are paced to `StreamOptions.send_rate`. Nothing is sent while the
        connection is not open.
        """
        ws = self._ws
        if ws is None or self.state is not ConnectionState.OPEN:
            return False
        await self._send_bucket.acquire()
        await ws.send(payload)
        return True

    async def aclose(self) -> None:
        """Close the socket, stop reconnecting and wait for the reader task to end."""
        if self._closing:
            return
        self._closing = True
        ws = self._ws
        if ws is not None:
            with contextlib.suppress(Exception):
                await ws.close()
        task = self._task
        if task is not None and not task.done():
            if self.state is ConnectionState.RECONNECTING:
                task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        self._finish(None)
