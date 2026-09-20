"""Messages exchanged over the WebSocket streams."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import IntEnum
from typing import TYPE_CHECKING, Literal

from pydantic import Field

from bacsy.models.base import BaseApiModel, OptionalDatetime, OptionalStr, RequestModel
from bacsy.models.common import InstrumentKey, InstrumentRef
from bacsy.models.enums import LenientStrEnum, TimeFrame, TradeSide
from bacsy.models.market_data import OrderBook, Quote
from bacsy.models.orders import OrderReport

if TYPE_CHECKING:
    from bacsy._json import JsonValue


class DataType(IntEnum):
    """Market-data subscription kinds."""

    ORDER_BOOK = 0
    CANDLES = 1
    LAST_TRADES = 2
    QUOTES = 3


class SubscribeType(IntEnum):
    """Direction of a `SubscribeMessage`."""

    SUBSCRIBE = 0
    UNSUBSCRIBE = 1


class SubscribeMessage(RequestModel):
    """Client-to-server message on the market-data socket."""

    subscribe_type: SubscribeType
    """Subscribe or unsubscribe."""
    data_type: DataType
    """Kind of data."""
    instruments: list[InstrumentKey]
    """Instruments the message applies to."""
    depth: int | None = None
    """Order book depth, 1 to 20; order books only. The server defaults to 20."""
    time_frame: TimeFrame | None = None
    """Candle timeframe; candles only."""


class StreamErrorCode(LenientStrEnum):
    """Error codes reported on the market-data socket."""

    NO_DATA = "NO_DATE"
    """No data. The wire value is spelled ``NO_DATE``."""
    NOT_FOUND = "NOT_FOUND"
    """Instrument not found."""
    INCORRECT_JSON = "INCORRECT_JSON"
    """Malformed message, e.g. a required field is missing."""
    BAD_REQUEST = "BAD_REQUEST"
    """Execution error."""
    UNAUTHORIZED = "UNAUTHORIZED"
    """Client not authorised."""


class StreamError(BaseApiModel):
    """One error entry of a `SubscriptionError`."""

    message: OptionalStr = None
    """Error text."""
    code: StreamErrorCode | None = None
    """Error code."""


class SubscriptionError(BaseApiModel):
    """An in-band error on the market-data socket, delivered as an event."""

    response_type: OptionalStr = None
    """Data type of the failed request, e.g. ``OrderBook`` or ``Quotes``."""
    errors: list[StreamError] = Field(default_factory=list)
    """Errors."""


class SubscriptionAck(InstrumentRef):
    """Confirmation of a subscribe or unsubscribe request for one instrument."""

    response_type: Literal["OrderBookSuccess", "CandleStickSuccess", "LastTradesSuccess"]
    """Which data type was confirmed."""
    subscribe_type: SubscribeType | None = None
    """Subscribe or unsubscribe."""
    depth: int | None = None
    """Order book depth (order books)."""
    time_frame: TimeFrame | None = None
    """Candle timeframe (candles)."""
    date_time: OptionalDatetime = None
    """Time of the response, UTC."""


class QuoteEvent(Quote):
    """A quote update on the market-data stream."""

    response_type: Literal["Quotes"] = "Quotes"
    type: OptionalStr = None
    """Kind of quote object, e.g. ``refresh``."""


class OrderBookEvent(OrderBook):
    """An order book update on the market-data stream."""

    response_type: Literal["OrderBook"] = "OrderBook"


class CandleEvent(InstrumentRef):
    """The latest candle of the subscribed timeframe, re-sent as it changes."""

    response_type: Literal["CandleStick"] = "CandleStick"
    time_frame: TimeFrame | None = None
    """Candle timeframe."""
    open: Decimal | None = None
    """Open price."""
    high: Decimal | None = None
    """High price."""
    low: Decimal | None = None
    """Low price."""
    close: Decimal | None = None
    """Close price."""
    volume: Decimal | None = None
    """Traded volume, in currency."""
    date_time: OptionalDatetime = None
    """Open time of the candle, UTC."""


class LastTradeEvent(InstrumentRef):
    """An anonymous trade on the market-data stream."""

    response_type: Literal["LastTrades"] = "LastTrades"
    side: TradeSide | None = None
    """Buy or sell."""
    price: Decimal | None = None
    """Trade price."""
    quantity: Decimal | None = None
    """Quantity, units."""
    volume: Decimal | None = None
    """Trade value, in currency."""
    date_time: OptionalDatetime = None
    """Time of the trade, UTC."""


@dataclass(frozen=True, slots=True)
class UnknownEvent:
    """A message with a ``responseType`` this library does not know."""

    response_type: str | None
    payload: JsonValue


@dataclass(frozen=True, slots=True)
class Reconnected:
    """Emitted by a stream after its connection was re-established.

    Events may have been missed during ``downtime``; the API provides no sequence
    numbers to detect a gap.
    """

    attempt: int
    downtime: float


MarketDataEvent = (
    QuoteEvent
    | OrderBookEvent
    | CandleEvent
    | LastTradeEvent
    | SubscriptionAck
    | SubscriptionError
    | UnknownEvent
)
"""Any event delivered by the market-data stream."""


class OrderEvent(BaseApiModel):
    """Execution report pushed by the order events stream."""

    original_client_order_id: OptionalStr = None
    """Client identifier of the order that was edited."""
    client_order_id: OptionalStr = None
    """Client identifier of the order."""
    data: OrderReport
    """Execution report."""
