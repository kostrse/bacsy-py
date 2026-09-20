"""Typed async iterators over a `WebSocketConnection`."""

from __future__ import annotations

from typing import TYPE_CHECKING, Self, override

from pydantic import TypeAdapter, ValidationError

from bacsy.exceptions import ProtocolError
from bacsy.models.ws import Reconnected

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import TracebackType

    from bacsy._json import JsonValue
    from bacsy.ws.connection import WebSocketConnection


class BaseStream[T]:
    """Async iterator of typed events over a `WebSocketConnection`.

    `async with` opens the connection and closes it on exit; `async for` yields events.
    Alongside events of type `T` the iterator yields `Reconnected` markers so a consumer
    knows when data may have been missed. A frame that fails validation raises
    `ProtocolError` from `__anext__`; the stream stays usable. Iteration ends
    with `WebSocketClosedError` when the connection is lost for good, or with
    `StopAsyncIteration` after `aclose`.
    """

    def __init__(
        self,
        connection: WebSocketConnection,
        *,
        on_close: Callable[[], None] | None = None,
    ) -> None:
        self._connection: WebSocketConnection = connection
        self._on_close: Callable[[], None] | None = on_close

    @property
    def connection(self) -> WebSocketConnection:
        return self._connection

    def parse(self, frame: JsonValue) -> T:
        """Convert a decoded frame into an event.

        Subclasses must override this method.
        """
        raise NotImplementedError

    async def start(self) -> None:
        """Open the connection."""
        await self._connection.start()

    async def aclose(self) -> None:
        """Close the connection and run the `on_close` callback once."""
        await self._connection.aclose()
        if self._on_close is not None:
            self._on_close()
            self._on_close = None

    async def __aenter__(self) -> Self:
        try:
            await self.start()
        except BaseException:
            await self.aclose()
            raise
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.aclose()

    def __aiter__(self) -> Self:
        return self

    async def __anext__(self) -> T | Reconnected:
        frame = await self._connection.next_frame()
        if isinstance(frame, Reconnected):
            return frame
        return self.parse(frame)


class PushStream[T](BaseStream[T]):
    """A server-push stream whose every frame validates as one `T`.

    `name` labels the stream in validation errors.
    """

    def __init__(
        self,
        connection: WebSocketConnection,
        model: type[T],
        *,
        name: str,
        on_close: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(connection, on_close=on_close)
        self._adapter: TypeAdapter[T] = TypeAdapter(model)
        self._name: str = name

    @override
    def parse(self, frame: JsonValue) -> T:
        try:
            return self._adapter.validate_python(frame)
        except ValidationError as exc:
            msg = f"{self._name} frame did not validate: {exc}"
            raise ProtocolError(msg, source=self._name, payload=frame) from exc
