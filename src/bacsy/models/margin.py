"""Margin lending indicators."""

from __future__ import annotations

from decimal import Decimal

from pydantic import Field, model_validator

from bacsy.models._wire import as_wire_dict, is_nested
from bacsy.models.base import BaseApiModel, OptionalStr
from bacsy.models.common import Board, InstrumentKey
from bacsy.models.enums import RiskLevel


def _nest_board(data: object) -> object:
    payload = as_wire_dict(data)
    if payload is None or is_nested(payload.get("board")):
        return data
    board = payload.pop("board", None)
    if board:
        payload["board"] = {"class_code": board}
    return payload


class InstrumentDiscount(BaseApiModel):
    """Margin discount rates of one instrument."""

    ticker: OptionalStr = None
    """Instrument ticker."""
    discount_long: Decimal | None = None
    """Discount rate for long positions."""
    discount_short: Decimal | None = None
    """Discount rate for short positions."""


class AgreementData(BaseApiModel):
    """The brokerage account a margin snapshot describes."""

    number: OptionalStr = None
    """Account number."""
    is_iia: bool | None = None
    """Whether the account is an individual investment account (IIA)."""
    display_name: OptionalStr = None
    """Display name of the account."""
    subaccount_id: OptionalStr = None
    """Sub-account identifier."""
    color: OptionalStr = None
    """Hex colour code assigned to the account."""


class PortfolioCurrentValue(BaseApiModel):
    """Portfolio value and its changes."""

    current_value_rub: Decimal | None = None
    """Current value, RUB."""
    daily_portfolio_change_rub: Decimal | None = None
    """Change over the day, RUB."""
    daily_portfolio_change_perc: Decimal | None = None
    """Change over the day, percent."""
    total_portfolio_change_rub: Decimal | None = None
    """Change over the whole holding period, RUB."""
    total_portfolio_change_perc: Decimal | None = None
    """Change over the whole holding period, percent."""
    collateral_available: Decimal | None = None
    """Available collateral."""
    var_margin: Decimal | None = None
    """Variation margin."""


class PortfolioStability(BaseApiModel):
    """Margin stability of the portfolio."""

    is_margin_on: bool | None = None
    """Whether margin trading is enabled."""
    borrowed_funds: Decimal | None = None
    """Total debt, RUB."""
    stability_status_id: int | None = None
    """Stability status identifier, 0 to 5."""
    stability_status_name: OptionalStr = None
    """Stability status text."""
    refill_sum: Decimal | None = None
    """Amount to deposit to exit a margin call."""


class FortsStability(BaseApiModel):
    """Stability of the derivatives market (FORTS) position."""

    own_funds: Decimal | None = None
    """Own funds."""
    free_cash: Decimal | None = None
    """Free funds."""
    stability_status_id: int | None = None
    """Stability status identifier."""
    stability_status_name: OptionalStr = None
    """Stability status text."""
    refill_sum: Decimal | None = None
    """Amount to deposit."""
    forts_margin_call: Decimal | None = None
    """Margin call level."""
    forts_forced_closure: Decimal | None = None
    """Forced closure level."""
    risk_level: RiskLevel | None = None
    """Client risk category."""
    options_premium: Decimal | None = None


class MarginParameters(BaseApiModel):
    """Parameters of the margin portfolio."""

    margin_value: Decimal | None = None
    """Value of margin assets."""
    collateral: Decimal | None = None
    """Collateral."""
    margin_call: Decimal | None = None
    """Margin call level."""
    forced_closure: Decimal | None = None
    """Forced closure level."""


class CurrencyAmount(BaseApiModel):
    """An amount in one currency."""

    currency: OptionalStr = None
    """Currency code."""
    sum: Decimal | None = None
    """Amount."""


class MoneyDebt(BaseApiModel):
    """Money debt in total and per currency."""

    total_money_debt: Decimal | None = None
    """Total debt."""
    debt_by_currency: list[CurrencyAmount] = Field(default_factory=list)
    """Debt per currency."""


class MarginSecurity(BaseApiModel):
    """One margin position."""

    ticker: OptionalStr = None
    """Exchange ticker."""
    board: Board | None = None
    """Board the position is held on; the margin stream names no exchange."""
    display_name: OptionalStr = None
    """Display name."""
    quantity: Decimal | None = None
    """Quantity."""
    current_value: Decimal | None = None
    """Current value."""
    currency: OptionalStr = None
    """Currency."""
    discount: Decimal | None = None
    """Discount, percent."""

    @property
    def key(self) -> InstrumentKey | None:
        """Ticker and class code, or ``None`` when either is missing."""
        return InstrumentKey.maybe(self.ticker, self.board.class_code if self.board else None)

    @model_validator(mode="before")
    @classmethod
    def _nest_board(cls, data: object) -> object:
        return _nest_board(data)


class MarginSecurities(BaseApiModel):
    """Margin positions."""

    total_margin_security: Decimal | None = None
    """Total debt across the positions."""
    margin_by_security: list[MarginSecurity] = Field(default_factory=list)
    """Positions."""


class MarginFuturesPosition(BaseApiModel):
    """One futures position, as the margin indicators describe it."""

    ticker: OptionalStr = None
    """Exchange ticker."""
    board: Board | None = None
    """Board the position is held on; the margin stream names no exchange."""
    display_name: OptionalStr = None
    """Display name."""
    current_value: Decimal | None = None
    """Current value."""
    balance_value: Decimal | None = None
    """Value at the opening price."""
    futures_collateral: Decimal | None = None
    """Collateral held for the position."""
    discount: Decimal | None = None
    """Discount."""

    @property
    def key(self) -> InstrumentKey | None:
        """Ticker and class code, or ``None`` when either is missing."""
        return InstrumentKey.maybe(self.ticker, self.board.class_code if self.board else None)

    @model_validator(mode="before")
    @classmethod
    def _nest_board(cls, data: object) -> object:
        return _nest_board(data)


class FuturesParameters(BaseApiModel):
    """Futures positions."""

    futures_value: Decimal | None = None
    """Total value of the positions."""
    futures_portfolio: list[MarginFuturesPosition] = Field(default_factory=list)
    """Positions."""


class MarginIndicators(BaseApiModel):
    """Snapshot pushed by the marginal-indicators stream."""

    agreement_data: AgreementData | None = None
    """The account the snapshot describes."""
    portfolio_current_value: PortfolioCurrentValue | None = None
    """Portfolio value and its changes."""
    portfolio_stability: PortfolioStability | None = None
    """Margin stability of the portfolio."""
    forts_stability: FortsStability | None = None
    """Stability of the derivatives position."""
    margin_parameters: MarginParameters | None = None
    """Margin portfolio parameters."""
    cash_by_currency: list[CurrencyAmount] = Field(default_factory=list)
    """Free cash per currency."""
    money_debt: MoneyDebt | None = None
    """Money debt."""
    margin_securities: MarginSecurities | None = None
    """Margin positions."""
    futures_parameters: FuturesParameters | None = None
    """Futures positions."""
