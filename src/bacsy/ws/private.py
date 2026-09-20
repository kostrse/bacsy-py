"""Server-push streams of account data: order events, portfolio, limits, margin."""

from __future__ import annotations

from typing import TYPE_CHECKING

from bacsy.models.limits import Limits
from bacsy.models.margin import MarginIndicators
from bacsy.models.portfolio import Portfolio
from bacsy.models.ws import OrderEvent
from bacsy.routes import Service
from bacsy.ws.stream import PushStream

if TYPE_CHECKING:
    from collections.abc import Callable

    from bacsy.ws.connection import WebSocketConnection

ORDERS_EVENTS_PATH = f"{Service.OPERATIONS.value}/api/v1/orders/events/ws"
PORTFOLIO_PATH = f"{Service.PORTFOLIO.value}/api/v1/portfolio/ws"
LIMITS_PATH = f"{Service.LIMIT.value}/api/v1/limits/ws"
MARGIN_PATH = f"{Service.MARGINAL_INDICATORS.value}/api/v1/marginal-indicators/ws"


class OrdersEventsStream(PushStream[OrderEvent]):
    """Order events for the account, one `OrderEvent` per frame."""

    def __init__(
        self, connection: WebSocketConnection, *, on_close: Callable[[], None] | None = None
    ) -> None:
        super().__init__(connection, OrderEvent, name="orders-events", on_close=on_close)


class PortfolioStream(PushStream[Portfolio]):
    """Portfolio snapshots, one `Portfolio` per frame."""

    def __init__(
        self, connection: WebSocketConnection, *, on_close: Callable[[], None] | None = None
    ) -> None:
        super().__init__(connection, Portfolio, name="portfolio", on_close=on_close)


class LimitsStream(PushStream[Limits]):
    """Limits snapshots, one `Limits` per frame."""

    def __init__(
        self, connection: WebSocketConnection, *, on_close: Callable[[], None] | None = None
    ) -> None:
        super().__init__(connection, Limits, name="limits", on_close=on_close)


class MarginStream(PushStream[MarginIndicators]):
    """Margin indicator snapshots, one `MarginIndicators` per frame."""

    def __init__(
        self, connection: WebSocketConnection, *, on_close: Callable[[], None] | None = None
    ) -> None:
        super().__init__(connection, MarginIndicators, name="margin", on_close=on_close)
