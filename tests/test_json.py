"""Decimal-preserving JSON encoding and decoding."""

from __future__ import annotations

from decimal import Decimal

from bacsy._json import dumps_request, loads_decimal
from bacsy.models import Money, RequestModel


class Body(RequestModel):
    order_quantity: int
    price: Money | None = None
    stop_price: Money | None = None


def test_loads_floats_as_decimal() -> None:
    payload = loads_decimal('{"price": 300.526666, "qty": 3, "nested": [1.10]}')

    assert payload == {"price": Decimal("300.526666"), "qty": 3, "nested": [Decimal("1.10")]}
    assert isinstance(payload, dict)
    assert isinstance(payload["price"], Decimal)


def test_dumps_uses_aliases_and_drops_none() -> None:
    body = Body(order_quantity=2, price=Decimal("244.35"))

    assert dumps_request(body) == b'{"orderQuantity":2,"price":244.35}'


def test_dumps_integral_decimal_as_integer() -> None:
    assert dumps_request(Body(order_quantity=1, price=Decimal("100.0"))) == (
        b'{"orderQuantity":1,"price":100}'
    )


def test_dumps_round_trips_market_prices_exactly() -> None:
    for text in ("0.0001", "1e-07", "12345.678", "99999.99999999", "0.12345678"):
        body = Body(order_quantity=1, price=Decimal(text))
        decoded = loads_decimal(dumps_request(body))
        assert isinstance(decoded, dict)
        assert decoded["price"] == Decimal(text)
