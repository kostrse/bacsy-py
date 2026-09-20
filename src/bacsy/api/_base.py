"""Plumbing shared by the typed services."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import TypeAdapter, ValidationError

from bacsy.exceptions import ProtocolError
from bacsy.models.base import format_utc

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
    from datetime import datetime

    from pydantic import BaseModel

    from bacsy._json import JsonValue
    from bacsy.http import ApiHttpClient, QueryParams
    from bacsy.models.common import Page
    from bacsy.routes import Operation

MAX_PAGE_SIZE = 100


def check_page(page: int, size: int) -> None:
    if page < 0:
        msg = "page must be >= 0"
        raise ValueError(msg)
    if not 1 <= size <= MAX_PAGE_SIZE:
        msg = f"size must be between 1 and {MAX_PAGE_SIZE}"
        raise ValueError(msg)


def iso_utc(value: datetime) -> str:
    """Format a datetime as the API expects it in query strings."""
    return format_utc(value)


class BaseService:
    """Base of the typed services: calls an `ApiHttpClient` and validates responses.

    A response that does not match the expected model raises `ProtocolError`.
    """

    def __init__(self, transport: ApiHttpClient) -> None:
        self._transport: ApiHttpClient = transport

    async def _call[T](
        self,
        operation: Operation,
        model: type[T],
        *,
        path_params: Mapping[str, str] | None = None,
        params: QueryParams | None = None,
        body: BaseModel | None = None,
    ) -> T:
        payload = await self._transport.call(
            operation, path_params=path_params, params=params, body=body
        )
        return self._validate(operation, model, payload)

    @staticmethod
    def _validate[T](operation: Operation, model: type[T], payload: JsonValue) -> T:
        try:
            return TypeAdapter(model).validate_python(payload)
        except ValidationError as exc:
            msg = f"{operation.name} returned an unexpected response: {exc}"
            raise ProtocolError(msg, source=operation.name, payload=payload) from exc


async def iter_pages[T](
    fetch: Callable[[int], Awaitable[Page[T]]], *, start_page: int = 0
) -> AsyncIterator[T]:
    """Yield records from consecutive pages until ``total_pages`` is reached."""
    page = start_page
    while True:
        result = await fetch(page)
        for record in result.records:
            yield record
        page += 1
        if not result.records or page >= result.total_pages:
            return


async def iter_until_short[T](
    fetch: Callable[[int], Awaitable[Sequence[T]]], *, size: int, start_page: int = 0
) -> AsyncIterator[T]:
    """Yield records from consecutive pages until a page comes back shorter than ``size``."""
    page = start_page
    while True:
        records = await fetch(page)
        for record in records:
            yield record
        if len(records) < size:
            return
        page += 1
