"""Reading the claims of a JSON Web Token without verifying its signature.

The payload of a JWT is base64url-encoded JSON, readable by anyone holding the token.
This module splits a token, decodes the payload, and reads typed values out of the claim
mapping. Signatures are never checked.
"""

from __future__ import annotations

import base64
import binascii
import json
import math
import re
from typing import TYPE_CHECKING, cast

from bacsy.exceptions import InvalidTokenError

if TYPE_CHECKING:
    from collections.abc import Mapping

type Claims = Mapping[str, object]
"""A decoded JWT payload."""

_SEGMENT = re.compile(r"[A-Za-z0-9_-]+={0,2}")
"""The base64url alphabet, padding tolerated."""


def _b64url_decode(segment: str) -> bytes:
    unpadded = segment.rstrip("=")
    padding = "=" * (-len(unpadded) % 4)
    if not _SEGMENT.fullmatch(segment) or (segment != unpadded and segment != unpadded + padding):
        msg = "not a JWT (a segment is not valid base64url)"
        raise InvalidTokenError(msg)
    try:
        return base64.b64decode(unpadded + padding, altchars=b"-_", validate=True)
    except binascii.Error as exc:
        msg = "not a JWT (a segment is not valid base64url)"
        raise InvalidTokenError(msg) from exc


def decode_jwt_claims(value: str) -> dict[str, object]:
    """Return the payload claims of a JWT without verifying its signature.

    Surrounding whitespace is ignored.

    Raises:
        InvalidTokenError: `value` is not a three-segment JWT with JSON object header
            and payload and valid base64url segments.
    """
    segments = value.strip().split(".")
    if len(segments) != 3 or not all(segments):
        msg = "not a JWT (expected three dot-separated segments)"
        raise InvalidTokenError(msg)
    decoded = [_b64url_decode(segment) for segment in segments]
    claims: dict[str, object] = {}
    for name, data in zip(("header", "payload"), decoded[:2], strict=True):
        try:
            value_object = cast("object", json.loads(data))
        except (ValueError, UnicodeDecodeError) as exc:
            msg = f"JWT {name} is not valid base64url-encoded JSON"
            raise InvalidTokenError(msg) from exc
        if not isinstance(value_object, dict):
            msg = f"JWT {name} is not a JSON object"
            raise InvalidTokenError(msg)
        claims = cast("dict[str, object]", value_object)
    return claims


def str_claim(claims: Claims, name: str) -> str:
    """Return the string claim `name`.

    Raises:
        InvalidTokenError: the claim is absent or is not a non-empty string.
    """
    value = claims.get(name)
    if not isinstance(value, str) or not value:
        msg = f"JWT claim {name!r} is missing or not a string"
        raise InvalidTokenError(msg)
    return value


def timestamp_claim(claims: Claims, name: str) -> int:
    """Return the NumericDate claim `name` as whole Unix seconds.

    A fractional value is floored.

    Raises:
        InvalidTokenError: the claim is absent or is not a number.
    """
    value = claims.get(name)
    if isinstance(value, bool) or not isinstance(value, int | float):
        msg = f"JWT claim {name!r} is missing or not a number"
        raise InvalidTokenError(msg)
    return math.floor(value)


def nested_str_claim(claims: Claims, *path: str) -> str | None:
    """Return the non-empty string at `path` inside nested claim objects, or `None`.

    A missing key, a non-object along the path, or a leaf that is not a non-empty string
    yields `None`.
    """
    current: object = claims
    for key in path:
        if not isinstance(current, dict):
            return None
        current = cast("dict[object, object]", current).get(key)
    return current if isinstance(current, str) and current else None
