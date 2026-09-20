"""The position hierarchy: one class per kind, chosen from the wire ``type``."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from bacsy.models import (
    PERPETUAL_EXPIRY,
    Board,
    BondPosition,
    CashPosition,
    EquityPosition,
    FuturesMoneyPosition,
    FuturesPosition,
    InstrumentKey,
    InstrumentPosition,
    InstrumentType,
    MoneyPosition,
    OtcPosition,
    Portfolio,
    PositionType,
    SecurityPosition,
    UnknownPosition,
)

MONEY = {
    "type": "moneyLimit",
    "ticker": "CNY",
    "displayName": "CNY",
    "board": "",
    "exchange": "MOEX",
    "currency": "CNY",
    "instrumentType": "CURRENCY",
    "upperType": "CURRENCY",
    "term": "T365",
    "quantity": "404.42",
    "locked": "0.0",
    "balancePrice": "10.7832",
    "currentPrice": "12.587",
    "balanceValue": "404.42",
    "balanceValueRub": "4360.9515",
    "balanceValueUsd": "51.6974",
    "balanceValueEur": "44.9598",
    "currentValue": "404.42",
    "currentValueRub": "5090.4345",
    "currentValueUsd": "60.3452",
    "currentValueEur": "52.4805",
    "dailyPL": "0.0",
    "dailyPercentPL": "0.0",
    "unrealizedPL": "57.9553",
    "unrealizedPercentPL": "16.7276",
    "faceValue": "0.0",
    "accruedIncome": "0.0",
    "scale": 4,
    "minimumStep": "0.01",
}

STOCK = {
    "type": "depoLimit",
    "ticker": "PHOR",
    "displayName": "ФосАгро",
    "board": "TQBR",
    "exchange": "MOEX",
    "currency": "RUB",
    "instrumentType": "STOCK",
    "upperType": "RUSSIA",
    "term": "T365",
    "quantity": "30.0",
    "balancePrice": "6421.6667",
    "currentPrice": "5169.0",
    "currentValue": "155070.0",
    "currentValueRub": "155070.0",
    "unrealizedPL": "-37580.0",
    "unrealizedPercentPL": "-19.5069",
    "faceValue": "2.5",
    "accruedIncome": "0.0",
    "ratioQuantity": "0.0",
    "scale": 0,
    "minimumStep": "1.0",
    "priceUnit": "",
}

BOND = {
    "type": "depoLimit",
    "ticker": "RU000A1056U0",
    "displayName": "Gazprom capital ZO27-1-D USD",
    "board": "TQCB",
    "exchange": "MOEX",
    "currency": "RUB",
    "instrumentType": "BONDS",
    "upperType": "RUSSIA",
    "term": "T365",
    "quantity": "1.0",
    "balancePrice": "82203.6494",
    "currentPrice": "82752.5493",
    "currentValue": "84821.337",
    "currentValueRub": "84821.337",
    "faceValue": "1000.0",
    "accruedIncome": "2068.787664",
    "priceUnit": "%",
    "scale": 4,
    "minimumStep": "0.00010",
}

FUTURE = {
    "type": "futuresHolding",
    "ticker": "USDRUBF",
    "displayName": "USDRUBF",
    "board": "SPBFUT",
    "exchange": "FORTS",
    "currency": "RUB",
    "instrumentType": "FUTURES",
    "upperType": "RUSSIA",
    "term": "T365",
    "quantity": "-1.0",
    "balancePrice": "84.28",
    "currentPrice": "84.3",
    "currentValue": "-84300.0",
    "unrealizedPL": "-20.0",
    "unrealizedPercentPL": "-0.0237",
    "lockedForFutures": "11380.5",
    "ratioQuantity": "1000.0",
    "expireDate": "2099-12-31T21:00:00Z",
    "baseAssetTicker": "",
}


def only(portfolio: Portfolio) -> object:
    assert len(portfolio.lines) == 1
    return portfolio.lines[0]


def test_money_position_drops_instrument_fields() -> None:
    money = only(Portfolio.model_validate([MONEY]))

    assert isinstance(money, MoneyPosition)
    assert isinstance(money, CashPosition)
    assert not isinstance(money, InstrumentPosition)
    assert money.type is PositionType.MONEY_LIMIT
    assert money.currency == "CNY"
    assert money.exchange == "MOEX"
    assert money.quantity == Decimal("404.42")
    assert money.current_rate == Decimal("12.587")
    assert money.balance_rate == Decimal("10.7832")
    assert money.current_value.value == Decimal("404.42")
    assert money.current_value.rub == Decimal("5090.4345")
    assert money.unrealized_pl.percent == Decimal("16.7276")
    assert money.locked_for_futures is None
    assert not hasattr(money, "ticker")
    assert not hasattr(money, "face_value")


def test_money_position_carries_the_futures_collateral() -> None:
    money, first, second = Portfolio.model_validate(
        [
            {
                **MONEY,
                "currency": "RUB",
                "quantity": "186163.66",
                "locked": "126778.26",
                "lockedForFutures": "28028.26",
            },
            {**FUTURE, "ticker": "SiH6", "quantity": "1", "lockedForFutures": "9155.15"},
            {**FUTURE, "ticker": "SiM6", "quantity": "2", "lockedForFutures": "18873.11"},
        ]
    ).lines

    assert isinstance(money, MoneyPosition)
    assert isinstance(first, FuturesPosition)
    assert isinstance(second, FuturesPosition)
    assert first.collateral is not None
    assert second.collateral is not None
    assert money.locked_for_futures == first.collateral + second.collateral
    assert money.locked is not None
    assert money.locked_for_futures is not None
    assert money.locked > money.locked_for_futures


def test_equity_position_has_a_key_and_a_board() -> None:
    stock = only(Portfolio.model_validate([STOCK]))

    assert isinstance(stock, EquityPosition)
    assert isinstance(stock, SecurityPosition)
    assert stock.key == InstrumentKey(ticker="PHOR", class_code="TQBR")
    assert stock.board == Board(class_code="TQBR", exchange="MOEX")
    assert stock.instrument_type is InstrumentType.STOCK
    assert stock.face_value == Decimal("2.5")
    assert stock.current_value.usd is None
    assert stock.daily_pl.amount is None
    assert stock.unrealized_pl.amount == Decimal("-37580.0")
    assert not hasattr(stock, "accrued_income")
    assert not hasattr(stock, "ratio_quantity")


def test_bond_position_carries_accrued_income() -> None:
    bond = only(Portfolio.model_validate([BOND]))

    assert isinstance(bond, BondPosition)
    assert bond.instrument_type is InstrumentType.BONDS
    assert bond.face_value == Decimal("1000.0")
    assert bond.accrued_income == Decimal("2068.787664")
    assert bond.accrued_total == Decimal("2068.787664")
    assert bond.price_unit == "%"
    assert bond.current_value.value is not None
    assert bond.quantity is not None
    assert bond.current_price is not None
    assert bond.accrued_income is not None
    total = bond.quantity * (bond.current_price + bond.accrued_income)
    assert abs(bond.current_value.value - total) < Decimal("0.001")


@pytest.mark.parametrize("instrument_type", ["EURO_BONDS", "NOTES"])
def test_every_debt_type_is_a_bond_position(instrument_type: str) -> None:
    bond = only(Portfolio.model_validate([{**BOND, "instrumentType": instrument_type}]))

    assert isinstance(bond, BondPosition)


def test_accrued_total_needs_both_parts() -> None:
    bond = only(Portfolio.model_validate([{**BOND, "accruedIncome": None}]))

    assert isinstance(bond, BondPosition)
    assert bond.accrued_total is None


def test_futures_position_reads_multiplier_expiry_and_collateral() -> None:
    future = only(Portfolio.model_validate([FUTURE]))

    assert isinstance(future, FuturesPosition)
    assert future.key == InstrumentKey(ticker="USDRUBF", class_code="SPBFUT")
    assert future.board == Board(class_code="SPBFUT", exchange="FORTS")
    assert future.quantity == Decimal("-1.0")
    assert future.multiplier == Decimal("1000.0")
    assert future.collateral == Decimal("11380.5")
    assert future.expiry == PERPETUAL_EXPIRY
    assert future.is_perpetual
    assert future.base_asset_ticker is None
    assert future.quantity is not None
    assert future.current_price is not None
    assert future.multiplier is not None
    assert future.current_value.value == future.quantity * future.current_price * future.multiplier
    assert future.unrealized_pl.amount == Decimal("-20.0")


def test_expiring_future_is_dated_in_moscow_time() -> None:
    future = only(Portfolio.model_validate([{**FUTURE, "expireDate": "2026-12-16T21:00:00Z"}]))

    assert isinstance(future, FuturesPosition)
    assert future.expiry == date(2026, 12, 17)
    assert not future.is_perpetual


def test_future_without_expiry_is_not_perpetual() -> None:
    future = only(Portfolio.model_validate([{**FUTURE, "expireDate": ""}]))

    assert isinstance(future, FuturesPosition)
    assert future.expiry is None
    assert not future.is_perpetual


def test_documented_kinds_without_live_shapes() -> None:
    otc, futures_money = Portfolio.model_validate(
        [
            {**STOCK, "type": "otcLimit", "board": "QMEBLCK", "exchange": "Вне биржи"},
            {
                "type": "futuresLimit",
                "currency": "RUB",
                "exchange": "FORTS",
                "quantity": "100.5",
                "currentPrice": "1.0",
                "lockedForFutures": 5,
            },
        ]
    ).lines

    assert isinstance(otc, OtcPosition)
    assert otc.key == InstrumentKey(ticker="PHOR", class_code="QMEBLCK")
    assert otc.face_value == Decimal("2.5")
    assert isinstance(futures_money, FuturesMoneyPosition)
    assert isinstance(futures_money, CashPosition)
    assert futures_money.currency == "RUB"
    assert futures_money.quantity == Decimal("100.5")
    assert futures_money.current_rate == 1
    assert futures_money.locked_for_futures == 5
    assert not hasattr(futures_money, "ticker")
    assert not hasattr(futures_money, "board")


def test_unknown_and_missing_kinds_keep_every_field() -> None:
    weird, untyped = Portfolio.model_validate(
        [
            {**BOND, "type": "repoLimit", "expireDate": "2026-12-16T21:00:00Z"},
            {"ticker": "SBER", "quantity": 2},
        ]
    ).lines

    assert isinstance(weird, UnknownPosition)
    assert weird.type is not None
    assert not weird.type.is_known
    assert weird.ticker == "RU000A1056U0"
    assert weird.board == "TQCB"
    assert weird.accrued_income == Decimal("2068.787664")
    assert weird.expire_date == date(2026, 12, 17)
    assert weird.current_value.rub == Decimal("84821.337")
    assert isinstance(untyped, UnknownPosition)
    assert untyped.type is None
    assert untyped.quantity == 2


def test_empty_board_means_no_board() -> None:
    stock = only(Portfolio.model_validate([{**STOCK, "board": ""}]))

    assert isinstance(stock, EquityPosition)
    assert stock.board is None
    assert stock.key is None


def test_nested_and_dumped_payloads_validate_the_same() -> None:
    portfolio = Portfolio.model_validate([MONEY, STOCK, BOND, FUTURE])

    dumped = Portfolio.model_validate([line.model_dump() for line in portfolio.lines])
    aliased = Portfolio.model_validate([line.model_dump(by_alias=True) for line in portfolio.lines])
    instances = Portfolio.model_validate(portfolio.lines)

    assert dumped == portfolio
    assert aliased == portfolio
    assert instances == portfolio


def test_select_filters_by_kind_and_term() -> None:
    portfolio = Portfolio.model_validate(
        [MONEY, STOCK, BOND, FUTURE, {**STOCK, "term": "T0"}, {**BOND, "term": None}]
    )

    assert [type(p) for p in portfolio.select(SecurityPosition)] == [EquityPosition, BondPosition]
    assert len(portfolio.select(InstrumentPosition)) == 3
    assert [p.currency for p in portfolio.select(MoneyPosition)] == ["CNY"]
    assert [p.ticker for p in portfolio.select(BondPosition)] == ["RU000A1056U0"]
    assert [p.term for p in portfolio.select(EquityPosition, term=Term.T0)] == [Term.T0]
    assert portfolio.select(OtcPosition) == []


from bacsy.models import Term  # noqa: E402 - keeps the fixtures at the top of the module
