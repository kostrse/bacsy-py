"""Margin indicators service."""

from __future__ import annotations

from bacsy.api._base import BaseService
from bacsy.models.margin import InstrumentDiscount
from bacsy.routes import Operation, Service

GET_INSTRUMENT_DISCOUNTS = Operation(
    name="getInstrumentsDiscounts",
    service=Service.MARGINAL_INDICATORS,
    method="GET",
    path="/api/v1/instruments-discounts",
)


class MarginService(BaseService):
    """``client.margin``: margin lending parameters."""

    async def get_instrument_discounts(self) -> list[InstrumentDiscount]:
        """Long and short discount rates per instrument."""
        return await self._call(GET_INSTRUMENT_DISCOUNTS, list[InstrumentDiscount])
