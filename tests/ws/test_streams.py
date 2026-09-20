"""Typed streams, the market-data registry and the factory's connection budget."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

import httpx
import pytest

from bacsy import ClientConfig, StreamOptions, TradeApiClient
from bacsy.auth import StaticAccessTokenProvider
from bacsy.exceptions import ProtocolError, StreamLimitError
from bacsy.models import (
    CandleEvent,
    DataType,
    InstrumentKey,
    LastTradeEvent,
    OrderBookEvent,
    OrderStatus,
    QuoteEvent,
    Reconnected,
    StreamErrorCode,
    SubscriptionAck,
    SubscriptionError,
    TimeFrame,
    TradeSide,
    UnknownEvent,
)
from bacsy.routes import Service
from bacsy.ws import StreamFactory, parse_market_data_event
from tests.ws.fakes import FakeConnector, FakeWebSocket

if TYPE_CHECKING:
    from tests.conftest import FakeClock


@pytest.fixture
def connector() -> FakeConnector:
    return FakeConnector()


@pytest.fixture
def factory(connector: FakeConnector, fake_clock: FakeClock) -> StreamFactory:
    return StreamFactory(
        config=ClientConfig(stream=StreamOptions(send_rate=1000)),
        token_provider=StaticAccessTokenProvider("tok"),
        connector=connector,
        clock=fake_clock,
        sleep=fake_clock.sleep,
    )


async def test_orders_events_stream(factory: StreamFactory, connector: FakeConnector) -> None:
    async with factory.orders_events() as stream:
        connector.current.push(
            {
                "originalClientOrderId": "abc",
                "clientOrderId": "",
                "data": {"orderStatus": "2", "executedQuantity": 100, "averagePrice": 244.5},
            }
        )
        event = await anext(stream)

    assert (
        connector.calls[0][0]
        == "wss://ws.broker.ru/trade-api-bff-operations/api/v1/orders/events/ws"
    )
    assert not isinstance(event, Reconnected)
    assert event.original_client_order_id == "abc"
    assert event.client_order_id is None
    assert event.data.order_status is OrderStatus.FILLED
    assert event.data.average_price == Decimal("244.5")


async def test_portfolio_limits_and_margin_streams(
    factory: StreamFactory, connector: FakeConnector
) -> None:
    async with factory.portfolio() as portfolio:
        connector.current.push([{"ticker": "SBER", "quantity": 2}])
        positions = await anext(portfolio)
    async with factory.limits() as limits:
        connector.current.push({"moneyLimits": [{"currencyCode": "RUB"}]})
        snapshot = await anext(limits)
    async with factory.margin() as margin:
        connector.current.push(
            {
                "portfolioCurrentValue": {"currentValueRub": 8086.59},
                "cashByCurrency": [{"currency": "RUB", "sum": 4544.79}],
                "marginSecurities": {"marginBySecurity": [{"ticker": "SBER", "discount": 20}]},
            }
        )
        indicators = await anext(margin)

    assert not isinstance(positions, Reconnected)
    assert positions.lines[0].quantity == 2
    assert not isinstance(snapshot, Reconnected)
    assert snapshot.money_limits[0].currency_code == "RUB"
    assert not isinstance(indicators, Reconnected)
    assert indicators.portfolio_current_value is not None
    assert indicators.portfolio_current_value.current_value_rub == Decimal("8086.59")
    assert indicators.margin_securities is not None
    assert indicators.margin_securities.margin_by_security[0].discount == 20


async def test_invalid_frame_raises_but_stream_continues(
    factory: StreamFactory, connector: FakeConnector
) -> None:
    async with factory.limits() as stream:
        connector.current.push([1, 2, 3])
        connector.current.push({"depoLimit": []})
        with pytest.raises(ProtocolError) as info:
            await anext(stream)
        event = await anext(stream)

    assert info.value.source == "limits"
    assert not isinstance(event, Reconnected)
    assert event.depo_limit == []


async def test_market_data_subscribe_and_events(
    factory: StreamFactory, connector: FakeConnector
) -> None:
    async with factory.market_data() as stream:
        await stream.subscribe_quotes([InstrumentKey(ticker="SBER", class_code="TQBR")])
        await stream.subscribe_order_book(
            [InstrumentKey(ticker="GAZP", class_code="TQBR")], depth=5
        )
        await stream.subscribe_candles(
            [InstrumentKey(ticker="SBER", class_code="TQBR")], timeframe=TimeFrame.M1
        )
        await stream.subscribe_last_trades([InstrumentKey(ticker="SBER", class_code="TQBR")])

        assert connector.current.sent_json() == [
            {
                "subscribeType": 0,
                "dataType": 3,
                "instruments": [{"ticker": "SBER", "classCode": "TQBR"}],
            },
            {
                "subscribeType": 0,
                "dataType": 0,
                "instruments": [{"ticker": "GAZP", "classCode": "TQBR"}],
                "depth": 5,
            },
            {
                "subscribeType": 0,
                "dataType": 1,
                "instruments": [{"ticker": "SBER", "classCode": "TQBR"}],
                "timeFrame": "M1",
            },
            {
                "subscribeType": 0,
                "dataType": 2,
                "instruments": [{"ticker": "SBER", "classCode": "TQBR"}],
            },
        ]
        assert len(stream.subscriptions) == 4

        connector.current.push(
            {"responseType": "OrderBookSuccess", "subscribeType": 0, "ticker": "GAZP", "depth": 5}
        )
        connector.current.push(
            {"responseType": "Quotes", "ticker": "SBER", "type": "refresh", "last": 305.97}
        )
        connector.current.push(
            {
                "responseType": "OrderBook",
                "ticker": "GAZP",
                "bidVolume": "59851",
                "bids": [{"price": 244.30, "quantity": 100}],
                "asks": [],
            }
        )
        connector.current.push(
            {"responseType": "CandleStick", "ticker": "SBER", "timeFrame": "M1", "close": 244.5}
        )
        connector.current.push(
            {"responseType": "LastTrades", "ticker": "SBER", "side": "BUY", "price": 305.89}
        )
        connector.current.push(
            {"responseType": "Quotes", "errors": [{"message": "bad", "code": "NOT_FOUND"}]}
        )
        connector.current.push({"responseType": "Surprise", "x": 1})
        events = [await anext(stream) for _ in range(7)]

        await stream.unsubscribe_quotes([InstrumentKey(ticker="SBER", class_code="TQBR")])
        assert connector.current.sent_json()[-1]["subscribeType"] == 1  # pyright: ignore[reportIndexIssue]
        assert len(stream.subscriptions) == 3

    ack, quote, book, candle, trade, error, unknown = events
    assert isinstance(ack, SubscriptionAck)
    assert ack.depth == 5
    assert isinstance(quote, QuoteEvent)
    assert quote.last == Decimal("305.97")
    assert isinstance(book, OrderBookEvent)
    assert book.bid_volume == Decimal("59851")
    assert book.bids[0].price == Decimal("244.30")
    assert isinstance(candle, CandleEvent)
    assert candle.time_frame is TimeFrame.M1
    assert isinstance(trade, LastTradeEvent)
    assert trade.side is TradeSide.BUY
    assert isinstance(error, SubscriptionError)
    assert error.errors[0].code is StreamErrorCode.NOT_FOUND
    assert isinstance(unknown, UnknownEvent)
    assert unknown.response_type == "Surprise"


def test_parse_rejects_non_object() -> None:
    with pytest.raises(ProtocolError):
        parse_market_data_event([1])


async def test_convenience_constructors_subscribe_on_open(
    factory: StreamFactory, connector: FakeConnector
) -> None:
    stream = factory.order_book(
        [
            InstrumentKey(ticker="SBER", class_code="TQBR"),
            InstrumentKey(ticker="GAZP", class_code="TQBR"),
        ],
        depth=10,
    )
    assert connector.calls == []

    async with stream:
        pass

    assert connector.sockets[0].sent_json() == [
        {
            "subscribeType": 0,
            "dataType": 0,
            "instruments": [
                {"ticker": "GAZP", "classCode": "TQBR"},
                {"ticker": "SBER", "classCode": "TQBR"},
            ],
            "depth": 10,
        }
    ]


async def test_resubscribes_after_reconnect(
    factory: StreamFactory, connector: FakeConnector
) -> None:
    connector.outcomes = [FakeWebSocket(), FakeWebSocket()]
    async with factory.quotes([InstrumentKey(ticker="SBER", class_code="TQBR")]) as stream:
        await stream.subscribe_candles(
            [InstrumentKey(ticker="SBER", class_code="TQBR")], timeframe=TimeFrame.H1
        )
        connector.sockets[0].drop()

        marker = await anext(stream)

        assert isinstance(marker, Reconnected)
        assert sorted(str(m) for m in connector.sockets[1].sent_json()) == sorted(
            str(m)
            for m in [
                {
                    "subscribeType": 0,
                    "dataType": 3,
                    "instruments": [{"ticker": "SBER", "classCode": "TQBR"}],
                },
                {
                    "subscribeType": 0,
                    "dataType": 1,
                    "instruments": [{"ticker": "SBER", "classCode": "TQBR"}],
                    "timeFrame": "H1",
                },
            ]
        )


async def test_subscription_cap(factory: StreamFactory) -> None:
    stream = factory.market_data()
    instruments = [(f"T{i}", "TQBR") for i in range(100)]
    stream.subscriptions.add((DataType.QUOTES, t, c, None) for t, c in instruments)

    with pytest.raises(StreamLimitError, match="100"):
        await stream.subscribe_quotes([InstrumentKey(ticker="ONE_MORE", class_code="TQBR")])
    await stream.subscribe_quotes(
        [InstrumentKey(ticker="T1", class_code="TQBR")]
    )  # already registered: allowed


async def test_depth_validation(factory: StreamFactory) -> None:
    with pytest.raises(ValueError, match="depth"):
        await factory.market_data().subscribe_order_book(
            [InstrumentKey(ticker="S", class_code="T")], depth=0
        )


async def test_connection_budget(factory: StreamFactory) -> None:
    first = factory.portfolio()
    second = factory.portfolio()
    with pytest.raises(StreamLimitError, match="2 concurrent"):
        factory.portfolio()

    await first.aclose()
    third = factory.portfolio()
    await second.aclose()
    await third.aclose()
    assert factory.budget.in_use(Service.PORTFOLIO) == 0


async def test_client_closes_its_streams() -> None:
    connector = FakeConnector()
    http = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200)))
    client = TradeApiClient.from_access_token("t", http=http, ws_connector=connector)
    stream = client.streams.limits()
    await stream.start()

    await client.aclose()

    assert connector.current.closed
    await http.aclose()
