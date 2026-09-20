"""Tolerant enum parsing."""

from __future__ import annotations

from bacsy.models import BaseApiModel, LenientIntEnum, LenientStrEnum


class Colour(LenientStrEnum):
    RED = "RED"


class Level(LenientIntEnum):
    LOW = 1


class Payload(BaseApiModel):
    colour: Colour
    level: Level


def test_known_members() -> None:
    assert Colour("RED") is Colour.RED
    assert Colour.RED.is_known
    assert Level(1) is Level.LOW


def test_unknown_str_value_is_preserved() -> None:
    value = Colour("BLUE")

    assert value == "BLUE"
    assert value.value == "BLUE"
    assert not value.is_known
    assert isinstance(value, Colour)


def test_unknown_int_value_is_preserved() -> None:
    assert Level(7) == 7
    assert not Level(7).is_known
    assert Level("7") == 7


def test_pydantic_accepts_unknown_values() -> None:
    payload = Payload.model_validate({"colour": "GREEN", "level": 9})

    assert payload.colour == "GREEN"
    assert not payload.colour.is_known
    assert payload.level == 9


def test_pydantic_accepts_known_values() -> None:
    payload = Payload.model_validate({"colour": "RED", "level": "1"})

    assert payload.colour is Colour.RED
    assert payload.level is Level.LOW


def test_str_enum_accepts_integer_codes() -> None:
    from bacsy.models import Side, TimeInForce

    assert Side(2) is Side.SELL
    assert TimeInForce(1) is TimeInForce.DAY
    assert Side(7) == "7"
    assert not Side(7).is_known


def test_deal_type_and_risk_level_are_lenient() -> None:
    from decimal import Decimal

    from bacsy.models import DealType, RiskLevel, Trade
    from bacsy.models.margin import FortsStability

    assert Trade.model_validate({"dealType": 1}).deal_type is DealType.ORDINARY
    assert Trade.model_validate({"go": "12.5"}).collateral == Decimal("12.5")
    unknown = Trade.model_validate({"dealType": 99}).deal_type
    assert unknown is not None
    assert not unknown.is_known
    assert FortsStability.model_validate({"riskLevel": 2}).risk_level is RiskLevel.STANDARD
