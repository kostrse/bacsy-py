"""Limits service."""

from __future__ import annotations

from bacsy.api._base import BaseService
from bacsy.models.limits import Limits
from bacsy.routes import Operation, Service

GET_LIMITS = Operation(name="limits", service=Service.LIMIT, method="GET", path="/api/v1/limits")


class LimitsService(BaseService):
    """``client.limits``: securities, money and derivatives limits."""

    async def get(self) -> Limits:
        """Current limits of the account."""
        return await self._call(GET_LIMITS, Limits)
