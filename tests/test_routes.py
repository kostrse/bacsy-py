"""Operation descriptors and service prefixes."""

from __future__ import annotations

from bacsy.routes import Operation, Service, operation_for_raw_request, service_for_path


def test_url_joins_service_prefix_and_path() -> None:
    op = Operation(name="portfolio", service=Service.PORTFOLIO, method="GET", path="/api/v1/x")

    assert op.url() == "/trade-api-bff-portfolio/api/v1/x"


def test_url_substitutes_path_params() -> None:
    op = Operation(
        name="status", service=Service.OPERATIONS, method="GET", path="/api/v1/orders/{id}"
    )

    assert op.url(id="abc") == "/trade-api-bff-operations/api/v1/orders/abc"


def test_operations_are_idempotent_by_default() -> None:
    op = Operation(name="x", service=Service.LIMIT, method="POST", path="/p")

    assert op.idempotent
    assert op.scope == "read"


def test_every_service_has_a_leading_slash() -> None:
    for service in Service:
        assert service.value.startswith("/trade-api-")


def test_service_for_path() -> None:
    assert service_for_path("/trade-api-bff-limit/api/v1/limits") is Service.LIMIT
    assert service_for_path("/trade-api-bff-limit") is Service.LIMIT
    assert service_for_path("/trade-api-bff-limits/x") is None
    assert service_for_path("/api/v1/limits") is None


def test_operation_for_raw_request() -> None:
    get = operation_for_raw_request("get", "/trade-api-bff-limit/api/v1/limits")
    post = operation_for_raw_request("POST", "/trade-api-bff-operations/api/v1/orders")

    assert get is not None
    assert get.idempotent
    assert get.url() == "/trade-api-bff-limit/api/v1/limits"
    assert post is not None
    assert not post.idempotent
    assert get.scope == "read"
    assert post.scope == "write"
    search = operation_for_raw_request("POST", "/trade-api-bff-trade-details/api/v1/trades/search")
    assert search is not None
    assert search.scope == "read"
    assert operation_for_raw_request("GET", "/api/v1/limits") is None
