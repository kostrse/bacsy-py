"""Quotes, order books, candles and anonymous trades."""

from __future__ import annotations

from decimal import Decimal

from pydantic import Field

from bacsy.models.base import (
    BaseApiModel,
    OptionalDatetime,
    OptionalStr,
    RequestModel,
    UtcDatetime,
)
from bacsy.models.common import InstrumentKey, InstrumentRef
from bacsy.models.enums import SecurityTradingStatus, Side, TimeFrame


class QuotesRequest(RequestModel):
    """Body of ``POST /quotes``."""

    instruments: list[InstrumentKey]
    """Instruments to quote."""


class Quote(InstrumentRef):
    """Snapshot of an instrument's prices for the current session."""

    currency: OptionalStr = None
    """Quote currency."""
    date_time: OptionalDatetime = None
    """Time of the last update, UTC."""
    security_trading_status: SecurityTradingStatus | None = None
    """Trading status of the instrument."""
    bid: Decimal | None = None
    """Best bid."""
    offer: Decimal | None = None
    """Best ask."""
    bid_yield: Decimal | None = None
    """Yield at the bid (bonds)."""
    offer_yield: Decimal | None = None
    """Yield at the ask (bonds)."""
    open: Decimal | None = None
    """Session open price."""
    close: Decimal | None = None
    """Previous session close price."""
    high: Decimal | None = None
    """Day high."""
    low: Decimal | None = None
    """Day low."""
    last: Decimal | None = None
    """Last trade price."""
    theoretical_price: Decimal | None = None
    """Theoretical price (options)."""
    change: Decimal | None = None
    """Price change over the current session, in the price currency."""
    change_rate: Decimal | None = None
    """Price change over the current session, percent."""


class QuotesResponse(BaseApiModel):
    """Result of ``POST /quotes``."""

    records: list[Quote] = Field(default_factory=list)
    """Quotes."""


class OrderBookLevel(BaseApiModel):
    """One price level of an order book."""

    price: Decimal
    """Price."""
    quantity: Decimal
    """Quantity, units."""


class OrderBook(InstrumentRef):
    """Aggregated bids and asks up to ``depth`` levels."""

    depth: int | None = None
    """Levels per side."""
    date_time: OptionalDatetime = None
    """Time of the last update."""
    bid_volume: Decimal | None = None
    """Total bid quantity, units."""
    ask_volume: Decimal | None = None
    """Total ask quantity, units."""
    bids: list[OrderBookLevel] = Field(default_factory=list)
    """Bids."""
    asks: list[OrderBookLevel] = Field(default_factory=list)
    """Asks."""


class Candle(BaseApiModel):
    """One OHLCV bar."""

    time: UtcDatetime
    """Open time of the bar."""
    open: Decimal
    """Open price."""
    high: Decimal
    """High price."""
    low: Decimal
    """Low price."""
    close: Decimal
    """Close price."""
    volume: Decimal | None = None
    """Traded volume, in currency."""


class CandlesChart(InstrumentRef):
    """Candles of one instrument and timeframe over a period."""

    time_frame: TimeFrame | None = None
    """Timeframe of the bars."""
    start_date: OptionalDatetime = None
    """Start of the period."""
    end_date: OptionalDatetime = None
    """End of the period."""
    bars: list[Candle] = Field(default_factory=list)
    """Bars."""


class LastTradesRequest(RequestModel):
    """Body of ``POST /last-trades``."""

    ticker: str
    """Instrument ticker."""
    class_code: str
    """Class code of the security."""
    side: Side | None = None
    """Restrict to one direction."""
    start_date_time: UtcDatetime | None = None
    """Start of the period."""
    end_date_time: UtcDatetime | None = None
    """End of the period."""


class LastTrade(BaseApiModel):
    """An anonymous trade printed on the exchange."""

    date_time: OptionalDatetime = None
    """Time of the trade."""
    price: Decimal | None = None
    """Trade price."""
    quantity: Decimal | None = None
    """Quantity, units."""
    volume: Decimal | None = None
    """Trade value, in the instrument currency."""
    side: Side | None = None
    """Buy or sell."""


class LastTradesResponse(BaseApiModel):
    """Result of ``POST /last-trades``."""

    records: list[LastTrade] = Field(default_factory=list)
    """Trades."""
