"""Portfolio service."""

from __future__ import annotations

from typing import TYPE_CHECKING

from bacsy.api._base import BaseService
from bacsy.models.portfolio import DEFAULT_TERM, Portfolio, Position
from bacsy.routes import Operation, Service

if TYPE_CHECKING:
    from bacsy.models.enums import Term

GET_PORTFOLIO = Operation(
    name="portfolio", service=Service.PORTFOLIO, method="GET", path="/api/v1/portfolio"
)


class PortfolioService(BaseService):
    """``client.portfolio``: positions of the account the token belongs to."""

    async def get(self) -> Portfolio:
        """Return the portfolio snapshot, with every position in every settlement term."""
        return await self._call(GET_PORTFOLIO, Portfolio)

    async def get_positions(self, term: Term = DEFAULT_TERM) -> list[Position]:
        """Return the positions of one settlement term, money balances included.

        Makes the same request as `get` and selects `term` from the snapshot.

        Args:
            term: Settlement term to select. Defaults to `DEFAULT_TERM`, the planned
                position.
        """
        return (await self.get()).positions(term)
