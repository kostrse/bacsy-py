"""Annotated field types shared by the models."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from bacsy.models import (
    BaseApiModel,
    CompactDate,
    EpochMillis,
    Money,
    OptionalCalendarDate,
    OptionalDatetime,
    OptionalDecimal,
    OptionalMoexDate,
    OptionalStr,
    RequestModel,
    UtcDatetime,
)


class Sample(BaseApiModel):
    name: OptionalStr = None
    price: OptionalDecimal = None
    at: OptionalDatetime = None
    seen: UtcDatetime | None = None
    created: EpochMillis | None = None


class Reference(BaseApiModel):
    emission_date: OptionalCalendarDate = None
    maturity_date: OptionalCalendarDate = None
    settlement_date: OptionalCalendarDate = None
    next_coupon: OptionalMoexDate = None


class Order(RequestModel):
    price: Money
    expiry_date: CompactDate


def test_empty_strings_become_none() -> None:
    sample = Sample.model_validate({"name": "", "price": "", "at": ""})

    assert sample.name is None
    assert sample.price is None
    assert sample.at is None


def test_values_are_parsed() -> None:
    sample = Sample.model_validate(
        {"name": " x ", "price": Decimal("1.5"), "at": "2024-10-30T09:01:00.000Z"}
    )

    assert sample.name == "x"
    assert sample.price == Decimal("1.5")
    assert sample.at == datetime(2024, 10, 30, 9, 1, tzinfo=UTC)


def test_naive_datetimes_are_assumed_utc() -> None:
    sample = Sample.model_validate({"seen": "2024-10-30T09:01:00"})

    assert sample.seen == datetime(2024, 10, 30, 9, 1, tzinfo=UTC)


def test_epoch_millis() -> None:
    sample = Sample.model_validate({"created": 1730278860000})

    assert sample.created == datetime(2024, 10, 30, 9, 1, tzinfo=UTC)


def test_compact_date_round_trip() -> None:
    order = Order.model_validate({"price": 1, "expiryDate": "20241030"})

    assert order.expiry_date == date(2024, 10, 30)
    assert order.model_dump(mode="json", by_alias=True) == {
        "price": 1,
        "expiryDate": "20241030",
    }


def test_compact_date_accepts_date_objects() -> None:
    order = Order(price=Decimal("2.5"), expiry_date=date(2024, 1, 2))

    assert order.model_dump(mode="json", by_alias=True) == {
        "price": 2.5,
        "expiryDate": "20240102",
    }


def test_compact_calendar_date_is_a_date_not_a_timestamp() -> None:
    reference = Reference.model_validate({"maturityDate": "20270629"})

    assert reference.maturity_date == date(2027, 6, 29)


def test_calendar_date_reads_an_iso_date() -> None:
    reference = Reference.model_validate({"emissionDate": "2012-09-18"})

    assert reference.emission_date == date(2012, 9, 18)


def test_empty_calendar_date_is_absent() -> None:
    reference = Reference.model_validate({"maturityDate": ""})

    assert reference.maturity_date is None


@pytest.mark.parametrize(
    "value",
    ["1970-01-01", "19700101", "1970-01-01T00:00:00.000Z", "1970-01-01T00:00:00"],
)
def test_epoch_marker_is_read_as_absent(value: str) -> None:
    reference = Reference.model_validate({"emissionDate": value, "nextCoupon": value})

    assert reference.emission_date is None
    assert reference.next_coupon is None


def test_midnight_utc_timestamp_is_its_utc_date() -> None:
    reference = Reference.model_validate({"settlementDate": "2026-03-05T00:00:00.000Z"})

    assert reference.settlement_date == date(2026, 3, 5)


def test_midnight_moscow_timestamp_names_the_following_day() -> None:
    reference = Reference.model_validate({"nextCoupon": "2026-03-05T21:00:00.000Z"})

    assert reference.next_coupon == date(2026, 3, 6)


def test_moscow_date_crosses_the_year_boundary() -> None:
    reference = Reference.model_validate({"nextCoupon": "2026-12-31T21:00:00.000Z"})

    assert reference.next_coupon == date(2027, 1, 1)


def test_naive_moscow_timestamps_are_read_as_utc() -> None:
    naive = Reference.model_validate({"nextCoupon": "2026-03-05T21:00:00"})
    aware = Reference.model_validate({"nextCoupon": "2026-03-05T21:00:00+00:00"})

    assert naive.next_coupon == aware.next_coupon == date(2026, 3, 6)


def test_unexpected_time_of_day_is_converted_not_rejected() -> None:
    reference = Reference.model_validate({"nextCoupon": "2026-03-05T10:00:00.000Z"})

    assert reference.next_coupon == date(2026, 3, 5)


def test_calendar_dates_accept_date_objects() -> None:
    reference = Reference(maturity_date=date(2027, 6, 29))

    assert reference.maturity_date == date(2027, 6, 29)


def test_calendar_dates_serialize_as_iso_dates() -> None:
    reference = Reference.model_validate({"maturityDate": "20270629"})

    assert reference.model_dump(mode="json", by_alias=True) == {
        "emissionDate": None,
        "maturityDate": "2027-06-29",
        "settlementDate": None,
        "nextCoupon": None,
    }
