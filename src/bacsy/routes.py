"""Routing descriptors: which microservice an operation lives on and how to call it.

This module is a leaf: it imports nothing else from bacsy.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

HttpMethod = Literal["GET", "POST"]
ScopeName = Literal["read", "write"]
"""Token scope an operation needs; a write token also serves read operations."""


class Service(StrEnum):
    """Path prefix of each BCS Trade API microservice.

    Every service repeats the `/api/v1` prefix below its own segment and is rate limited
    independently.
    """

    PORTFOLIO = "/trade-api-bff-portfolio"
    OPERATIONS = "/trade-api-bff-operations"
    ORDER_DETAILS = "/trade-api-bff-order-details"
    LIMIT = "/trade-api-bff-limit"
    MARGINAL_INDICATORS = "/trade-api-bff-marginal-indicators"
    NONTRADE_OPERATIONS = "/trade-api-bff-nontrade-operations"
    TRADE_DETAILS = "/trade-api-bff-trade-details"
    INFORMATION = "/trade-api-information-service"
    MARKET_DATA = "/trade-api-market-data-connector"


@dataclass(frozen=True, slots=True, kw_only=True)
class Operation:
    """A single REST operation.

    `idempotent` drives retry decisions: only idempotent operations may be retried after
    a transport failure or a server error. `scope` selects the access token presented;
    only order create, edit and cancel need a write token.
    """

    name: str
    service: Service
    method: HttpMethod
    path: str
    idempotent: bool = True
    scope: ScopeName = "read"

    def url(self, **path_params: str) -> str:
        """Return the URL path, including the service prefix, with `path_params` substituted."""
        return f"{self.service.value}{self.path.format(**path_params)}"


def service_for_path(path: str) -> Service | None:
    """Return the service whose prefix is the first segment of `path`, or `None`."""
    for service in Service:
        if path == service.value or path.startswith(service.value + "/"):
            return service
    return None


def operation_for_raw_request(method: str, path: str) -> Operation | None:
    """Return an `Operation` describing a raw request, or `None` for an unknown service.

    Only `GET` requests are idempotent. A `POST` to `Service.OPERATIONS` needs a write
    token; every other request uses a read token.
    """
    service = service_for_path(path)
    if service is None:
        return None
    http_method: HttpMethod = "GET" if method.upper() == "GET" else "POST"
    return Operation(
        name=f"{method.upper()} {path}",
        service=service,
        method=http_method,
        path=path.removeprefix(service.value),
        idempotent=method.upper() == "GET",
        scope="write" if service is Service.OPERATIONS and http_method == "POST" else "read",
    )
