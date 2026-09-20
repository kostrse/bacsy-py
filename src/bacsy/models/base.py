"""Base models and field types shared by every request and response model."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Annotated

from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, PlainSerializer
from pydantic.alias_generators import to_camel

from bacsy._json import decimal_to_number


class BaseApiModel(BaseModel):
    """Frozen Pydantic model using the API's camelCase field names.

    Fields are declared in ``snake_case`` and serialized as ``camelCase``. Models can be
    constructed with either spelling. Unknown fields are ignored and string values are
    stripped of surrounding whitespace.
    """

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="ignore",
        frozen=True,
        str_strip_whitespace=True,
    )


class RequestModel(BaseApiModel):
    """Base for request bodies. Unknown fields are rejected."""

    model_config = ConfigDict(extra="forbid")


def empty_to_none(value: object) -> object:
    """Return ``None`` for an empty string, which the API sends for absent values."""
    return None if value == "" else value


def assume_utc(value: datetime) -> datetime:
    """Attach UTC to a naive datetime."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def format_utc(value: datetime) -> str:
    """Format a datetime as ISO 8601 in UTC with a ``Z`` suffix."""
    value = assume_utc(value).astimezone(UTC)
    if value.microsecond:
        return value.strftime("%Y-%m-%dT%H:%M:%S.") + f"{value.microsecond // 1000:03d}Z"
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_yyyymmdd(value: object) -> object:
    """Parse the compact ``YYYYMMDD`` date format."""
    if isinstance(value, str) and len(value) == 8 and value.isdigit():
        return date(int(value[:4]), int(value[4:6]), int(value[6:]))
    return value


def format_yyyymmdd(value: date) -> str:
    return value.strftime("%Y%m%d")


def epoch_millis_to_datetime(value: object) -> object:
    """Convert integer milliseconds since the epoch to an aware datetime."""
    if isinstance(value, int) and not isinstance(value, bool):
        return datetime.fromtimestamp(value / 1000, tz=UTC)
    return value


_MOEX_TIME = timezone(timedelta(hours=3))
_EPOCH_DATE = date(1970, 1, 1)


def _wire_datetime(value: object) -> datetime | None:
    """Read an ISO 8601 timestamp, or return ``None`` if the value is not one."""
    if isinstance(value, datetime):
        return assume_utc(value)
    if isinstance(value, str):
        try:
            return assume_utc(datetime.fromisoformat(value))
        except ValueError:
            return None
    return None


def _calendar_date(value: object, zone: timezone) -> object:
    """Reduce a timestamp to the calendar date it falls on in ``zone``.

    A value that is not a timestamp is passed through unchanged for the field's own
    validation.
    """
    moment = _wire_datetime(value)
    return value if moment is None else moment.astimezone(zone).date()


def utc_calendar_date(value: object) -> object:
    """Read a timestamp as the calendar date it falls on in UTC."""
    return _calendar_date(value, UTC)


def moex_calendar_date(value: object) -> object:
    """Read a timestamp as the calendar date it falls on in Moscow time, UTC+03:00."""
    return _calendar_date(value, _MOEX_TIME)


def epoch_date_to_none(value: date | None) -> date | None:
    """Return ``None`` for ``1970-01-01``, which the API sends for an absent date."""
    return None if value == _EPOCH_DATE else value


Money = Annotated[Decimal, PlainSerializer(decimal_to_number, when_used="json")]
"""A price, quantity or amount. Parsed exactly and serialized as a JSON number."""

UtcDatetime = Annotated[
    datetime, AfterValidator(assume_utc), PlainSerializer(format_utc, when_used="json")
]
"""A timestamp. Naive values are interpreted as UTC; serialized with a ``Z`` suffix."""

OptionalMoney = Money | None
"""A `Money` value that may be absent."""

OptionalStr = Annotated[str | None, BeforeValidator(empty_to_none)]
"""A string that may be absent; an empty string is read as ``None``."""

OptionalDecimal = Annotated[Decimal | None, BeforeValidator(empty_to_none)]
"""A decimal that may be absent; an empty string is read as ``None``."""

OptionalDatetime = Annotated[UtcDatetime | None, BeforeValidator(empty_to_none)]
"""A `UtcDatetime` that may be absent; an empty string is read as ``None``."""

OptionalDate = Annotated[date | None, BeforeValidator(empty_to_none)]
"""A date that may be absent; an empty string is read as ``None``."""

CompactDate = Annotated[
    date,
    BeforeValidator(parse_yyyymmdd),
    PlainSerializer(format_yyyymmdd, when_used="json"),
]
"""A date in the ``YYYYMMDD`` wire format."""

OptionalCalendarDate = Annotated[
    date | None,
    BeforeValidator(empty_to_none),
    BeforeValidator(parse_yyyymmdd),
    BeforeValidator(utc_calendar_date),
    AfterValidator(epoch_date_to_none),
]
"""A calendar date that may be absent.

Read from an ISO date, from the compact ``YYYYMMDD`` form, or from a timestamp, which is
reduced to the date it falls on in UTC. An empty string and ``1970-01-01``, both of which
the API sends for an absent value, are read as ``None``.
"""

OptionalMoexDate = Annotated[
    date | None,
    BeforeValidator(empty_to_none),
    BeforeValidator(moex_calendar_date),
    AfterValidator(epoch_date_to_none),
]
"""A calendar date sent as a timestamp at midnight Moscow time.

The timestamp is reduced to the date it falls on in UTC+03:00, the Moscow Exchange time
zone, rather than in UTC, which would name the day before. An empty string and the Unix
epoch, both of which the API sends for an absent value, are read as ``None``.
"""

EpochMillis = Annotated[UtcDatetime, BeforeValidator(epoch_millis_to_datetime)]
"""A timestamp sent as integer milliseconds since the Unix epoch."""
