"""Instrument identity shared across models."""

from __future__ import annotations

import pytest

from bacsy.models import (
    Board,
    HasInstrumentKey,
    InstrumentKey,
    InstrumentRef,
    MultiCurrencyValue,
    NonTradeOperation,
    OrderReport,
    OrderSummary,
    Portfolio,
    Quote,
    Trade,
)


def test_key_is_hashable_and_identifies_itself() -> None:
    key = InstrumentKey(ticker="SBER", class_code="TQBR")

    assert key.key is key
    assert isinstance(key, HasInstrumentKey)
    assert {key: 1}[InstrumentKey(ticker="SBER", class_code="TQBR")] == 1


def test_maybe_needs_both_parts() -> None:
    assert InstrumentKey.maybe("SBER", "TQBR") == InstrumentKey(ticker="SBER", class_code="TQBR")
    assert InstrumentKey.maybe(None, "TQBR") is None
    assert InstrumentKey.maybe("SBER", None) is None


def test_coerce_accepts_keys_tuples_and_keyed_objects() -> None:
    position = Portfolio.model_validate([{"type": "depoLimit", "ticker": "SBER", "board": "TQBR"}])
    key = InstrumentKey(ticker="SBER", class_code="TQBR")
    lines = [key, ("SBER", "TQBR"), position.lines[0]]

    assert InstrumentKey.coerce_all(lines) == [key, key, key]  # pyright: ignore[reportArgumentType]


def test_coerce_rejects_objects_that_do_not_name_an_instrument() -> None:
    class Odd:
        key = "SBER"

    with pytest.raises(TypeError, match="does not name an instrument"):
        InstrumentKey.coerce("SBER")  # pyright: ignore[reportArgumentType]
    with pytest.raises(TypeError, match="not InstrumentKey"):
        InstrumentKey.coerce(Odd())  # pyright: ignore[reportArgumentType]
    with pytest.raises(ValueError, match="unpack"):
        InstrumentKey.coerce(("SBER",))  # pyright: ignore[reportArgumentType]


def test_coerce_rejects_an_object_without_a_key() -> None:
    position = Portfolio.model_validate([{"type": "depoLimit", "ticker": "SBER"}]).lines[0]

    with pytest.raises(ValueError, match="no instrument key"):
        InstrumentKey.coerce(position)  # pyright: ignore[reportArgumentType]


def test_value_objects_default_to_empty() -> None:
    assert MultiCurrencyValue().rub is None
    assert Board().class_code is None


@pytest.mark.parametrize("model", [Quote, OrderReport, OrderSummary, Trade, NonTradeOperation])
def test_records_naming_an_instrument_expose_its_key(model: type[InstrumentRef]) -> None:
    record = model.model_validate({"ticker": "SBER", "classCode": "TQBR"})
    partial = model.model_validate({"ticker": "SBER"})

    assert record.key == InstrumentKey(ticker="SBER", class_code="TQBR")
    assert partial.key is None
