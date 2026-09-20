"""Trades service: executed trades of the account."""

from __future__ import annotations

from typing import TYPE_CHECKING

from bacsy.api._base import MAX_PAGE_SIZE, BaseService, check_page, iter_pages
from bacsy.models.common import Page
from bacsy.models.trades import Trade, TradesSearchRequest
from bacsy.routes import Operation, Service

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Sequence
    from datetime import datetime

    from bacsy.models.enums import Side

SEARCH_TRADES = Operation(
    name="getTrades", service=Service.TRADE_DETAILS, method="POST", path="/api/v1/trades/search"
)

DEFAULT_TRADE_SORT: tuple[str, ...] = ("tradeDateTime",)


class TradesService(BaseService):
    """``client.trades``: executed trades of the account."""

    async def search(
        self,
        *,
        tickers: Sequence[str] | None = None,
        class_codes: Sequence[str] | None = None,
        trade_nums: Sequence[int] | None = None,
        side: Side | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        page: int = 0,
        size: int = MAX_PAGE_SIZE,
        sort: Sequence[str] = DEFAULT_TRADE_SORT,
    ) -> Page[Trade]:
        """One page of trade history.

        The API lists trades made on or after 24 January 2026.
        """
        check_page(page, size)
        body = TradesSearchRequest(
            tickers=list(tickers) if tickers else None,
            class_codes=list(class_codes) if class_codes else None,
            trade_nums=list(trade_nums) if trade_nums else None,
            side=side,
            start_date_time=start,
            end_date_time=end,
        )
        return await self._call(
            SEARCH_TRADES,
            Page[Trade],
            params={"page": page, "size": size, "sort": list(sort)},
            body=body,
        )

    def iter_search(
        self,
        *,
        tickers: Sequence[str] | None = None,
        class_codes: Sequence[str] | None = None,
        trade_nums: Sequence[int] | None = None,
        side: Side | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        size: int = MAX_PAGE_SIZE,
        sort: Sequence[str] = DEFAULT_TRADE_SORT,
    ) -> AsyncIterator[Trade]:
        """Every trade matching the filter, across all pages."""

        async def fetch(page: int) -> Page[Trade]:
            return await self.search(
                tickers=tickers,
                class_codes=class_codes,
                trade_nums=trade_nums,
                side=side,
                start=start,
                end=end,
                page=page,
                size=size,
                sort=sort,
            )

        return iter_pages(fetch)
