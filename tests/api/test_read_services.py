"""Portfolio, limits, margin, instruments and market data services."""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import TYPE_CHECKING, assert_type

import pytest

from bacsy.api import InstrumentsService, LimitsService, MarginService, MarketDataService
from bacsy.api.portfolio import PortfolioService
from bacsy.exceptions import ProtocolError
from bacsy.models import (
    BasePosition,
    Bond,
    Equity,
    EquityPosition,
    InstrumentKey,
    InstrumentPosition,
    InstrumentType,
    MoneyPosition,
    Option,
    OptionType,
    Portfolio,
    PositionType,
    SecurityTradingStatus,
    SessionStatus,
    Side,
    Term,
    TimeFrame,
    UnknownInstrument,
    UpperType,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from bacsy.http import ApiHttpClient
    from tests.api.conftest import Recorder

POSITION = {
    "account": "X",
    "ticker": "SBER",
    "displayName": "Сбербанк",
    "board": "TQBR",
    "currency": "RUB",
    "type": "depoLimit",
    "term": "T2",
    "upperType": "RUSSIA",
    "quantity": 10,
    "currentPrice": 312.45,
    "currentValue": 3124.5,
    "dailyPL": -1.5,
    "expireDate": "",
    "isBlocked": False,
    "scale": 2,
}


async def test_portfolio(transport: ApiHttpClient, recorder: Recorder) -> None:
    recorder.reply([POSITION])

    portfolio = await PortfolioService(transport).get()

    assert recorder.last.method == "GET"
    assert recorder.last.url.path == "/trade-api-bff-portfolio/api/v1/portfolio"
    assert isinstance(portfolio, Portfolio)
    assert portfolio.terms == [Term.T2]
    position = portfolio.lines[0]
    assert isinstance(position, EquityPosition)
    assert position.type is PositionType.DEPO_LIMIT
    assert position.term is Term.T2
    assert position.upper_type is UpperType.RUSSIA
    assert position.key == InstrumentKey(ticker="SBER", class_code="TQBR")
    assert position.current_price == Decimal("312.45")
    assert position.current_value.value == Decimal("3124.5")
    assert position.daily_pl.amount == Decimal("-1.5")
    assert position.daily_pl.percent is None
    assert position.quantity == 10


async def test_portfolio_positions_select_one_term(
    transport: ApiHttpClient, recorder: Recorder
) -> None:
    lines = [
        {**POSITION, "term": term, "ticker": ticker}
        for ticker in ("SBER", "RUB")
        for term in ("T0", "T1", "T2", "T365")
    ]
    recorder.reply(lines)
    recorder.reply(lines)

    service = PortfolioService(transport)
    planned = await service.get_positions()
    settled = await service.get_positions(Term.T0)

    assert len(recorder.requests) == 2
    assert [(p.display_name, p.term) for p in planned] == [
        ("Сбербанк", Term.T365),
        ("Сбербанк", Term.T365),
    ]
    assert [p.term for p in settled] == [Term.T0, Term.T0]
    assert [p.key for p in service_positions(planned)] == [
        InstrumentKey(ticker="SBER", class_code="TQBR"),
        InstrumentKey(ticker="RUB", class_code="TQBR"),
    ]


def service_positions(positions: Sequence[BasePosition]) -> list[EquityPosition]:
    return [p for p in positions if isinstance(p, EquityPosition)]


async def test_portfolio_rejects_wrong_shape(transport: ApiHttpClient, recorder: Recorder) -> None:
    recorder.reply({"not": "a list"})

    with pytest.raises(ProtocolError) as info:
        await PortfolioService(transport).get()

    assert info.value.source == "portfolio"
    assert info.value.payload == {"not": "a list"}


async def test_limits(transport: ApiHttpClient, recorder: Recorder) -> None:
    recorder.reply(
        {
            "depoLimit": [
                {
                    "ticker": "SBER",
                    "classCode": "TQBR",
                    "quantity": {"type": "T2", "value": 10},
                    "quantityBatch": {"type": "T2", "value": 1},
                    "lockedBuyQuantity": 0,
                    "loadDate": "2024-10-29T21:00:00.000Z",
                }
            ],
            "futureHolding": [],
            "futuresLimits": [{"currencyCode": "SUR", "cbpLimit": 100.5, "accruedint": 1.25}],
            "moneyLimits": [{"currencyCode": "SUR", "quantity": {"type": "T0", "value": 1000.75}}],
        }
    )

    limits = await LimitsService(transport).get()

    assert recorder.last.url.path == "/trade-api-bff-limit/api/v1/limits"
    depo = limits.depo_limit[0]
    assert depo.key == InstrumentKey(ticker="SBER", class_code="TQBR")
    assert depo.board is not None
    assert depo.board.exchange is None
    assert depo.quantity is not None
    assert depo.quantity.type is Term.T2
    assert depo.quantity.value == 10
    assert depo.load_date == date(2024, 10, 30)
    assert limits.futures_limits[0].accrued_int == Decimal("1.25")
    money = limits.money_limits[0]
    assert money.quantity is not None
    assert money.quantity.value == Decimal("1000.75")


async def test_margin(transport: ApiHttpClient, recorder: Recorder) -> None:
    recorder.reply([{"ticker": "SBER", "discountLong": 0.2, "discountShort": 0.25}])

    discounts = await MarginService(transport).get_instrument_discounts()

    assert recorder.last.url.path == (
        "/trade-api-bff-marginal-indicators/api/v1/instruments-discounts"
    )
    assert discounts[0].discount_long == Decimal("0.2")


INSTRUMENT = {
    "ticker": "SBER",
    "isin": "RU0009029540",
    "type": "Акции обыкновенные",
    "instrumentType": "STOCK",
    "displayName": "Сбербанк",
    "primaryBoard": "TQBR",
    "secondaryBoards": ["SMAL"],
    "boards": [{"classCode": "TQBR", "exchange": "MOEX"}],
    "lotSize": 10,
    "minimumStep": 0.01,
    "scale": 2,
    "isCanShort": True,
    "maturityDate": "20300101",
    "emissionDate": "1970-01-01",
    "settlementDate": "2026-03-05T00:00:00.000Z",
    "nextCoupon": "2026-03-05T21:00:00.000Z",
    "cfi": "ignored",
}


async def test_instruments_by_tickers(transport: ApiHttpClient, recorder: Recorder) -> None:
    recorder.reply([INSTRUMENT])

    result = await InstrumentsService(transport).get_by_tickers(["SBER"], page=1, size=20)

    assert recorder.last.method == "POST"
    assert recorder.last.url.path == "/trade-api-information-service/api/v1/instruments/by-tickers"
    assert dict(recorder.last.url.params) == {"page": "1", "size": "20"}
    assert recorder.last_json() == {"tickers": ["SBER"]}
    instrument = result[0]
    assert isinstance(instrument, Equity)
    assert instrument.instrument_type is InstrumentType.STOCK
    assert instrument.type_name == "Акции обыкновенные"
    assert instrument.key == InstrumentKey(ticker="SBER", class_code="TQBR")
    assert instrument.keys == [
        InstrumentKey(ticker="SBER", class_code="TQBR"),
        InstrumentKey(ticker="SBER", class_code="SMAL"),
    ]
    assert instrument.listing.boards[0].exchange == "MOEX"
    assert instrument.trading.minimum_step == Decimal("0.01")
    assert instrument.emission_date is None
    assert instrument.listing.settlement_date == date(2026, 3, 5)


async def test_instruments_by_isins_return_bonds(
    transport: ApiHttpClient, recorder: Recorder
) -> None:
    recorder.reply([BOND])

    result = await InstrumentsService(transport).get_by_isins(["RU000A101Q26"])

    bond = result[0]
    assert isinstance(bond, Bond)
    assert bond.maturity_date == date(2030, 5, 15)
    assert bond.next_coupon == date(2026, 11, 18)
    assert bond.accrued_interest == Decimal("54.36")
    assert bond.issuer.name == "ПАО АФК Система"
    assert bond.analytics.market_cap == Decimal("68968550000")


BOND = {
    "ticker": "RU000A101Q26",
    "isin": "RU000A101Q26",
    "type": "Облигации корпоративные",
    "instrumentType": "BONDS",
    "subType": "AST_CORP",
    "primaryBoard": "TQCB",
    "boards": [{"classCode": "TQCB", "exchange": "MOEX"}],
    "issuerName": "ПАО АФК Система",
    "faceValue": 1000,
    "currencyNominal": "RUB",
    "couponRate": 16,
    "couponsPerYear": 2,
    "accruedInt": 54.36,
    "maturityDate": "20300515",
    "nextCoupon": "2026-11-17T21:00:00.000Z",
    "mktcap": 68968550000,
}


async def test_instruments_by_isins(transport: ApiHttpClient, recorder: Recorder) -> None:
    recorder.reply([INSTRUMENT])

    await InstrumentsService(transport).get_by_isins(["RU0009029540"])

    assert recorder.last.url.path == "/trade-api-information-service/api/v1/instruments/by-isins"
    assert recorder.last_json() == {"isins": ["RU0009029540"]}
    assert dict(recorder.last.url.params) == {"page": "0", "size": "100"}


async def test_instruments_by_type(transport: ApiHttpClient, recorder: Recorder) -> None:
    recorder.reply([{**INSTRUMENT, "instrumentType": "OPTIONS", "subType": "AST_OPT_PUT"}])

    options = await InstrumentsService(transport).get_by_type(
        InstrumentType.OPTIONS, base_asset_ticker="SBER", size=50
    )

    assert_type(options, list[Option])
    assert options[0].option_type is OptionType.PUT
    assert recorder.last.method == "GET"
    assert dict(recorder.last.url.params) == {
        "type": "OPTIONS",
        "baseAssetTicker": "SBER",
        "page": "0",
        "size": "50",
    }


async def test_instruments_by_type_rejects_another_type(
    transport: ApiHttpClient, recorder: Recorder
) -> None:
    recorder.reply([INSTRUMENT])

    with pytest.raises(ProtocolError):
        await InstrumentsService(transport).get_by_type(InstrumentType.FUTURES)


async def test_instruments_by_unknown_type_returns_the_union(
    transport: ApiHttpClient, recorder: Recorder
) -> None:
    recorder.reply([{**INSTRUMENT, "instrumentType": "NEW"}])

    result = await InstrumentsService(transport).get_by_type(InstrumentType("NEW"))

    assert isinstance(result[0], UnknownInstrument)


async def test_iter_by_type_stops_on_short_page(
    transport: ApiHttpClient, recorder: Recorder
) -> None:
    recorder.reply([INSTRUMENT, INSTRUMENT])
    recorder.reply([INSTRUMENT])

    items = [
        i async for i in InstrumentsService(transport).iter_by_type(InstrumentType.ETF, size=2)
    ]

    assert_type(items, list[Equity])
    assert len(items) == 3
    assert [r.url.params["page"] for r in recorder.requests] == ["0", "1"]


async def test_lookup_matches_keys_against_boards(
    transport: ApiHttpClient, recorder: Recorder
) -> None:
    other = {**INSTRUMENT, "primaryBoard": "SPBRU", "boards": [{"classCode": "SPBRU"}]}
    recorder.reply([INSTRUMENT, other, {**BOND, "primaryBoard": "BQMEO", "boards": []}])

    found = await InstrumentsService(transport).lookup(
        [
            InstrumentKey(ticker="SBER", class_code="SMAL"),
            InstrumentKey(ticker="SBER", class_code="SPBRU"),
            InstrumentKey(ticker="RU000A101Q26", class_code="TQCB"),
            InstrumentKey(ticker="NOPE", class_code="TQBR"),
        ]
    )

    assert recorder.last_json() == {"tickers": ["NOPE", "RU000A101Q26", "SBER"]}
    assert found[InstrumentKey(ticker="SBER", class_code="SMAL")].listing.primary_board == "TQBR"
    assert found[InstrumentKey(ticker="SBER", class_code="SPBRU")].listing.primary_board == "SPBRU"
    bond = found[InstrumentKey(ticker="RU000A101Q26", class_code="TQCB")]
    assert isinstance(bond, Bond)
    assert bond.listing.primary_board == "BQMEO"
    assert InstrumentKey(ticker="NOPE", class_code="TQBR") not in found


async def test_lookup_accepts_positions_and_pages(
    transport: ApiHttpClient, recorder: Recorder
) -> None:
    portfolio = Portfolio.model_validate([POSITION])
    recorder.reply([INSTRUMENT] * 100)
    recorder.reply([])

    found = await InstrumentsService(transport).lookup(
        portfolio.select(InstrumentPosition, Term.T2)
    )

    assert [r.url.params["page"] for r in recorder.requests] == ["0", "1"]
    assert list(found) == [InstrumentKey(ticker="SBER", class_code="TQBR")]


async def test_lookup_rejects_a_position_without_a_key(transport: ApiHttpClient) -> None:
    money, stock = Portfolio.model_validate(
        [{"type": "moneyLimit", "ticker": "RUB"}, {"type": "depoLimit", "ticker": "SBER"}]
    ).lines
    assert isinstance(money, MoneyPosition)

    with pytest.raises(TypeError, match="does not name an instrument"):
        await InstrumentsService(transport).lookup([money])  # pyright: ignore[reportArgumentType]
    with pytest.raises(ValueError, match="no instrument key"):
        await InstrumentsService(transport).lookup([stock])  # pyright: ignore[reportArgumentType]


@pytest.mark.parametrize(("page", "size"), [(-1, 10), (0, 0), (0, 101)])
async def test_page_arguments_are_validated(transport: ApiHttpClient, page: int, size: int) -> None:
    with pytest.raises(ValueError, match=r"page|size"):
        await InstrumentsService(transport).get_by_tickers(["SBER"], page=page, size=size)


async def test_daily_schedule(transport: ApiHttpClient, recorder: Recorder) -> None:
    recorder.reply(
        {
            "isWorkDay": True,
            "dailySchedule": [
                {
                    "startDate": "09:50:00",
                    "endDate": "10:00:00",
                    "tradingSessionStatus": "OPEN",
                    "tradingSessionType": "Аукцион открытия",
                }
            ],
        }
    )

    schedule = await InstrumentsService(transport).get_daily_schedule(
        ticker="SBER", class_code="TQBR"
    )

    assert dict(recorder.last.url.params) == {"ticker": "SBER", "classCode": "TQBR"}
    session = schedule.daily_schedule[0]
    assert session.start_date == time(9, 50)
    assert session.trading_session_status is SessionStatus.OPEN


async def test_trading_status(transport: ApiHttpClient, recorder: Recorder) -> None:
    recorder.reply(
        {
            "tradingSessionStatus": "CLOSE",
            "tradingSessionType": "Weekend",
            "tradingSessionTypeId": 3,
            "nextSessionDate": "2024-10-31T06:50:00Z",
        }
    )

    status = await InstrumentsService(transport).get_trading_status(class_code="TQBR")

    assert recorder.last.url.path == (
        "/trade-api-information-service/api/v1/trading-schedule/status"
    )
    assert status.trading_session_status is SessionStatus.CLOSE
    assert status.next_session_date == datetime(2024, 10, 31, 6, 50, tzinfo=UTC)


async def test_quotes(transport: ApiHttpClient, recorder: Recorder) -> None:
    recorder.reply(
        {
            "records": [
                {
                    "ticker": "SBER",
                    "classCode": "TQBR",
                    "dateTime": "2024-10-30T09:01:00.000Z",
                    "securityTradingStatus": 17,
                    "bid": 244.35,
                    "offer": 244.4,
                    "last": 244.37,
                    "changeRate": -0.12,
                }
            ]
        }
    )

    quotes = await MarketDataService(transport).get_quotes(
        [
            InstrumentKey(ticker="SBER", class_code="TQBR"),
            InstrumentKey(ticker="GAZP", class_code="TQBR"),
        ]
    )

    assert recorder.last.url.path == "/trade-api-market-data-connector/api/v1/quotes"
    assert recorder.last_json() == {
        "instruments": [
            {"ticker": "SBER", "classCode": "TQBR"},
            {"ticker": "GAZP", "classCode": "TQBR"},
        ]
    }
    assert quotes[0].security_trading_status is SecurityTradingStatus.OPEN
    assert quotes[0].bid == Decimal("244.35")


async def test_quotes_limits_batch_size(transport: ApiHttpClient) -> None:
    with pytest.raises(ValueError, match="between 1 and 100"):
        await MarketDataService(transport).get_quotes([])
    with pytest.raises(ValueError, match="between 1 and 100"):
        await MarketDataService(transport).get_quotes(
            [InstrumentKey(ticker="A", class_code="B")] * 101
        )


async def test_order_book(transport: ApiHttpClient, recorder: Recorder) -> None:
    recorder.reply(
        {
            "ticker": "SBER",
            "classCode": "TQBR",
            "depth": 2,
            "dateTime": "2024-10-30T09:01:00.000Z",
            "bidVolume": "59851",
            "askVolume": 90339,
            "bids": [{"price": 244.35, "quantity": 100}],
            "asks": [{"price": 244.4, "quantity": 50}],
        }
    )

    book = await MarketDataService(transport).get_order_book(
        ticker="SBER", class_code="TQBR", depth=2
    )

    assert dict(recorder.last.url.params) == {"ticker": "SBER", "classCode": "TQBR", "depth": "2"}
    assert book.bid_volume == Decimal("59851")
    assert book.bids[0].price == Decimal("244.35")
    assert book.asks[0].quantity == 50


async def test_order_book_depth_validation(transport: ApiHttpClient) -> None:
    with pytest.raises(ValueError, match="depth"):
        await MarketDataService(transport).get_order_book(ticker="S", class_code="T", depth=21)


async def test_candles(transport: ApiHttpClient, recorder: Recorder) -> None:
    recorder.reply(
        {
            "ticker": "SBER",
            "classCode": "TQBR",
            "timeFrame": "H1",
            "startDate": "2025-11-14T07:00:00Z",
            "endDate": "2025-11-14T10:00:00Z",
            "bars": [
                {
                    "time": "2025-11-14T07:00:00Z",
                    "open": 1.5,
                    "high": 2,
                    "low": 1,
                    "close": 1.75,
                    "volume": 1000,
                }
            ],
        }
    )

    chart = await MarketDataService(transport).get_candles(
        ticker="SBER",
        class_code="TQBR",
        timeframe=TimeFrame.H1,
        start=datetime(2025, 11, 14, 7, tzinfo=UTC),
        end=datetime(2025, 11, 14, 10, 0, 0, 500000, tzinfo=UTC),
    )

    assert dict(recorder.last.url.params) == {
        "ticker": "SBER",
        "classCode": "TQBR",
        "timeFrame": "H1",
        "startDate": "2025-11-14T07:00:00Z",
        "endDate": "2025-11-14T10:00:00.500Z",
    }
    assert chart.time_frame is TimeFrame.H1
    assert chart.bars[0].close == Decimal("1.75")
    assert chart.bars[0].time == datetime(2025, 11, 14, 7, tzinfo=UTC)


async def test_last_trades(transport: ApiHttpClient, recorder: Recorder) -> None:
    recorder.reply(
        {
            "records": [
                {
                    "dateTime": "2024-10-30T09:01:00.000Z",
                    "price": 244.35,
                    "quantity": 10,
                    "side": "2",
                    "volume": 2443,
                }
            ]
        }
    )

    trades = await MarketDataService(transport).get_last_trades(
        ticker="SBER",
        class_code="TQBR",
        side=Side.SELL,
        start=datetime(2024, 10, 30, tzinfo=UTC),
    )

    assert recorder.last_json() == {
        "ticker": "SBER",
        "classCode": "TQBR",
        "side": "2",
        "startDateTime": "2024-10-30T00:00:00Z",
    }
    assert trades[0].side is Side.SELL
    assert trades[0].price == Decimal("244.35")
