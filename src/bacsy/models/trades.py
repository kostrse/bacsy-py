"""Executed trades of the account."""

from __future__ import annotations

from decimal import Decimal

from pydantic import Field

from bacsy.models.base import (
    OptionalDate,
    OptionalDatetime,
    OptionalStr,
    RequestModel,
    UtcDatetime,
)
from bacsy.models.common import InstrumentRef
from bacsy.models.enums import DealType, Side


class TradesSearchRequest(RequestModel):
    """Body of ``POST /trades/search``."""

    tickers: list[str] | None = None
    """Restrict to these tickers."""
    class_codes: list[str] | None = None
    """Restrict to these class codes."""
    trade_nums: list[int] | None = None
    """Restrict to these trade numbers."""
    side: Side | None = None
    """Restrict to one direction."""
    start_date_time: UtcDatetime | None = None
    """Start of the period."""
    end_date_time: UtcDatetime | None = None
    """End of the period."""


class Trade(InstrumentRef):
    """One executed trade."""

    trade_num: int | None = None
    """Trade number."""
    order_num: int | None = None
    """Order number."""
    client_code: OptionalStr = None
    """Client code."""
    instrument_type_name: OptionalStr = Field(default=None, alias="instrumentType")
    """Human-readable instrument kind in Russian, e.g. ``Фьючерсы``."""
    side: Side | None = None
    """Buy or sell."""
    deal_type: DealType | None = None
    """Type of deal: ordinary, negotiated, a repo leg and so on."""
    price: Decimal | None = None
    """Trade price."""
    price_currency: OptionalStr = None
    """Price currency."""
    base_currency: OptionalStr = None
    """Base currency."""
    settlement_currency: OptionalStr = None
    """Settlement currency."""
    trade_quantity: Decimal | None = None
    """Quantity, units; for futures the underlying, so a one-contract trade reports the
    contract size."""
    trade_quantity_lots: Decimal | None = None
    """Quantity, lots."""
    volume: Decimal | None = None
    """Trade value."""
    contract_amount: Decimal | None = None
    """Contract amount."""
    collateral: Decimal | None = Field(default=None, alias="go")
    """Collateral (initial margin) held for the trade."""
    trade_date_time: OptionalDatetime = None
    """When the trade was made."""
    settle_date: OptionalDate = None
    """Settlement date."""
