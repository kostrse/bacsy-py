"""The client exposes one service object per API and reuses it."""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx2

from bacsy.api import (
    InstrumentsService,
    LimitsService,
    MarginService,
    MarketDataService,
    NonTradeOperationsService,
    OrdersService,
    PortfolioService,
    TradesService,
)

if TYPE_CHECKING:
    from tests.conftest import ClientFactory


async def test_services_are_cached_and_share_the_transport(make_client: ClientFactory) -> None:
    client = make_client(lambda _: httpx2.Response(200, json=[]))

    assert client.portfolio is client.portfolio
    assert isinstance(client.portfolio, PortfolioService)
    assert isinstance(client.limits, LimitsService)
    assert isinstance(client.margin, MarginService)
    assert isinstance(client.instruments, InstrumentsService)
    assert isinstance(client.market_data, MarketDataService)
    assert isinstance(client.orders, OrdersService)
    assert isinstance(client.trades, TradesService)
    assert isinstance(client.operations, NonTradeOperationsService)
    assert (await client.portfolio.get()).lines == []
