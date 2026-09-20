"""Orders, trades and non-trade operations services."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

import httpx2

from bacsy.api import NonTradeOperationsService, OrdersService, TradesService
from bacsy.api.orders import CANCEL_ORDER, CREATE_ORDER, EDIT_ORDER
from bacsy.models import (
    BalanceChange,
    ExecutionType,
    OffsetType,
    OperationStatus,
    OperationType,
    OrderIdType,
    OrderListStatus,
    OrderListType,
    OrderStatus,
    OrderType,
    Side,
    StopExecutionType,
    TimeInForce,
)

if TYPE_CHECKING:
    from bacsy.http import ApiHttpClient
    from tests.api.conftest import Recorder

CLIENT_ID = UUID("12345678-1234-5678-1234-567812345678")
OK = {"clientOrderId": str(CLIENT_ID), "status": "OK"}


async def test_create_limit_order(transport: ApiHttpClient, recorder: Recorder) -> None:
    recorder.reply(OK)

    result = await OrdersService(transport).create(
        ticker="SBER",
        class_code="TQBR",
        side=Side.BUY,
        order_type=OrderType.LIMIT,
        quantity=10,
        price=Decimal("244.35"),
        time_in_force=TimeInForce.GOOD_TILL_DATE,
        expiry_date=date(2026, 3, 1),
        client_order_id=CLIENT_ID,
    )

    assert recorder.last.method == "POST"
    assert recorder.last.url.path == "/trade-api-bff-operations/api/v1/orders"
    assert recorder.last_json() == {
        "clientOrderId": str(CLIENT_ID),
        "ticker": "SBER",
        "classCode": "TQBR",
        "side": "1",
        "orderType": "2",
        "orderQuantity": 10,
        "price": 244.35,
        "timeInForce": "3",
        "expiryDate": "20260301",
    }
    assert result.client_order_id == CLIENT_ID
    assert result.status == "OK"


async def test_create_generates_client_order_id(
    transport: ApiHttpClient, recorder: Recorder
) -> None:
    recorder.respond(lambda request: httpx2.Response(200, content=request.read()))

    result = await OrdersService(transport).create(
        ticker="SBER", class_code="TQBR", side=Side.SELL, order_type=OrderType.MARKET, quantity=1
    )

    sent = recorder.last_json()
    assert isinstance(sent, dict)
    assert result.client_order_id == UUID(str(sent["clientOrderId"]))
    assert "price" not in sent


async def test_create_conditional_order(transport: ApiHttpClient, recorder: Recorder) -> None:
    recorder.reply(OK)

    await OrdersService(transport).create(
        ticker="SBER",
        class_code="TQBR",
        side=Side.SELL,
        order_type=OrderType.CONDITIONAL,
        quantity=10,
        stop_price=Decimal("240"),
        take_price=Decimal("250.5"),
        offset=Decimal("1"),
        offset_type=OffsetType.PERCENT,
        execution_stop_loss_type=StopExecutionType.MARKET,
        client_order_id=CLIENT_ID,
    )

    sent = recorder.last_json()
    assert isinstance(sent, dict)
    assert sent["stopPrice"] == 240
    assert sent["takePrice"] == 250.5
    assert sent["offsetType"] == 1
    assert sent["executionStopLossType"] == 1


async def test_edit_order(transport: ApiHttpClient, recorder: Recorder) -> None:
    recorder.reply(OK)

    await OrdersService(transport).edit(
        order_id="260130-TQBR-12345",
        order_id_type=OrderIdType.EXCHANGE,
        quantity=5,
        price=Decimal("245"),
        client_order_id=CLIENT_ID,
    )

    assert recorder.last.url.path == "/trade-api-bff-operations/api/v1/orders/edit"
    assert recorder.last_json() == {
        "clientOrderId": str(CLIENT_ID),
        "orderId": "260130-TQBR-12345",
        "orderIdType": "2",
        "orderQuantity": 5,
        "price": 245,
    }


async def test_cancel_order(transport: ApiHttpClient, recorder: Recorder) -> None:
    recorder.reply(OK)
    original = UUID("00000000-0000-0000-0000-000000000001")

    await OrdersService(transport).cancel(order_id=original, client_order_id=CLIENT_ID)

    assert recorder.last.url.path == "/trade-api-bff-operations/api/v1/orders/cancel"
    assert recorder.last_json() == {
        "clientOrderId": str(CLIENT_ID),
        "orderId": str(original),
        "orderIdType": "1",
    }


async def test_get_order(transport: ApiHttpClient, recorder: Recorder) -> None:
    recorder.reply(
        {
            "clientOrderId": str(CLIENT_ID),
            "originalClientOrderId": str(CLIENT_ID),
            "data": {
                "messageType": "8",
                "executionType": "0",
                "orderStatus": "0",
                "orderId": "1",
                "ticker": "SBER",
                "classCode": "TQBR",
                "side": "1",
                "orderType": "2",
                "timeInForce": 1,
                "price": 244.35,
                "orderQuantity": 10,
                "executedQuantity": 0,
                "remainedQuantity": 10,
                "transactionTime": "2024-10-30T09:01:00.000Z",
                "tradeDate": "2024-10-30",
                "expiryDate": "20241130",
            },
        }
    )

    response = await OrdersService(transport).get(order_id=CLIENT_ID)

    assert recorder.last.method == "GET"
    assert dict(recorder.last.url.params) == {"orderId": str(CLIENT_ID), "orderIdType": "1"}
    report = response.data
    assert report is not None
    assert report.execution_type is ExecutionType.NEW
    assert report.order_status is OrderStatus.NEW
    assert report.time_in_force is TimeInForce.DAY
    assert report.trade_date == date(2024, 10, 30)
    assert report.expiry_date == date(2024, 11, 30)
    assert report.transaction_time == datetime(2024, 10, 30, 9, 1, tzinfo=UTC)


async def test_get_order_reads_a_partially_filled_report(
    transport: ApiHttpClient, recorder: Recorder
) -> None:
    recorder.reply(
        {
            "clientOrderId": str(CLIENT_ID),
            "originalClientOrderId": "",
            "data": {
                "executionType": "11",
                "orderStatus": "1",
                "orderId": "260909-TQBR-1",
                "ticker": "PLZL",
                "classCode": "TQBR",
                "side": "1",
                "orderType": "2",
                "averagePrice": 987.4,
                "orderQuantity": 104.0,
                "executedQuantity": 41.0,
                "remainedQuantity": 63.0,
                "tradeDate": "2026-09-09",
            },
        }
    )

    response = await OrdersService(transport).get(order_id=CLIENT_ID)

    assert response.original_client_order_id is None
    report = response.data
    assert report is not None
    assert report.order_status is OrderStatus.PARTIALLY_FILLED
    assert not report.order_status.is_final
    assert report.executed_quantity == Decimal("41")
    assert report.remained_quantity == Decimal("63")
    assert report.average_price == Decimal("987.4")
    assert report.trade_date == date(2026, 9, 9)


async def test_get_order_reads_an_absent_report_as_none(
    transport: ApiHttpClient, recorder: Recorder
) -> None:
    recorder.reply({"clientOrderId": str(CLIENT_ID)})

    response = await OrdersService(transport).get(order_id=CLIENT_ID)

    assert response.data is None


async def test_get_report_by_exchange_id(transport: ApiHttpClient, recorder: Recorder) -> None:
    recorder.reply({"clientOrderId": str(CLIENT_ID), "data": None})

    report = await OrdersService(transport).get_report(
        order_id="260130-TQBR-1", order_id_type=OrderIdType.EXCHANGE
    )

    assert report is None
    assert recorder.last.url.params["orderIdType"] == "2"


async def test_search_orders(transport: ApiHttpClient, recorder: Recorder) -> None:
    recorder.reply(
        {
            "records": [
                {
                    "orderId": "abc",
                    "orderNum": 123,
                    "ticker": "SBER",
                    "side": 2,
                    "orderType": 4,
                    "orderStatus": 3,
                    "price": 244.35,
                    "orderQuantity": 10,
                    "marketStopLoss": 1,
                    "orderDateTime": "2026-01-30T09:01:00Z",
                    "tradeDate": "2026-01-30",
                }
            ],
            "totalPages": 1,
            "totalRecords": 1,
        }
    )

    page = await OrdersService(transport).search(
        tickers=["SBER"],
        statuses=[OrderListStatus.ACTIVE],
        types=[OrderListType.STOP_LIMIT, OrderListType.LIMIT],
        side=Side.SELL,
        start=datetime(2026, 1, 26, tzinfo=UTC),
        page=0,
        size=10,
        sort=["orderDateTime,desc"],
    )

    assert recorder.last.url.path == "/trade-api-bff-order-details/api/v1/orders/search"
    assert recorder.last.url.params.multi_items() == [
        ("page", "0"),
        ("size", "10"),
        ("sort", "orderDateTime,desc"),
    ]
    assert recorder.last_json() == {
        "tickers": ["SBER"],
        "orderStatus": [3],
        "orderTypes": [4, 2],
        "side": "2",
        "startDateTime": "2026-01-26T00:00:00Z",
    }
    order = page.records[0]
    assert order.side is Side.SELL
    assert order.order_type is OrderListType.STOP_LIMIT
    assert order.order_status is OrderListStatus.ACTIVE
    assert order.market_stop_loss is StopExecutionType.MARKET
    assert page.total_records == 1


async def test_iter_search_orders_walks_pages(transport: ApiHttpClient, recorder: Recorder) -> None:
    recorder.reply({"records": [{"orderId": "1"}, {"orderId": "2"}], "totalPages": 2})
    recorder.reply({"records": [{"orderId": "3"}], "totalPages": 2})

    ids = [o.order_id async for o in OrdersService(transport).iter_search(size=2)]

    assert ids == ["1", "2", "3"]
    assert [r.url.params["page"] for r in recorder.requests] == ["0", "1"]


async def test_iter_search_stops_on_empty_page(
    transport: ApiHttpClient, recorder: Recorder
) -> None:
    recorder.reply({"records": [], "totalPages": 5})

    assert [o async for o in OrdersService(transport).iter_search()] == []
    assert len(recorder.requests) == 1


async def test_search_trades(transport: ApiHttpClient, recorder: Recorder) -> None:
    recorder.reply(
        {
            "records": [
                {
                    "tradeNum": 1,
                    "orderNum": 2,
                    "ticker": "SBER",
                    "classCode": "TQBR",
                    "instrumentType": "Stocks",
                    "side": "1",
                    "price": 244.35,
                    "tradeQuantity": 10,
                    "volume": 2443.5,
                    "tradeDateTime": "2026-01-30T09:01:00Z",
                    "settleDate": "2026-01-31",
                }
            ],
            "totalPages": 1,
            "totalRecords": 1,
        }
    )

    page = await TradesService(transport).search(
        trade_nums=[1], side=Side.BUY, end=datetime(2026, 2, 1, tzinfo=UTC)
    )

    assert recorder.last.url.path == "/trade-api-bff-trade-details/api/v1/trades/search"
    assert recorder.last.url.params.multi_items() == [
        ("page", "0"),
        ("size", "100"),
        ("sort", "tradeDateTime"),
    ]
    assert recorder.last_json() == {
        "tradeNums": [1],
        "side": "1",
        "endDateTime": "2026-02-01T00:00:00Z",
    }
    trade = page.records[0]
    assert trade.volume == Decimal("2443.5")
    assert trade.settle_date == date(2026, 1, 31)


async def test_iter_search_trades(transport: ApiHttpClient, recorder: Recorder) -> None:
    recorder.reply({"records": [{"tradeNum": 1}], "totalPages": 1})

    nums = [t.trade_num async for t in TradesService(transport).iter_search()]

    assert nums == [1]


async def test_search_operations(transport: ApiHttpClient, recorder: Recorder) -> None:
    recorder.reply(
        {
            "pageSize": 50,
            "records": [
                {
                    "id": "12345678-1234-5678-1234-567812345678",
                    "type": "Dividend",
                    "status": "Approved",
                    "balanceChange": "Positive",
                    "date": "2026-01-30T09:01:00Z",
                    "sum": 100.5,
                    "currency": "RUB",
                    "ticker": "SBER",
                    "isIia": False,
                }
            ],
        }
    )

    page = await NonTradeOperationsService(transport).search(
        types=[OperationType.DIVIDEND, OperationType.PAY_IN],
        statuses=[OperationStatus.APPROVED],
        currencies=["RUB"],
        size=50,
    )

    assert recorder.last.url.path == "/trade-api-bff-nontrade-operations/api/v1/operations/search"
    assert dict(recorder.last.url.params) == {"page": "0", "size": "50"}
    assert recorder.last_json() == {
        "currencies": ["RUB"],
        "operationTypes": ["Dividend", "PayIn"],
        "statuses": ["Approved"],
    }
    operation = page.records[0]
    assert operation.type is OperationType.DIVIDEND
    assert operation.balance_change is BalanceChange.POSITIVE
    assert operation.sum == Decimal("100.5")
    assert operation.id == CLIENT_ID


async def test_iter_search_operations(transport: ApiHttpClient, recorder: Recorder) -> None:
    recorder.reply({"records": [{"type": "PayIn"}, {"type": "PayOut"}]})
    recorder.reply({"records": [{"type": "Dividend"}]})

    types = [o.type async for o in NonTradeOperationsService(transport).iter_search(size=2)]

    assert types == [OperationType.PAY_IN, OperationType.PAY_OUT, OperationType.DIVIDEND]


def test_order_mutations_need_a_write_token() -> None:
    assert {op.scope for op in (CREATE_ORDER, EDIT_ORDER, CANCEL_ORDER)} == {"write"}
    assert not any(op.idempotent for op in (CREATE_ORDER, EDIT_ORDER, CANCEL_ORDER))
