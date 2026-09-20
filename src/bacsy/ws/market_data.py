"""The market-data stream: quotes, order books, candles and last trades."""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from pydantic import ValidationError

from bacsy._json import dumps_request
from bacsy.exceptions import ProtocolError, StreamLimitError
from bacsy.models.common import InstrumentKey
from bacsy.models.ws import (
    CandleEvent,
    DataType,
    LastTradeEvent,
    MarketDataEvent,
    OrderBookEvent,
    QuoteEvent,
    SubscribeMessage,
    SubscribeType,
    SubscriptionAck,
    SubscriptionError,
    UnknownEvent,
)
from bacsy.routes import Service
from bacsy.ws.stream import BaseStream

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from bacsy._json import JsonValue
    from bacsy.models.base import BaseApiModel
    from bacsy.models.common import InstrumentLike
    from bacsy.models.enums import TimeFrame
    from bacsy.ws.connection import WebSocketConnection

MARKET_DATA_PATH = f"{Service.MARKET_DATA.value}/api/v1/market-data/ws"
MAX_INSTRUMENTS_PER_CONNECTION = 100
"""Subscriptions the API allows on one market-data connection."""
MAX_ORDER_BOOK_DEPTH = 20

type SubscriptionKey = tuple[DataType, str, str, str | int | None]
"""One subscription: `(data_type, ticker, class_code, depth or timeframe value)`."""

_DATA_EVENTS: dict[str, type[BaseApiModel]] = {
    "Quotes": QuoteEvent,
    "OrderBook": OrderBookEvent,
    "CandleStick": CandleEvent,
    "LastTrades": LastTradeEvent,
    "OrderBookSuccess": SubscriptionAck,
    "CandleStickSuccess": SubscriptionAck,
    "LastTradesSuccess": SubscriptionAck,
}


def parse_market_data_event(frame: JsonValue) -> MarketDataEvent:
    """Convert a decoded market-data frame into the matching event.

    A frame carrying `errors` becomes a `SubscriptionError`; otherwise `responseType`
    selects the model. An unrecognised type becomes an `UnknownEvent`.

    Raises:
        ProtocolError: The frame is not a JSON object or fails validation.
    """
    if not isinstance(frame, dict):
        raise ProtocolError(
            "market-data frame is not a JSON object", source="market-data", payload=frame
        )
    response_type = frame.get("responseType")
    name = response_type if isinstance(response_type, str) else None
    try:
        if "errors" in frame:
            return SubscriptionError.model_validate(frame)
        model = _DATA_EVENTS.get(name) if name is not None else None
        if model is None:
            return UnknownEvent(response_type=name, payload=frame)
        return model.model_validate(frame)  # pyright: ignore[reportReturnType]
    except ValidationError as exc:
        raise ProtocolError(
            f"market-data frame {name!r} did not validate: {exc}",
            source="market-data",
            payload=frame,
        ) from exc


class SubscriptionRegistry:
    """The set of active subscriptions of a market-data connection."""

    def __init__(self) -> None:
        self._keys: set[SubscriptionKey] = set()

    def __len__(self) -> int:
        return len(self._keys)

    def __contains__(self, key: SubscriptionKey) -> bool:
        return key in self._keys

    @property
    def keys(self) -> frozenset[SubscriptionKey]:
        """A snapshot of the registered subscriptions."""
        return frozenset(self._keys)

    def add(self, keys: Iterable[SubscriptionKey]) -> None:
        """Register subscriptions."""
        self._keys.update(keys)

    def remove(self, keys: Iterable[SubscriptionKey]) -> None:
        """Unregister subscriptions; unknown keys are ignored."""
        self._keys.difference_update(keys)

    def messages(self) -> list[SubscribeMessage]:
        """Return subscribe messages that recreate every registered subscription.

        Subscriptions sharing a data type and parameter are grouped into one message.
        """
        groups: dict[tuple[DataType, str | int | None], list[InstrumentKey]] = {}
        for data_type, ticker, class_code, param in sorted(self._keys, key=str):
            groups.setdefault((data_type, param), []).append(
                InstrumentKey(ticker=ticker, class_code=class_code)
            )
        return [
            _message(SubscribeType.SUBSCRIBE, data_type, instruments, param)
            for (data_type, param), instruments in groups.items()
        ]


def _message(
    action: SubscribeType,
    data_type: DataType,
    instruments: list[InstrumentKey],
    param: str | int | None,
) -> SubscribeMessage:
    return SubscribeMessage(
        subscribe_type=action,
        data_type=data_type,
        instruments=instruments,
        depth=param if data_type is DataType.ORDER_BOOK and isinstance(param, int) else None,
        time_frame=param if data_type is DataType.CANDLES and isinstance(param, str) else None,  # pyright: ignore[reportArgumentType]
    )


class MarketDataStream(BaseStream[MarketDataEvent]):
    """One market-data socket carrying any mix of subscriptions.

    Subscriptions are recorded in the registry before they are sent, so a subscription
    made while the connection is down is sent once it is back, and all of them are
    replayed by `resubscribe`. A connection carries at most
    `MAX_INSTRUMENTS_PER_CONNECTION` subscriptions; `subscribe_*` raises
    `StreamLimitError` beyond that. Instruments may be given as `InstrumentKey` or as
    `(ticker, class_code)` tuples.
    """

    def __init__(
        self, connection: WebSocketConnection, *, on_close: Callable[[], None] | None = None
    ) -> None:
        super().__init__(connection, on_close=on_close)
        self._registry = SubscriptionRegistry()

    @property
    def subscriptions(self) -> SubscriptionRegistry:
        """The registry of active subscriptions."""
        return self._registry

    async def resubscribe(self) -> None:
        """Send a subscribe message for every registered subscription."""
        for message in self._registry.messages():
            await self._connection.send_json(dumps_request(message).decode())

    async def _change(
        self,
        action: SubscribeType,
        data_type: DataType,
        instruments: Iterable[InstrumentLike],
        param: str | int | None,
    ) -> None:
        keys = InstrumentKey.coerce_all(instruments)
        if not keys:
            return
        sub_keys = [(data_type, key.ticker, key.class_code, param) for key in keys]
        if action is SubscribeType.SUBSCRIBE:
            new = {key for key in sub_keys if key not in self._registry}
            if len(self._registry) + len(new) > MAX_INSTRUMENTS_PER_CONNECTION:
                msg = (
                    f"a market-data connection may carry at most "
                    f"{MAX_INSTRUMENTS_PER_CONNECTION} subscriptions"
                )
                raise StreamLimitError(msg)
            self._registry.add(new)
        else:
            self._registry.remove(sub_keys)
        message = _message(action, data_type, list(keys), param)
        await self._connection.send_json(dumps_request(message).decode())

    async def subscribe_quotes(self, instruments: Iterable[InstrumentLike]) -> None:
        """Subscribe to quotes for `instruments`."""
        await self._change(SubscribeType.SUBSCRIBE, DataType.QUOTES, instruments, None)

    async def unsubscribe_quotes(self, instruments: Iterable[InstrumentLike]) -> None:
        """Unsubscribe from quotes for `instruments`."""
        await self._change(SubscribeType.UNSUBSCRIBE, DataType.QUOTES, instruments, None)

    async def subscribe_order_book(
        self,
        instruments: Iterable[InstrumentLike],
        *,
        depth: int = MAX_ORDER_BOOK_DEPTH,
    ) -> None:
        """Subscribe to order books of `depth` levels for `instruments`.

        Raises:
            ValueError: `depth` is outside `1..MAX_ORDER_BOOK_DEPTH`.
        """
        if not 1 <= depth <= MAX_ORDER_BOOK_DEPTH:
            msg = f"depth must be between 1 and {MAX_ORDER_BOOK_DEPTH}"
            raise ValueError(msg)
        await self._change(SubscribeType.SUBSCRIBE, DataType.ORDER_BOOK, instruments, depth)

    async def unsubscribe_order_book(
        self,
        instruments: Iterable[InstrumentLike],
        *,
        depth: int = MAX_ORDER_BOOK_DEPTH,
    ) -> None:
        """Unsubscribe from order books of `depth` levels for `instruments`."""
        await self._change(SubscribeType.UNSUBSCRIBE, DataType.ORDER_BOOK, instruments, depth)

    async def subscribe_candles(
        self, instruments: Iterable[InstrumentLike], *, timeframe: TimeFrame
    ) -> None:
        """Subscribe to candles of `timeframe` for `instruments`."""
        await self._change(SubscribeType.SUBSCRIBE, DataType.CANDLES, instruments, timeframe.value)

    async def unsubscribe_candles(
        self, instruments: Iterable[InstrumentLike], *, timeframe: TimeFrame
    ) -> None:
        """Unsubscribe from candles of `timeframe` for `instruments`."""
        await self._change(
            SubscribeType.UNSUBSCRIBE, DataType.CANDLES, instruments, timeframe.value
        )

    async def subscribe_last_trades(self, instruments: Iterable[InstrumentLike]) -> None:
        """Subscribe to last trades for `instruments`."""
        await self._change(SubscribeType.SUBSCRIBE, DataType.LAST_TRADES, instruments, None)

    async def unsubscribe_last_trades(self, instruments: Iterable[InstrumentLike]) -> None:
        """Unsubscribe from last trades for `instruments`."""
        await self._change(SubscribeType.UNSUBSCRIBE, DataType.LAST_TRADES, instruments, None)

    @override
    def parse(self, frame: JsonValue) -> MarketDataEvent:
        return parse_market_data_event(frame)
