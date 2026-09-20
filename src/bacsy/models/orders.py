"""Order requests, execution reports and order search results.

The API uses two vocabularies for orders. The operations service (placing, editing,
cancelling, fetching by id, and the order events stream) reports execution-report
fields: `OrderReport` with `OrderStatus` and `OrderType`. The order-details service
(search) returns `OrderSummary` with `OrderListStatus` and `OrderListType`.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from pydantic import Field

from bacsy.models.base import (
    BaseApiModel,
    CompactDate,
    Money,
    OptionalDate,
    OptionalDatetime,
    OptionalStr,
    RequestModel,
    UtcDatetime,
)
from bacsy.models.common import InstrumentRef
from bacsy.models.enums import (
    ExecutionType,
    OffsetType,
    OrderIdType,
    OrderListStatus,
    OrderListType,
    OrderStatus,
    OrderType,
    Side,
    StopExecutionType,
    TimeInForce,
)


class NewOrderRequest(RequestModel):
    """Body of ``POST /orders``."""

    client_order_id: UUID
    """Client-generated identifier used to track the order and reject duplicates."""
    ticker: str
    """Instrument ticker."""
    class_code: str
    """Class code of the security, e.g. ``TQBR``."""
    side: Side
    """Buy or sell."""
    order_type: OrderType
    """Order type."""
    order_quantity: int = Field(ge=1)
    """Quantity, units; one contract per unit for futures."""
    price: Money | None = None
    """Price per unit, positive, up to 8 decimal places; limit, algorithmic, iceberg and
    conditional orders."""
    time_in_force: TimeInForce | None = None
    """Order lifetime; ``DAY`` when omitted. ``GOOD_TILL_DATE`` applies to algorithmic
    orders only."""
    expiry_date: CompactDate | None = None
    """Last day the order is valid; required with ``GOOD_TILL_DATE``, at most 30 calendar
    days after placement."""
    visible: int | None = Field(default=None, ge=1)
    """Visible quantity of an iceberg order; required for ``ICEBERG``, less than
    `order_quantity`."""
    stop_price: Money | None = None
    """Stop price of a conditional order; required in stop-loss scenarios."""
    take_price: Money | None = None
    """Take-profit price of a conditional order; required in take-profit scenarios."""
    offset: Money | None = None
    """Offset of a conditional order."""
    offset_type: OffsetType | None = None
    """Units of `offset`."""
    spread: Money | None = None
    """Protective spread of a conditional order."""
    spread_type: OffsetType | None = None
    """Units of `spread`."""
    execution_stop_loss_type: StopExecutionType | None = None
    """How the stop-loss leg of a conditional order executes."""
    execution_take_profit_type: StopExecutionType | None = None
    """How the take-profit leg of a conditional order executes."""


class EditOrderRequest(RequestModel):
    """Body of ``POST /orders/edit``.

    The API cancels the order and places a new one. Orders in status ``NEW``,
    ``PARTIALLY_FILLED``, ``REPLACED`` or ``PENDING_NEW`` can be edited.
    """

    client_order_id: UUID
    """Client-generated identifier of the edit request."""
    order_id: str
    """Identifier of the order to edit, interpreted per `order_id_type`."""
    order_id_type: OrderIdType | None = None
    """How `order_id` identifies the order; ``CLIENT`` when omitted."""
    order_quantity: int = Field(ge=1)
    """Quantity of the new order, units."""
    order_type: OrderType | None = None
    """Type of the new order."""
    price: Money | None = None
    """Price per unit, positive, up to 8 decimal places; limit, algorithmic, iceberg and
    conditional orders."""
    time_in_force: TimeInForce | None = None
    """Lifetime of the new order. ``GOOD_TILL_DATE`` applies to algorithmic orders only."""
    expiry_date: CompactDate | None = None
    """Last day the order is valid; required with ``GOOD_TILL_DATE``, at most 30 calendar
    days after the edit."""
    visible: int | None = Field(default=None, ge=1)
    """Visible quantity of an iceberg order; required for ``ICEBERG``, less than
    `order_quantity`."""
    stop_price: Money | None = None
    """Stop price of a conditional order; required in stop-loss scenarios."""
    take_price: Money | None = None
    """Take-profit price of a conditional order; required in take-profit scenarios."""
    offset: Money | None = None
    """Offset of a conditional order; 0 when omitted."""
    offset_type: OffsetType | None = None
    """Units of `offset`."""
    spread: Money | None = None
    """Protective spread of a conditional order."""
    spread_type: OffsetType | None = None
    """Units of `spread`."""
    execution_stop_loss_type: StopExecutionType | None = None
    """How the stop-loss leg of a conditional order executes."""
    execution_take_profit_type: StopExecutionType | None = None
    """How the take-profit leg of a conditional order executes."""


class CancelOrderRequest(RequestModel):
    """Body of ``POST /orders/cancel``.

    Orders in status ``NEW``, ``PARTIALLY_FILLED``, ``REPLACED`` or ``PENDING_NEW`` can
    be cancelled.
    """

    client_order_id: UUID
    """Client-generated identifier of the cancel request."""
    order_id: str
    """Identifier of the order to cancel, interpreted per `order_id_type`."""
    order_id_type: OrderIdType | None = None
    """How `order_id` identifies the order; ``CLIENT`` when omitted."""


class OrderSubmitResult(BaseApiModel):
    """Acknowledgement of an order request. The order itself is reported asynchronously."""

    client_order_id: UUID
    """Identifier of the request."""
    status: OptionalStr = None
    """Completion status, e.g. ``OK``."""


class OrderReport(InstrumentRef):
    """One execution report of an order (operations service vocabulary)."""

    message_type: OptionalStr = None
    execution_type: ExecutionType | None = None
    """Kind of report."""
    order_status: OrderStatus | None = None
    """Order state."""
    order_id: OptionalStr = None
    """Exchange order identifier."""
    order_number: OptionalStr = None
    """Exchange order number."""
    execution_id: OptionalStr = None
    """Trade identifier."""
    security_exchange: OptionalStr = None
    """Exchange identifier."""
    client_code: OptionalStr = None
    """Client code."""
    currency: OptionalStr = None
    """Currency."""
    side: Side | None = None
    """Buy or sell."""
    order_type: OrderType | None = None
    """Order type."""
    time_in_force: TimeInForce | None = None
    """Order lifetime; reported for market, limit and algorithmic orders."""
    expiry_date: CompactDate | None = None
    """Last day the order is valid; reported with ``GOOD_TILL_DATE``."""
    price: Decimal | None = None
    """Order price."""
    average_price: Decimal | None = None
    """Average execution price; for repo and spread trades, the price of the first leg."""
    order_quantity: Decimal | None = None
    """Quantity in the order, units."""
    executed_quantity: Decimal | None = None
    """Executed quantity, units."""
    last_quantity: Decimal | None = None
    """Quantity of the current trade, units."""
    remained_quantity: Decimal | None = None
    """Remaining quantity, units."""
    visible: int | None = None
    """Visible quantity of an iceberg order."""
    stop_price: Decimal | None = None
    """Stop price of a conditional order."""
    take_price: Decimal | None = None
    """Take-profit price of a conditional order."""
    offset: Decimal | None = None
    """Offset of a conditional order."""
    offset_type: OffsetType | None = None
    """Units of `offset`."""
    spread: Decimal | None = None
    """Protective spread of a conditional order."""
    spread_type: OffsetType | None = None
    """Units of `spread`."""
    execution_value: Decimal | None = None
    """Trade value."""
    commission: Decimal | None = None
    """Commission."""
    accrued_coupon: Decimal | None = None
    """Accrued coupon income."""
    reject_reason: OptionalStr = None
    """Why the order was rejected."""
    transaction_time: OptionalDatetime = None
    """Time of the transaction."""
    trade_date: OptionalDate = None
    """Trade date; for the FORTS evening session, the date of the next session."""


class OrderResponse(BaseApiModel):
    """Result of ``GET /orders``: the current state of one order.

    `data` carries the order's latest execution report, not its report history.
    """

    client_order_id: OptionalStr = None
    """Identifier of the request."""
    original_client_order_id: OptionalStr = None
    """Identifier of the order a cancel or edit acted on; ``None`` for a placement."""
    data: OrderReport | None = None
    """The order's latest execution report."""


class OrdersSearchRequest(RequestModel):
    """Body of ``POST /orders/search``."""

    tickers: list[str] | None = None
    """Restrict to these tickers."""
    class_codes: list[str] | None = None
    """Restrict to these class codes."""
    order_status: list[OrderListStatus] | None = None
    """Restrict to these statuses."""
    order_types: list[OrderListType] | None = None
    """Restrict to these order types."""
    side: Side | None = None
    """Restrict to one direction."""
    start_date_time: UtcDatetime | None = None
    """Start of the period."""
    end_date_time: UtcDatetime | None = None
    """End of the period."""


class OrderSummary(InstrumentRef):
    """One order as listed by the order search (order-details service vocabulary)."""

    order_id: OptionalStr = None
    """Order identifier."""
    order_num: int | None = None
    """Order number."""
    client_code: OptionalStr = None
    """Client code."""
    side: Side | None = None
    """Buy or sell."""
    order_type: OrderListType | None = None
    """Order type."""
    order_status: OrderListStatus | None = None
    """Order status."""
    price: Decimal | None = None
    """Order price."""
    average_price: Decimal | None = None
    """Average execution price."""
    stop_price: Decimal | None = None
    """Stop-loss price."""
    take_price: Decimal | None = None
    """Take-profit price."""
    position_price_limit: Decimal | None = None
    """Limit price of the position."""
    position_price_stop: Decimal | None = None
    """Stop price of the position."""
    order_quantity: Decimal | None = None
    """Quantity in the order, units; one contract per unit for futures."""
    order_quantity_lots: Decimal | None = None
    """Quantity in the order, lots."""
    executed_quantity: Decimal | None = None
    """Executed quantity, units."""
    executed_quantity_lots: Decimal | None = None
    """Executed quantity, lots."""
    remained_quantity: Decimal | None = None
    """Remaining quantity, units."""
    remained_quantity_lots: Decimal | None = None
    """Remaining quantity, lots."""
    visible: Decimal | None = None
    """Visible part of an iceberg order."""
    executed_value: Decimal | None = None
    """Executed value, in currency."""
    calculation_volume: Decimal | None = None
    """Calculated volume."""
    contract_sum: Decimal | None = None
    """Contract amount."""
    settlement_currency: OptionalStr = None
    """Settlement currency."""
    market_stop_loss: StopExecutionType | None = None
    """How the stop-loss leg executes."""
    market_take_profit: StopExecutionType | None = None
    """How the take-profit leg executes."""
    linked_order: OptionalStr = None
    """Number of the linked order."""
    stop_order: OptionalStr = None
    """Number of the stop order."""
    reject_reason: OptionalStr = None
    """Why the order was rejected."""
    order_date_time: OptionalDatetime = None
    """When the order was placed."""
    execution_date_time: OptionalDatetime = None
    """When the order was executed."""
    update_date_time: OptionalDatetime = None
    """When the order was last updated."""
    trade_date: OptionalDate = None
    """Trading date."""
