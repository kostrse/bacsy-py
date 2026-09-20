"""Orders service: placing, editing, cancelling, fetching and searching orders."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from bacsy.api._base import MAX_PAGE_SIZE, BaseService, check_page, iter_pages
from bacsy.models.common import Page
from bacsy.models.enums import OrderIdType
from bacsy.models.orders import (
    CancelOrderRequest,
    EditOrderRequest,
    NewOrderRequest,
    OrderReport,
    OrderResponse,
    OrdersSearchRequest,
    OrderSubmitResult,
    OrderSummary,
)
from bacsy.routes import Operation, Service

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Sequence
    from datetime import date, datetime
    from decimal import Decimal

    from bacsy.models.enums import (
        OffsetType,
        OrderListStatus,
        OrderListType,
        OrderType,
        Side,
        StopExecutionType,
        TimeInForce,
    )

CREATE_ORDER = Operation(
    name="create",
    service=Service.OPERATIONS,
    method="POST",
    path="/api/v1/orders",
    idempotent=False,
    scope="write",
)
EDIT_ORDER = Operation(
    name="updateOrder",
    service=Service.OPERATIONS,
    method="POST",
    path="/api/v1/orders/edit",
    idempotent=False,
    scope="write",
)
CANCEL_ORDER = Operation(
    name="cancelOrder",
    service=Service.OPERATIONS,
    method="POST",
    path="/api/v1/orders/cancel",
    idempotent=False,
    scope="write",
)
GET_ORDER = Operation(
    name="getOrderById", service=Service.OPERATIONS, method="GET", path="/api/v1/orders"
)
SEARCH_ORDERS = Operation(
    name="allOrderList",
    service=Service.ORDER_DETAILS,
    method="POST",
    path="/api/v1/orders/search",
)

DEFAULT_ORDER_SORT: tuple[str, ...] = ("orderDateTime",)


class OrdersService(BaseService):
    """``client.orders``: placing, editing, cancelling, fetching and searching orders.

    Placing, editing and cancelling require a token with the ``write`` scope. Each of
    those takes a ``client_order_id`` that the API uses to de-duplicate; one is generated
    when not supplied and returned in the result. These calls are not retried after a
    transport failure or server error; re-issue them with the same ``client_order_id``.
    """

    async def create(
        self,
        *,
        ticker: str,
        class_code: str,
        side: Side,
        order_type: OrderType,
        quantity: int,
        price: Decimal | None = None,
        time_in_force: TimeInForce | None = None,
        expiry_date: date | None = None,
        visible: int | None = None,
        stop_price: Decimal | None = None,
        take_price: Decimal | None = None,
        offset: Decimal | None = None,
        offset_type: OffsetType | None = None,
        spread: Decimal | None = None,
        spread_type: OffsetType | None = None,
        execution_stop_loss_type: StopExecutionType | None = None,
        execution_take_profit_type: StopExecutionType | None = None,
        client_order_id: UUID | None = None,
    ) -> OrderSubmitResult:
        """Place an order.

        ``quantity`` is in units of the instrument, one contract per unit for futures.
        """
        body = NewOrderRequest(
            client_order_id=client_order_id or uuid4(),
            ticker=ticker,
            class_code=class_code,
            side=side,
            order_type=order_type,
            order_quantity=quantity,
            price=price,
            time_in_force=time_in_force,
            expiry_date=expiry_date,
            visible=visible,
            stop_price=stop_price,
            take_price=take_price,
            offset=offset,
            offset_type=offset_type,
            spread=spread,
            spread_type=spread_type,
            execution_stop_loss_type=execution_stop_loss_type,
            execution_take_profit_type=execution_take_profit_type,
        )
        return await self._call(CREATE_ORDER, OrderSubmitResult, body=body)

    async def edit(
        self,
        *,
        order_id: str | UUID,
        quantity: int,
        order_id_type: OrderIdType = OrderIdType.CLIENT,
        order_type: OrderType | None = None,
        price: Decimal | None = None,
        time_in_force: TimeInForce | None = None,
        expiry_date: date | None = None,
        visible: int | None = None,
        stop_price: Decimal | None = None,
        take_price: Decimal | None = None,
        offset: Decimal | None = None,
        offset_type: OffsetType | None = None,
        spread: Decimal | None = None,
        spread_type: OffsetType | None = None,
        execution_stop_loss_type: StopExecutionType | None = None,
        execution_take_profit_type: StopExecutionType | None = None,
        client_order_id: UUID | None = None,
    ) -> OrderSubmitResult:
        """Replace an order. The API implements this as cancel plus a new order."""
        body = EditOrderRequest(
            client_order_id=client_order_id or uuid4(),
            order_id=str(order_id),
            order_id_type=order_id_type,
            order_quantity=quantity,
            order_type=order_type,
            price=price,
            time_in_force=time_in_force,
            expiry_date=expiry_date,
            visible=visible,
            stop_price=stop_price,
            take_price=take_price,
            offset=offset,
            offset_type=offset_type,
            spread=spread,
            spread_type=spread_type,
            execution_stop_loss_type=execution_stop_loss_type,
            execution_take_profit_type=execution_take_profit_type,
        )
        return await self._call(EDIT_ORDER, OrderSubmitResult, body=body)

    async def cancel(
        self,
        *,
        order_id: str | UUID,
        order_id_type: OrderIdType = OrderIdType.CLIENT,
        client_order_id: UUID | None = None,
    ) -> OrderSubmitResult:
        """Cancel an order."""
        body = CancelOrderRequest(
            client_order_id=client_order_id or uuid4(),
            order_id=str(order_id),
            order_id_type=order_id_type,
        )
        return await self._call(CANCEL_ORDER, OrderSubmitResult, body=body)

    async def get(
        self, *, order_id: str | UUID, order_id_type: OrderIdType = OrderIdType.CLIENT
    ) -> OrderResponse:
        """Return the current state of one order.

        The response carries the order's latest execution report, not its history.
        """
        return await self._call(
            GET_ORDER,
            OrderResponse,
            params={"orderId": str(order_id), "orderIdType": order_id_type.value},
        )

    async def get_report(
        self, *, order_id: str | UUID, order_id_type: OrderIdType = OrderIdType.CLIENT
    ) -> OrderReport | None:
        """Return the order's latest execution report, or ``None`` if absent."""
        return (await self.get(order_id=order_id, order_id_type=order_id_type)).data

    async def search(
        self,
        *,
        tickers: Sequence[str] | None = None,
        class_codes: Sequence[str] | None = None,
        statuses: Sequence[OrderListStatus] | None = None,
        types: Sequence[OrderListType] | None = None,
        side: Side | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        page: int = 0,
        size: int = MAX_PAGE_SIZE,
        sort: Sequence[str] = DEFAULT_ORDER_SORT,
    ) -> Page[OrderSummary]:
        """One page of the order history.

        The API lists orders placed on or after 26 January 2026.
        """
        check_page(page, size)
        body = OrdersSearchRequest(
            tickers=list(tickers) if tickers else None,
            class_codes=list(class_codes) if class_codes else None,
            order_status=list(statuses) if statuses else None,
            order_types=list(types) if types else None,
            side=side,
            start_date_time=start,
            end_date_time=end,
        )
        return await self._call(
            SEARCH_ORDERS,
            Page[OrderSummary],
            params={"page": page, "size": size, "sort": list(sort)},
            body=body,
        )

    def iter_search(
        self,
        *,
        tickers: Sequence[str] | None = None,
        class_codes: Sequence[str] | None = None,
        statuses: Sequence[OrderListStatus] | None = None,
        types: Sequence[OrderListType] | None = None,
        side: Side | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        size: int = MAX_PAGE_SIZE,
        sort: Sequence[str] = DEFAULT_ORDER_SORT,
    ) -> AsyncIterator[OrderSummary]:
        """Every order matching the filter, across all pages."""

        async def fetch(page: int) -> Page[OrderSummary]:
            return await self.search(
                tickers=tickers,
                class_codes=class_codes,
                statuses=statuses,
                types=types,
                side=side,
                start=start,
                end=end,
                page=page,
                size=size,
                sort=sort,
            )

        return iter_pages(fetch)
