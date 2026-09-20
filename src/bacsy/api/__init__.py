"""Typed services, one per API microservice, exposed as attributes of the client."""

from __future__ import annotations

from bacsy.api._base import BaseService, iter_pages, iter_until_short
from bacsy.api.instruments import InstrumentsService
from bacsy.api.limits import LimitsService
from bacsy.api.margin import MarginService
from bacsy.api.market_data import MarketDataService
from bacsy.api.operations import NonTradeOperationsService
from bacsy.api.orders import OrdersService
from bacsy.api.portfolio import PortfolioService
from bacsy.api.trades import TradesService

__all__ = [
    "BaseService",
    "InstrumentsService",
    "LimitsService",
    "MarginService",
    "MarketDataService",
    "NonTradeOperationsService",
    "OrdersService",
    "PortfolioService",
    "TradesService",
    "iter_pages",
    "iter_until_short",
]
