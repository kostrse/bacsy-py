"""Private helpers for reshaping wire payloads before validation."""

from __future__ import annotations

from typing import cast

from pydantic import BaseModel


def as_wire_dict(data: object) -> dict[str, object] | None:
    """Return a shallow copy of ``data`` when it is a JSON object, else ``None``."""
    if isinstance(data, dict):
        return dict(cast("dict[str, object]", data))
    return None


def is_nested(value: object) -> bool:
    """``True`` when ``value`` is already a nested object rather than a flat wire value."""
    return isinstance(value, dict | BaseModel)


def nest(data: dict[str, object], target: str, fields: dict[str, str]) -> None:
    """Move flat wire keys into a nested object stored under ``target``.

    ``fields`` maps each wire key to the field name it takes inside the nested object. A
    ``target`` that already holds a nested object or model is left alone, so validating
    an already-nested payload, or a model instance, is idempotent. Nothing is written
    when none of the wire keys is present, leaving the field to its default.
    """
    if is_nested(data.get(target)):
        return
    nested: dict[str, object] = {}
    for wire_key, field in fields.items():
        if wire_key in data:
            nested[field] = data.pop(wire_key)
    if nested:
        data[target] = nested


def get_wire(value: object, wire_key: str, field: str) -> object:
    """Read a value from a payload by its wire key or field name, or from a model instance.

    A payload may spell the key either way, since models accept both the alias and the
    field name and ``model_dump()`` produces the latter.
    """
    if isinstance(value, dict):
        payload = cast("dict[str, object]", value)
        return payload.get(wire_key, payload.get(field))
    return getattr(value, field, None)
