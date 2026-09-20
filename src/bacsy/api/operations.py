"""Non-trade operations service."""

from __future__ import annotations

from typing import TYPE_CHECKING

from bacsy.api._base import MAX_PAGE_SIZE, BaseService, check_page, iter_until_short
from bacsy.models.operations import NonTradeOperation, OperationsPage, OperationsSearchRequest
from bacsy.routes import Operation, Service

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Sequence
    from datetime import datetime

    from bacsy.models.enums import OperationStatus, OperationType

SEARCH_OPERATIONS = Operation(
    name="getOperationHistory",
    service=Service.NONTRADE_OPERATIONS,
    method="POST",
    path="/api/v1/operations/search",
)


class NonTradeOperationsService(BaseService):
    """``client.operations``: deposits, withdrawals, dividends, coupons, fees, taxes.

    This service is limited to three requests per second.
    """

    async def search(
        self,
        *,
        tickers: Sequence[str] | None = None,
        isins: Sequence[str] | None = None,
        currencies: Sequence[str] | None = None,
        types: Sequence[OperationType] | None = None,
        statuses: Sequence[OperationStatus] | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        page: int = 0,
        size: int = MAX_PAGE_SIZE,
    ) -> OperationsPage:
        """One page of non-trade operations matching the filter."""
        check_page(page, size)
        body = OperationsSearchRequest(
            tickers=list(tickers) if tickers else None,
            isins=list(isins) if isins else None,
            currencies=list(currencies) if currencies else None,
            operation_types=list(types) if types else None,
            statuses=list(statuses) if statuses else None,
            start_date_time=start,
            end_date_time=end,
        )
        return await self._call(
            SEARCH_OPERATIONS, OperationsPage, params={"page": page, "size": size}, body=body
        )

    def iter_search(
        self,
        *,
        tickers: Sequence[str] | None = None,
        isins: Sequence[str] | None = None,
        currencies: Sequence[str] | None = None,
        types: Sequence[OperationType] | None = None,
        statuses: Sequence[OperationStatus] | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        size: int = MAX_PAGE_SIZE,
    ) -> AsyncIterator[NonTradeOperation]:
        """Every operation matching the filter, across all pages."""

        async def fetch(page: int) -> list[NonTradeOperation]:
            result = await self.search(
                tickers=tickers,
                isins=isins,
                currencies=currencies,
                types=types,
                statuses=statuses,
                start=start,
                end=end,
                page=page,
                size=size,
            )
            return result.records

        return iter_until_short(fetch, size=size)
