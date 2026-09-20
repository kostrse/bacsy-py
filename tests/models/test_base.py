"""Behaviour of the shared Pydantic base model."""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from bacsy.models import BaseApiModel


class Position(BaseApiModel):
    ticker: str
    current_price: Decimal


def test_parses_camel_case_payload() -> None:
    position = Position.model_validate({"ticker": "SBER", "currentPrice": "312.45"})

    assert position.current_price == Decimal("312.45")


def test_accepts_field_names_as_well_as_aliases() -> None:
    position = Position(ticker="SBER", current_price=Decimal("1"))

    assert position.ticker == "SBER"


def test_serializes_back_to_camel_case() -> None:
    position = Position.model_validate({"ticker": "SBER", "currentPrice": "1.5"})

    assert position.model_dump(by_alias=True) == {"ticker": "SBER", "currentPrice": Decimal("1.5")}


def test_ignores_unknown_fields() -> None:
    position = Position.model_validate({"ticker": "SBER", "currentPrice": "1", "newField": 1})

    assert not hasattr(position, "newField")


def test_models_are_frozen() -> None:
    position = Position.model_validate({"ticker": "SBER", "currentPrice": "1"})

    with pytest.raises(ValidationError):
        position.ticker = "GAZP"
