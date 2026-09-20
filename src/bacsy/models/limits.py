"""Trading limits: securities, money and derivatives positions with settlement terms."""

from __future__ import annotations

from decimal import Decimal

from pydantic import Field, model_validator

from bacsy.models._wire import as_wire_dict, is_nested, nest
from bacsy.models.base import BaseApiModel, OptionalMoexDate, OptionalStr
from bacsy.models.common import Board, InstrumentKey
from bacsy.models.enums import InstrumentType, Term

_BOARD = {"classCode": "class_code", "exchange": "exchange"}


def _nest_board(data: object) -> object:
    payload = as_wire_dict(data)
    if payload is None or is_nested(payload.get("board")):
        return data
    nest(payload, "board", _BOARD)
    return payload


class TermQuantity(BaseApiModel):
    """A quantity attached to a settlement term."""

    type: Term | None = None
    """Settlement term."""
    value: Decimal | None = None
    """Quantity."""


class DepoLimit(BaseApiModel):
    """Securities position."""

    ticker: OptionalStr = None
    """Instrument ticker."""
    board: Board | None = None
    """Board the position is held on."""
    instrument_type: InstrumentType | None = None
    """Instrument category."""
    average_price: Decimal | None = None
    """Weighted average acquisition price; in percent of face for a bond priced that way."""
    quantity: TermQuantity | None = None
    """Quantity in units, with its settlement term."""
    quantity_batch: TermQuantity | None = None
    """Quantity in lots, with its settlement term."""
    locked_buy_quantity: Decimal | None = None
    """Units locked for active buy orders."""
    locked_buy_value: Decimal | None = None
    """Money in active buy orders for the security."""
    locked_sell_quantity: Decimal | None = None
    """Units locked for active sell orders."""
    locked_sell_value: Decimal | None = None
    """Money in active sell orders for the security."""
    load_date: OptionalMoexDate = None
    """Business date the data was last loaded for."""

    @property
    def key(self) -> InstrumentKey | None:
        """Ticker and class code, or ``None`` when either is missing."""
        return InstrumentKey.maybe(self.ticker, self.board.class_code if self.board else None)

    @model_validator(mode="before")
    @classmethod
    def _nest_board(cls, data: object) -> object:
        return _nest_board(data)


class FutureHolding(BaseApiModel):
    """Derivatives position."""

    ticker: OptionalStr = None
    """Instrument ticker."""
    board: Board | None = None
    """Board the position is held on."""
    instrument_type: InstrumentType | None = None
    """Instrument category."""
    average_price: Decimal | None = None
    """Effective price of the position."""
    total_net: Decimal | None = None
    """Current net position, contracts; negative for a short."""
    position_value: Decimal | None = None
    """Value of the position."""
    var_margin: Decimal | None = None
    """Variation margin computed within the exchange's price limits."""
    real_var_margin: Decimal | None = None
    """Variation margin actually credited at clearing."""
    total_var_margin: Decimal | None = None
    """Variation margin credited across all positions at the main clearing."""
    cbpl_planned: Decimal | None = None
    """Planned net position."""
    trade_date: OptionalMoexDate = None
    """Trading session date."""
    execution_date: OptionalMoexDate = None
    """Contract execution date. A perpetual contract carries ``2100-01-01``."""

    @property
    def key(self) -> InstrumentKey | None:
        """Ticker and class code, or ``None`` when either is missing."""
        return InstrumentKey.maybe(self.ticker, self.board.class_code if self.board else None)

    @model_validator(mode="before")
    @classmethod
    def _nest_board(cls, data: object) -> object:
        return _nest_board(data)


class FuturesLimit(BaseApiModel):
    """Derivatives market money limit and collateral usage."""

    currency_code: OptionalStr = None
    """Currency code."""
    exchange: OptionalStr = None
    """Exchange code."""
    instrument_type: OptionalStr = None
    """Instrument type code, e.g. ``MONEY``."""
    cbp_limit: Decimal | None = None
    """Open position limit."""
    cbpl_used: Decimal | None = None
    """Value of the current net positions."""
    cbpl_used_for_orders: Decimal | None = None
    """Part of `cbpl_used` reserved for active orders."""
    cbpl_used_for_positions: Decimal | None = None
    """Part of `cbpl_used` reserved for open positions."""
    cbpl_planned: Decimal | None = None
    """Value of the planned net positions."""
    var_margin: Decimal | None = None
    """Variation margin computed within the exchange's price limits."""
    real_var_margin: Decimal | None = None
    """Variation margin actually credited at clearing."""
    accrued_int: Decimal | None = Field(default=None, alias="accruedint")
    """Variation margin accrued during the current day."""
    options_premium: Decimal | None = None
    """Options premiums."""
    load_date: OptionalMoexDate = None
    """Business date the data was last loaded for."""


class MoneyLimit(BaseApiModel):
    """Money position in one currency."""

    currency_code: OptionalStr = None
    """Currency code."""
    exchange: OptionalStr = None
    """Exchange code."""
    instrument_type: OptionalStr = None
    """Instrument type code, e.g. ``MONEY``."""
    average_price: Decimal | None = None
    """Weighted average rate the currency was acquired at."""
    quantity: TermQuantity | None = None
    """Amount, with its settlement term."""
    locked: Decimal | None = None
    """Money held in active orders."""
    load_date: OptionalMoexDate = None
    """Business date the data was last loaded for."""


class Limits(BaseApiModel):
    """Limits of the account: securities, derivatives and money positions."""

    depo_limit: list[DepoLimit] = Field(default_factory=list)
    """Securities positions."""
    future_holding: list[FutureHolding] = Field(default_factory=list)
    """Derivatives positions."""
    futures_limits: list[FuturesLimit] = Field(default_factory=list)
    """Derivatives market money limits."""
    money_limits: list[MoneyLimit] = Field(default_factory=list)
    """Money positions per currency."""
