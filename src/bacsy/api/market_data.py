"""Market data service (REST snapshots; see ``client.streams`` for live data)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from bacsy.api._base import BaseService, iso_utc
from bacsy.models.common import InstrumentKey
from bacsy.models.market_data import (
    CandlesChart,
    LastTrade,
    LastTradesRequest,
    LastTradesResponse,
    OrderBook,
    Quote,
    QuotesRequest,
    QuotesResponse,
)
from bacsy.routes import Operation, Service

if TYPE_CHECKING:
    from collections.abc import Iterable
    from datetime import datetime

    from bacsy.models.common import InstrumentLike
    from bacsy.models.enums import Side, TimeFrame

MAX_QUOTES_PER_REQUEST = 100
MAX_ORDER_BOOK_DEPTH = 20

GET_QUOTES = Operation(
    name="getQuotes", service=Service.MARKET_DATA, method="POST", path="/api/v1/quotes"
)
GET_ORDER_BOOK = Operation(
    name="getOrderBook", service=Service.MARKET_DATA, method="GET", path="/api/v1/order-book"
)
GET_CANDLES = Operation(
    name="getCandlesChart",
    service=Service.MARKET_DATA,
    method="GET",
    path="/api/v1/candles-chart",
)
GET_LAST_TRADES = Operation(
    name="getLastTrades", service=Service.MARKET_DATA, method="POST", path="/api/v1/last-trades"
)


class MarketDataService(BaseService):
    """``client.market_data``: quotes, order books, candles and recent trades."""

    async def get_quotes(self, instruments: Iterable[InstrumentLike]) -> list[Quote]:
        """Current quotes for up to 100 instruments."""
        keys = InstrumentKey.coerce_all(instruments)
        if not 1 <= len(keys) <= MAX_QUOTES_PER_REQUEST:
            msg = f"between 1 and {MAX_QUOTES_PER_REQUEST} instruments per request"
            raise ValueError(msg)
        response = await self._call(
            GET_QUOTES, QuotesResponse, body=QuotesRequest(instruments=list(keys))
        )
        return response.records

    async def get_order_book(
        self, *, ticker: str, class_code: str, depth: int = MAX_ORDER_BOOK_DEPTH
    ) -> OrderBook:
        """Current order book of one instrument, up to 20 levels per side."""
        if not 1 <= depth <= MAX_ORDER_BOOK_DEPTH:
            msg = f"depth must be between 1 and {MAX_ORDER_BOOK_DEPTH}"
            raise ValueError(msg)
        return await self._call(
            GET_ORDER_BOOK,
            OrderBook,
            params={"ticker": ticker, "classCode": class_code, "depth": depth},
        )

    async def get_candles(
        self,
        *,
        ticker: str,
        class_code: str,
        timeframe: TimeFrame,
        start: datetime,
        end: datetime,
    ) -> CandlesChart:
        """Historical candles.

        The API rejects a request whose period holds more than 1440 bars of
        `timeframe` with HTTP 400 (`RequestValidationError`).
        """
        return await self._call(
            GET_CANDLES,
            CandlesChart,
            params={
                "ticker": ticker,
                "classCode": class_code,
                "timeFrame": timeframe.value,
                "startDate": iso_utc(start),
                "endDate": iso_utc(end),
            },
        )

    async def get_last_trades(
        self,
        *,
        ticker: str,
        class_code: str,
        side: Side | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[LastTrade]:
        """Anonymous trades of one instrument during the current trading session."""
        body = LastTradesRequest(
            ticker=ticker,
            class_code=class_code,
            side=side,
            start_date_time=start,
            end_date_time=end,
        )
        response = await self._call(GET_LAST_TRADES, LastTradesResponse, body=body)
        return response.records
