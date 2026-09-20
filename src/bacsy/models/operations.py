"""Non-trade operations: deposits, withdrawals, dividends, coupons, commissions and taxes."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from pydantic import Field

from bacsy.models.base import (
    BaseApiModel,
    OptionalDatetime,
    OptionalStr,
    RequestModel,
    UtcDatetime,
)
from bacsy.models.common import InstrumentRef
from bacsy.models.enums import BalanceChange, OperationStatus, OperationType


class OperationsSearchRequest(RequestModel):
    """Body of ``POST /operations/search``."""

    tickers: list[str] | None = None
    """Restrict to these tickers."""
    isins: list[str] | None = None
    """Restrict to these ISINs."""
    currencies: list[str] | None = None
    """Restrict to these currencies."""
    operation_types: list[OperationType] | None = None
    """Restrict to these operation types."""
    statuses: list[OperationStatus] | None = None
    """Restrict to these statuses."""
    start_date_time: UtcDatetime | None = None
    """Start of the period."""
    end_date_time: UtcDatetime | None = None
    """End of the period."""


class NonTradeOperation(InstrumentRef):
    """One non-trade operation."""

    id: UUID | None = None
    """Operation identifier."""
    type: OperationType | None = None
    """Operation type."""
    status: OperationStatus | None = None
    """Processing status."""
    balance_change: BalanceChange | None = None
    """Effect on the account balance."""
    date: OptionalDatetime = None
    """Operation date."""
    sum: Decimal | None = None
    """Amount."""
    currency: OptionalStr = None
    """Currency of the operation."""
    isin: OptionalStr = None
    """ISIN of the instrument."""
    issuer_name: OptionalStr = None
    """Name of the instrument."""
    execution_period: OptionalStr = None
    """Expected execution period."""
    rejection_reason: OptionalStr = None
    """Why the operation was rejected."""
    replenishment_type: OptionalStr = None
    """Deposit method."""
    is_iia: bool | None = None
    """Whether the agreement is an individual investment account (IIA)."""
    is_rests_pay_out: bool | None = None
    """Whether the whole remaining balance is withdrawn."""


class OperationsPage(BaseApiModel):
    """One page of non-trade operations. The response carries no total count."""

    page_size: int | None = None
    """Records per page."""
    records: list[NonTradeOperation] = Field(default_factory=list)
    """Operations."""
