"""The instrument hierarchy: one class per instrument type, with grouped fields."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from pydantic import TypeAdapter

from bacsy.models import (
    Board,
    Bond,
    Commodity,
    CurrencyPair,
    Equity,
    Future,
    Index,
    Instrument,
    InstrumentKey,
    InstrumentSubType,
    InstrumentType,
    Option,
    OptionType,
    Security,
    UnknownInstrument,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

INSTRUMENTS = TypeAdapter(list[Instrument])

SHARE = {
    "ticker": "SBERP",
    "isin": "RU0009029557",
    "type": "Акции привилегированные",
    "instrumentType": "STOCK",
    "subType": "AST_SEC_PREV",
    "displayName": "Сбербанк ап",
    "issuerName": "ПАО Сбербанк",
    "businessSector": "Финансы",
    "businessSectorId": 7,
    "businessCountryCode": "RU",
    "primaryBoard": "TQBR",
    "secondaryBoards": ["SMAL"],
    "boards": [
        {"classCode": "TQBR", "exchange": "MOEX"},
        {"classCode": "SPBRU", "exchange": "SPB"},
    ],
    "lotSize": "1.0",
    "minimumStep": "0.01",
    "scale": 2,
    "tradingCurrency": "RUB",
    "settlementCurrency": "RUR",
    "settleCode": "T+1",
    "settlementDate": "2026-09-21T00:00:00.000Z",
    "faceValue": "3.0",
    "currencyNominal": "RUB",
    "emissionDate": "1970-01-01",
    "isCanMargin": True,
    "isCanShort": False,
    "availableForUnqualified": True,
    "mktcap": "6.86868E+11",
    "peNorm": "7.22",
    "dividendYield": "5.75",
    "priceChangeYear": "15.73",
    "priceChangeEarlyYear": "10.29",
    "cfi": "ESVXFR",
}

BOND = {
    "ticker": "RU000A101Q26",
    "isin": "RU000A101Q26",
    "type": "Облигации корпоративные",
    "instrumentType": "BONDS",
    "subType": "AST_CORP",
    "primaryBoard": "TQCB",
    "boards": [{"classCode": "TQCB", "exchange": "MOEX"}],
    "faceValue": "1000.0",
    "currencyNominal": "RUB",
    "couponRate": "16.0",
    "couponTypeName": "Переменный",
    "couponsPerYear": 2,
    "nextCoupon": "2026-11-17T21:00:00.000Z",
    "accruedInt": "54.36",
    "amortisedMty": False,
    "emissionDate": "2020-05-25",
    "maturityDate": "20300515",
    "creditRating": "high",
    "liquidityRating": "middle3",
    "isReplacementBond": False,
}

FUTURE = {
    "ticker": "SiZ6",
    "instrumentType": "FUTURES",
    "subType": "AST_FUT",
    "type": "Фьючерсы",
    "primaryBoard": "SPBFUT",
    "boards": [{"classCode": "SPBFUT", "exchange": "MOEX"}],
    "baseAsset": "USD/RUB",
    "baseAssetFuture": "Валюта",
    "baseAssetSecurityClassCode": "CETS_FX",
    "baseAssetSecuritySecCode": "USD000SMALL",
    "maturityDate": "20261217",
    "lotSize": "1000.0",
    "stepPrice": "1.0",
    "currencyStepPrice": "RUB",
    "minimumStep": "1.0",
    "scale": 0,
    "settleCode": "T+n",
}

OPTION = {
    "ticker": "SR100CC0",
    "instrumentType": "OPTIONS",
    "subType": "AST_OPT_CALL",
    "type": "call",
    "primaryBoard": "OPTSPOT",
    "boards": [{"classCode": "OPTSPOT", "exchange": "MOEX"}],
    "baseAsset": "Сбербанк",
    "baseAssetFuture": "Акции",
    "baseAssetSecurityClassCode": "TQBR",
    "baseAssetSecuritySecCode": "SBER",
    "maturityDate": "20300320",
    "strike": "100.0",
}


def one(payload: Mapping[str, object]) -> object:
    return INSTRUMENTS.validate_python([payload])[0]


def test_share_groups_listing_trading_issuer_and_analytics() -> None:
    share = one(SHARE)

    assert isinstance(share, Equity)
    assert isinstance(share, Security)
    assert share.instrument_type is InstrumentType.STOCK
    assert share.sub_type is InstrumentSubType.PREFERRED_SHARE
    assert share.type_name == "Акции привилегированные"
    assert share.key == InstrumentKey(ticker="SBERP", class_code="TQBR")
    assert share.keys == [
        InstrumentKey(ticker="SBERP", class_code="TQBR"),
        InstrumentKey(ticker="SBERP", class_code="SPBRU"),
        InstrumentKey(ticker="SBERP", class_code="SMAL"),
    ]
    assert share.listing.boards[1] == Board(class_code="SPBRU", exchange="SPB")
    assert share.listing.settle_code == "T+1"
    assert share.listing.settlement_date == date(2026, 9, 21)
    assert share.trading.lot_size == 1
    assert share.trading.minimum_step == Decimal("0.01")
    assert share.trading.settlement_currency == "RUR"
    assert share.eligibility.margin_allowed is True
    assert share.eligibility.short_allowed is False
    assert share.eligibility.qualified_only is None
    assert share.issuer.name == "ПАО Сбербанк"
    assert share.issuer.sector_id == 7
    assert share.face_value == 3
    assert share.nominal_currency == "RUB"
    assert share.emission_date is None
    assert share.analytics.market_cap == Decimal("6.86868E+11")
    assert share.analytics.dividend_yield == Decimal("5.75")
    assert share.price_change.year == Decimal("15.73")
    assert share.price_change.year_to_date == Decimal("10.29")
    assert share.price_change.month is None
    assert not hasattr(share, "cfi")
    assert not hasattr(share, "coupon_rate")
    assert not hasattr(share, "strike")


@pytest.mark.parametrize(
    "instrument_type", ["FOREIGN_STOCK", "DEPOSITARY_RECEIPTS", "ETF", "MUTUAL_FUNDS"]
)
def test_the_equity_family_is_one_class(instrument_type: str) -> None:
    assert isinstance(one({**SHARE, "instrumentType": instrument_type}), Equity)


def test_bond_terms() -> None:
    bond = one(BOND)

    assert isinstance(bond, Bond)
    assert bond.sub_type is InstrumentSubType.CORPORATE_BOND
    assert bond.coupon_rate == 16
    assert bond.coupons_per_year == 2
    assert bond.next_coupon == date(2026, 11, 18)
    assert bond.accrued_interest == Decimal("54.36")
    assert bond.amortised is False
    assert bond.emission_date == date(2020, 5, 25)
    assert bond.maturity_date == date(2030, 5, 15)
    assert bond.credit_rating == "high"
    assert bond.face_value == 1000


@pytest.mark.parametrize("instrument_type", ["EURO_BONDS", "NOTES"])
def test_the_debt_family_is_one_class(instrument_type: str) -> None:
    assert isinstance(one({**BOND, "instrumentType": instrument_type}), Bond)


def test_future_names_its_underlying() -> None:
    future = one(FUTURE)

    assert isinstance(future, Future)
    assert future.base_asset_name == "USD/RUB"
    assert future.base_asset_group == "Валюта"
    assert future.underlying == InstrumentKey(ticker="USD000SMALL", class_code="CETS_FX")
    assert future.expiry == date(2026, 12, 17)
    assert not future.is_perpetual
    assert future.trading.step_price == 1
    assert future.trading.step_price_currency == "RUB"
    assert not hasattr(future, "isin")


def test_perpetual_future_and_foreign_underlying() -> None:
    future = one(
        {
            **FUTURE,
            "maturityDate": "21000101",
            "baseAssetSecurityClassCode": "",
            "baseAssetSecuritySecCode": "",
        }
    )

    assert isinstance(future, Future)
    assert future.is_perpetual
    assert future.underlying is None


def test_option_reads_strike_and_type() -> None:
    call = one(OPTION)
    put = one({**OPTION, "subType": "", "type": "put"})

    assert isinstance(call, Option)
    assert call.strike == 100
    assert call.option_type is OptionType.CALL
    assert call.underlying == InstrumentKey(ticker="SBER", class_code="TQBR")
    assert isinstance(put, Option)
    assert put.option_type is OptionType.PUT
    assert put.sub_type is None


def test_currency_pair_index_and_commodity() -> None:
    pair, index, commodity = INSTRUMENTS.validate_python(
        [
            {
                "ticker": "CNYRUB_TOM",
                "instrumentType": "CURRENCY",
                "firstCurrCode": "CNY",
                "lotSize": 1000,
            },
            {"ticker": "IMOEX", "instrumentType": "INDICES", "primaryBoard": "INDX"},
            {"ticker": "AL3M", "instrumentType": "GOODS", "primaryBoard": "FEM"},
        ]
    )

    assert isinstance(pair, CurrencyPair)
    assert pair.quoted_currency == "CNY"
    assert pair.trading.lot_size == 1000
    assert isinstance(index, Index)
    assert index.key == InstrumentKey(ticker="IMOEX", class_code="INDX")
    assert isinstance(commodity, Commodity)


def test_unknown_type_keeps_every_field() -> None:
    unknown, untyped = INSTRUMENTS.validate_python(
        [{**BOND, **OPTION, "instrumentType": "WARRANTS", "isin": "X"}, {"ticker": "Y"}]
    )

    assert isinstance(unknown, UnknownInstrument)
    assert unknown.instrument_type is not None
    assert not unknown.instrument_type.is_known
    assert unknown.isin == "X"
    assert unknown.coupon_rate == 16
    assert unknown.strike == 100
    assert unknown.underlying == InstrumentKey(ticker="SBER", class_code="TQBR")
    assert isinstance(untyped, UnknownInstrument)
    assert untyped.instrument_type is None
    assert untyped.keys == []
    assert untyped.key is None


def test_nested_and_dumped_payloads_validate_the_same() -> None:
    instruments = INSTRUMENTS.validate_python([SHARE, BOND, FUTURE, OPTION])

    dumped = INSTRUMENTS.validate_python([i.model_dump() for i in instruments])
    aliased = INSTRUMENTS.validate_python([i.model_dump(by_alias=True) for i in instruments])
    instances = INSTRUMENTS.validate_python(instruments)

    assert dumped == instruments
    assert aliased == instruments
    assert instances == instruments
