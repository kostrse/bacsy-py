"""JSON helpers that keep decimal precision.

The API encodes prices and quantities as JSON numbers; responses are decoded with
`parse_float=Decimal` so their digits are preserved.
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from pydantic import BaseModel

type JsonValue = dict[str, JsonValue] | list[JsonValue] | str | int | Decimal | bool | None
"""A decoded JSON document with floats represented as `Decimal`."""


def loads_decimal(data: str | bytes) -> JsonValue:
    """Decode `data` with floats as `Decimal`."""
    return cast("JsonValue", json.loads(data, parse_float=Decimal))


def decimal_to_number(value: Decimal) -> int | float:
    """Serialize a ``Decimal`` as a JSON number."""
    if value == value.to_integral_value():
        return int(value)
    return float(value)


def _default(value: object) -> int | float:
    if isinstance(value, Decimal):
        return decimal_to_number(value)
    msg = f"Object of type {type(value).__name__} is not JSON serializable"
    raise TypeError(msg)


def dumps_json(payload: object) -> bytes:
    """Encode `payload` as compact JSON, sending `Decimal` values as numbers."""
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False, default=_default).encode()


def dumps_request(model: BaseModel) -> bytes:
    """Serialize a request model to compact JSON using the API's field aliases."""
    return dumps_json(model.model_dump(mode="json", by_alias=True, exclude_none=True))
