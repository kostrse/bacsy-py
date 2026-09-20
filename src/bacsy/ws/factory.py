"""Stream construction and the per-service connection budget."""

from __future__ import annotations

import asyncio
import random
import time
from types import MappingProxyType
from typing import TYPE_CHECKING

from bacsy.exceptions import StreamLimitError
from bacsy.models.common import InstrumentKey
from bacsy.models.ws import DataType
from bacsy.routes import Service
from bacsy.ws.connection import WebSocketConnection
from bacsy.ws.market_data import MARKET_DATA_PATH, MarketDataStream
from bacsy.ws.private import (
    LIMITS_PATH,
    MARGIN_PATH,
    ORDERS_EVENTS_PATH,
    PORTFOLIO_PATH,
    LimitsStream,
    MarginStream,
    OrdersEventsStream,
    PortfolioStream,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Iterable, Mapping

    from bacsy.auth.protocols import AccessTokenProvider
    from bacsy.config import ClientConfig
    from bacsy.models.common import InstrumentLike
    from bacsy.models.enums import TimeFrame
    from bacsy.ws.market_data import SubscriptionKey
    from bacsy.ws.protocol import WebSocketConnector
    from bacsy.ws.stream import BaseStream

DEFAULT_CONNECTION_CAPS: Mapping[Service, int] = MappingProxyType(
    {
        Service.PORTFOLIO: 2,
        Service.LIMIT: 2,
        Service.OPERATIONS: 4,
        Service.MARGINAL_INDICATORS: 2,
        Service.MARKET_DATA: 20,
    }
)
"""Concurrent WebSocket connections the API allows per service and account."""


class ConnectionBudget:
    """Counts connections per service against per-service caps.

    With `enforce` off the counts are kept but never limit anything. Services absent
    from `caps` are unlimited.
    """

    def __init__(
        self, caps: Mapping[Service, int] = DEFAULT_CONNECTION_CAPS, *, enforce: bool = True
    ) -> None:
        self._caps: Mapping[Service, int] = caps
        self._enforce: bool = enforce
        self._open: dict[Service, int] = {}

    def in_use(self, service: Service) -> int:
        """Return the number of connections counted for `service`."""
        return self._open.get(service, 0)

    def acquire(self, service: Service) -> None:
        """Count one more connection to `service`.

        Raises:
            StreamLimitError: The cap is enforced and already reached.
        """
        cap = self._caps.get(service)
        if self._enforce and cap is not None and self.in_use(service) >= cap:
            msg = f"the API allows {cap} concurrent connections to {service.name.lower()}"
            raise StreamLimitError(msg)
        self._open[service] = self.in_use(service) + 1

    def release(self, service: Service) -> None:
        """Count one connection to `service` less, never below zero."""
        self._open[service] = max(0, self.in_use(service) - 1)


class StreamFactory:
    """Creates streams bound to a token provider and configuration.

    Each stream is counted against the connection budget when it is created and
    released when it is closed. Streams are not connected until entered with
    `async with` or started with `BaseStream.start`.
    """

    def __init__(
        self,
        *,
        config: ClientConfig,
        token_provider: AccessTokenProvider,
        connector: WebSocketConnector,
        budget: ConnectionBudget | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        rng: Callable[[], float] = random.random,
    ) -> None:
        self._config: ClientConfig = config
        self._provider: AccessTokenProvider = token_provider
        self._connector: WebSocketConnector = connector
        self._budget: ConnectionBudget = budget or ConnectionBudget(
            enforce=config.stream.enforce_connection_caps
        )
        self._clock: Callable[[], float] = clock
        self._sleep: Callable[[float], Awaitable[None]] = sleep
        self._rng: Callable[[], float] = rng
        self._open: set[BaseStream[object]] = set()

    @property
    def budget(self) -> ConnectionBudget:
        """The connection budget the factory counts streams against."""
        return self._budget

    def _connection(
        self,
        path: str,
        service: Service,
        on_open: Callable[[WebSocketConnection], Awaitable[None]] | None = None,
    ) -> WebSocketConnection:
        self._budget.acquire(service)
        return WebSocketConnection(
            f"{self._config.ws_base_url}{path}",
            token_provider=self._provider,
            connector=self._connector,
            reconnect=self._config.reconnect,
            options=self._config.stream,
            on_open=on_open,
            clock=self._clock,
            sleep=self._sleep,
            rng=self._rng,
        )

    def _release(self, service: Service, stream: BaseStream[object]) -> None:
        self._budget.release(service)
        self._open.discard(stream)

    def _track[S: BaseStream[object]](self, stream: S, service: Service) -> S:
        self._open.add(stream)
        return stream

    def market_data(self) -> MarketDataStream:
        """Return a market-data stream with no subscriptions."""
        holder: list[MarketDataStream] = []

        async def on_open(_: WebSocketConnection) -> None:
            await holder[0].resubscribe()

        service = Service.MARKET_DATA
        stream = MarketDataStream(
            self._connection(MARKET_DATA_PATH, service, on_open),
            on_close=lambda: self._release(service, holder[0]),
        )
        holder.append(stream)
        return self._track(stream, service)

    def quotes(self, instruments: Iterable[InstrumentLike]) -> MarketDataStream:
        """Return a market-data stream that subscribes to quotes on connection."""
        stream = self.market_data()
        stream.subscriptions.add(_keys(DataType.QUOTES, instruments, None))
        return stream

    def order_book(
        self, instruments: Iterable[InstrumentLike], *, depth: int = 20
    ) -> MarketDataStream:
        """Return a market-data stream that subscribes to order books on connection."""
        stream = self.market_data()
        stream.subscriptions.add(_keys(DataType.ORDER_BOOK, instruments, depth))
        return stream

    def candles(
        self, instruments: Iterable[InstrumentLike], *, timeframe: TimeFrame
    ) -> MarketDataStream:
        """Return a market-data stream that subscribes to candles on connection."""
        stream = self.market_data()
        stream.subscriptions.add(_keys(DataType.CANDLES, instruments, timeframe.value))
        return stream

    def last_trades(self, instruments: Iterable[InstrumentLike]) -> MarketDataStream:
        """Return a market-data stream that subscribes to last trades on connection."""
        stream = self.market_data()
        stream.subscriptions.add(_keys(DataType.LAST_TRADES, instruments, None))
        return stream

    def _push_stream[S: BaseStream[object]](
        self, cls: Callable[..., S], path: str, service: Service
    ) -> S:
        holder: list[S] = []
        stream = cls(
            self._connection(path, service), on_close=lambda: self._release(service, holder[0])
        )
        holder.append(stream)
        return self._track(stream, service)

    def orders_events(self) -> OrdersEventsStream:
        """Return a stream of the account's order events."""
        return self._push_stream(OrdersEventsStream, ORDERS_EVENTS_PATH, Service.OPERATIONS)

    def portfolio(self) -> PortfolioStream:
        """Return a stream of portfolio snapshots."""
        return self._push_stream(PortfolioStream, PORTFOLIO_PATH, Service.PORTFOLIO)

    def limits(self) -> LimitsStream:
        """Return a stream of limits snapshots."""
        return self._push_stream(LimitsStream, LIMITS_PATH, Service.LIMIT)

    def margin(self) -> MarginStream:
        """Return a stream of margin indicator snapshots."""
        return self._push_stream(MarginStream, MARGIN_PATH, Service.MARGINAL_INDICATORS)

    async def aclose(self) -> None:
        """Close every open stream this factory created."""
        for stream in list(self._open):
            await stream.aclose()


def _keys(
    data_type: DataType,
    instruments: Iterable[InstrumentLike],
    param: str | int | None,
) -> list[SubscriptionKey]:
    return [
        (data_type, key.ticker, key.class_code, param)
        for key in InstrumentKey.coerce_all(instruments)
    ]
