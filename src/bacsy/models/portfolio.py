"""Portfolio positions: one class per kind of position, and the snapshot they come in.

The API reports every position as one flat object tagged by ``type``. The classes here
split that object by kind, so each carries only the fields that mean something for it:
`MoneyPosition` and `FuturesMoneyPosition` for cash, `EquityPosition` and
`BondPosition` for securities,
`FuturesPosition` for derivatives, with `UnknownPosition` for a kind this library does
not know. `Position` is the union `Portfolio` yields.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated

from pydantic import Discriminator, Field, RootModel, Tag, model_validator

from bacsy.models._wire import as_wire_dict, get_wire, is_nested, nest
from bacsy.models.base import BaseApiModel, OptionalMoexDate, OptionalStr
from bacsy.models.common import Board, InstrumentKey, MultiCurrencyValue, ProfitLoss
from bacsy.models.enums import InstrumentType, PositionType, Term, UpperType

DEFAULT_TERM = Term.T365
"""Settlement term selected by default: the planned position."""

PERPETUAL_EXPIRY = date(2100, 1, 1)
"""The expiry date the API reports for a perpetual futures contract."""

_BALANCE_VALUE = {
    "balanceValue": "value",
    "balanceValueRub": "rub",
    "balanceValueUsd": "usd",
    "balanceValueEur": "eur",
}
_CURRENT_VALUE = {
    "currentValue": "value",
    "currentValueRub": "rub",
    "currentValueUsd": "usd",
    "currentValueEur": "eur",
}
_DAILY_PL = {"dailyPL": "amount", "dailyPercentPL": "percent"}
_UNREALIZED_PL = {"unrealizedPL": "amount", "unrealizedPercentPL": "percent"}
_BOARD = {"board": "class_code", "exchange": "exchange"}


class BasePosition(BaseApiModel):
    """Fields every kind of position carries: what it is, how much, and what it is worth."""

    type: PositionType | None = None
    """Kind of position; the tag the concrete class was chosen by."""
    account: OptionalStr = None
    """Trading account."""
    term: Term | None = None
    """Settlement term this line describes."""
    upper_type: UpperType | None = None
    """Top-level market group."""
    display_name: OptionalStr = None
    """Display name."""
    quantity: Decimal | None = None
    """Quantity in units; the amount for a money position."""
    locked: Decimal | None = None
    """Part of `quantity` held for active orders or as collateral."""
    balance_value: MultiCurrencyValue = Field(default_factory=MultiCurrencyValue)
    """Value at the opening price, in the price currency and converted."""
    current_value: MultiCurrencyValue = Field(default_factory=MultiCurrencyValue)
    """Current value, in the price currency and converted."""
    daily_pl: ProfitLoss = Field(default_factory=ProfitLoss, alias="dailyPL")
    """Change over the day."""
    unrealized_pl: ProfitLoss = Field(default_factory=ProfitLoss, alias="unrealizedPL")
    """Change since the position was opened."""
    portfolio_share: Decimal | None = None
    """Share of the portfolio's RUB value, percent."""
    is_blocked: bool | None = None
    """Whether the class is blocked."""
    is_blocked_trade_account: bool | None = None
    """Whether the trading account is blocked."""

    @model_validator(mode="before")
    @classmethod
    def _nest_valuation(cls, data: object) -> object:
        payload = as_wire_dict(data)
        if payload is None:
            return data
        nest(payload, "balanceValue", _BALANCE_VALUE)
        nest(payload, "currentValue", _CURRENT_VALUE)
        nest(payload, "dailyPL", _DAILY_PL)
        nest(payload, "unrealizedPL", _UNREALIZED_PL)
        return payload


class CashPosition(BasePosition):
    """A cash balance in one currency.

    `quantity` is the amount in `currency`; `current_value.value` repeats it and
    `current_value.rub` is the RUB equivalent at `current_rate`. `locked` is the part
    held for active orders and as collateral, and `locked_for_futures` the collateral part
    of it.
    """

    currency: OptionalStr = None
    """Currency code, e.g. ``RUB``."""
    exchange: OptionalStr = None
    """Exchange the balance is held on."""
    current_rate: Decimal | None = Field(default=None, alias="currentPrice")
    """Current rate, RUB per unit of `currency`."""
    balance_rate: Decimal | None = Field(default=None, alias="balancePrice")
    """Average rate the currency was acquired at, RUB per unit."""
    locked_for_futures: Decimal | None = None
    """Collateral for futures positions held out of this balance."""


class MoneyPosition(CashPosition):
    """The cash balance of the main account in one currency (``moneyLimit``).

    When the derivatives account is combined with the main one, the collateral for
    futures is held out of this balance and reported in `locked_for_futures`.
    """


class FuturesMoneyPosition(CashPosition):
    """The derivatives-market cash balance in one currency (``futuresLimit``), reported
    separately from `MoneyPosition`."""


class InstrumentPosition(BasePosition):
    """A position in a traded instrument, identified by ticker and board."""

    ticker: OptionalStr = None
    """Instrument ticker."""
    board: Board | None = None
    """Board the position is held on; fixes the currency of every price below."""
    instrument_type: InstrumentType | None = None
    """Instrument category."""
    currency: OptionalStr = None
    """Price currency: the settlement currency of `board`."""
    current_price: Decimal | None = None
    """Current price per unit."""
    balance_price: Decimal | None = None
    """Opening price of the position per unit."""
    scale: int | None = None
    """Price precision, decimal places."""
    minimum_step: Decimal | None = None
    """Minimum price step."""
    price_unit: OptionalStr = None
    """Price unit label from the trading system: ``%`` marks a bond whose exchange price is
    percent of face. The prices on this position are nonetheless in `currency`."""

    @property
    def key(self) -> InstrumentKey | None:
        """Ticker and class code, or ``None`` when either is missing."""
        return InstrumentKey.maybe(self.ticker, self.board.class_code if self.board else None)

    @model_validator(mode="before")
    @classmethod
    def _nest_board(cls, data: object) -> object:
        payload = as_wire_dict(data)
        if payload is None or is_nested(payload.get("board")):
            return data
        # An empty board means the position has none; the exchange alone is not a board.
        if not payload.get("board"):
            payload.pop("board", None)
            payload.pop("exchange", None)
            return payload
        nest(payload, "board", _BOARD)
        return payload


class SecurityPosition(InstrumentPosition):
    """A position in an issued security (``depoLimit``): a share, fund unit or bond."""

    face_value: Decimal | None = None
    """Nominal per unit, in the instrument's nominal currency: share par or bond face."""


class EquityPosition(SecurityPosition):
    """A position in a share, depositary receipt or fund unit.

    Which of those it is, read from `instrument_type`.
    """


class BondPosition(SecurityPosition):
    """A position in a bond, eurobond or note.

    `current_price` and `balance_price` are per bond in `currency`, the settlement
    currency of `board`, not percent of face as on a quote; a USD-face bond held on a
    RUB board is priced in RUB. `accrued_income` is per bond in the same currency, and
    ``current_value.value == quantity * (current_price + accrued_income)``.
    """

    accrued_income: Decimal | None = None
    """Accrued coupon income per bond, in `currency`."""

    @property
    def accrued_total(self) -> Decimal | None:
        """Accrued coupon income of the whole position, in `currency`."""
        if self.quantity is None or self.accrued_income is None:
            return None
        return self.quantity * self.accrued_income


class FuturesPosition(InstrumentPosition):
    """A futures position (``futuresHolding``).

    `quantity` is signed: negative for a short. Prices are per unit of the underlying
    or per contract, as the exchange quotes the contract, and
    ``current_value.value == quantity * current_price * multiplier``.
    `unrealized_pl.amount` is the variation margin accumulated since the position opened.
    """

    multiplier: Decimal | None = Field(default=None, alias="ratioQuantity")
    """Contract value per price unit: 1 when the price is quoted per contract."""
    expiry: OptionalMoexDate = Field(default=None, alias="expireDate")
    """Execution date; a perpetual contract carries `PERPETUAL_EXPIRY`."""
    collateral: Decimal | None = Field(default=None, alias="lockedForFutures")
    """Collateral held for the position."""
    base_asset_ticker: OptionalStr = None
    """Ticker of the underlying, when the API provides it."""

    @property
    def is_perpetual(self) -> bool:
        """``True`` for a perpetual contract, which the API dates `PERPETUAL_EXPIRY`."""
        return self.expiry is not None and self.expiry >= PERPETUAL_EXPIRY


class OtcPosition(InstrumentPosition):
    """An over-the-counter position (``otcLimit``)."""

    face_value: Decimal | None = None
    """Nominal per unit."""


class UnknownPosition(BasePosition):
    """A position of a kind this library does not know, with every field the API sends."""

    ticker: OptionalStr = None
    """Instrument ticker."""
    board: OptionalStr = None
    """Class code of the security."""
    exchange: OptionalStr = None
    """Exchange code."""
    instrument_type: InstrumentType | None = None
    """Instrument category."""
    currency: OptionalStr = None
    """Price currency."""
    current_price: Decimal | None = None
    """Current price."""
    balance_price: Decimal | None = None
    """Opening price of the position."""
    scale: int | None = None
    """Price precision, decimal places."""
    minimum_step: Decimal | None = None
    """Minimum price step."""
    price_unit: OptionalStr = None
    """Price unit label."""
    ratio_quantity: Decimal | None = None
    """Units per lot or contract multiplier, as the API sends it."""
    face_value: Decimal | None = None
    """Nominal per unit."""
    accrued_income: Decimal | None = None
    """Accrued coupon income per unit."""
    base_asset_ticker: OptionalStr = None
    """Ticker of the underlying."""
    expire_date: OptionalMoexDate = None
    """Expiry date."""
    locked_for_futures: Decimal | None = None
    """Collateral held for futures."""


_TAG_BY_TYPE: dict[str, str] = {
    PositionType.MONEY_LIMIT: "money",
    PositionType.FUTURES_HOLDING: "futures",
    PositionType.FUTURES_LIMIT: "futures_money",
    PositionType.OTC_LIMIT: "otc",
}


def _position_tag(value: object) -> str:
    kind = get_wire(value, "type", "type")
    if kind == PositionType.DEPO_LIMIT:
        instrument_type = get_wire(value, "instrumentType", "instrument_type")
        is_debt = isinstance(instrument_type, str) and InstrumentType(instrument_type).is_debt
        return "bond" if is_debt else "equity"
    if isinstance(kind, str):
        return _TAG_BY_TYPE.get(kind, "unknown")
    return "unknown"


Position = Annotated[
    Annotated[MoneyPosition, Tag("money")]
    | Annotated[EquityPosition, Tag("equity")]
    | Annotated[BondPosition, Tag("bond")]
    | Annotated[FuturesPosition, Tag("futures")]
    | Annotated[OtcPosition, Tag("otc")]
    | Annotated[FuturesMoneyPosition, Tag("futures_money")]
    | Annotated[UnknownPosition, Tag("unknown")],
    Discriminator(_position_tag),
]
"""Any position in a `Portfolio`, chosen by its ``type`` and, for securities, its
``instrumentType``."""


class Portfolio(RootModel[list[Position]]):
    """A portfolio snapshot: positions by settlement term.

    Each holding appears once per settlement term. ``T0`` is the settled position,
    ``T1`` and ``T2`` the position after the trades settling on those days have cleared,
    and ``T365`` the planned position with every unsettled trade counted. The lines of a
    holding carry the same values while none of its trades is pending. `positions`
    selects one term, `select` one term and one kind, and `by_term` groups the lines.
    """

    @property
    def lines(self) -> list[Position]:
        """The lines as received, in every settlement term."""
        return self.root

    @property
    def terms(self) -> list[Term]:
        """Distinct settlement terms present, in order of first appearance."""
        return list(dict.fromkeys(line.term for line in self.root if line.term is not None))

    def positions(self, term: Term = DEFAULT_TERM) -> list[Position]:
        """Return the lines of one settlement term, in the order received.

        Lines without a term are never selected.

        Args:
            term: Settlement term to select. Defaults to `DEFAULT_TERM`.
        """
        return [line for line in self.root if line.term == term]

    def select[T: BasePosition](self, kind: type[T], term: Term = DEFAULT_TERM) -> list[T]:
        """Return the positions of one kind in one settlement term.

        ``kind`` may be a concrete class or a base: `select(BondPosition)` gives the
        bonds, `select(SecurityPosition)` equities and bonds, `select(InstrumentPosition)`
        everything with a `key`, `select(CashPosition)` every cash balance.

        Args:
            kind: Position class to select, by ``isinstance``.
            term: Settlement term to select. Defaults to `DEFAULT_TERM`.
        """
        return [line for line in self.root if line.term == term and isinstance(line, kind)]

    def by_term(self) -> dict[Term, list[Position]]:
        """Return the lines grouped by settlement term, omitting lines without one."""
        grouped: dict[Term, list[Position]] = {}
        for line in self.root:
            if line.term is not None:
                grouped.setdefault(line.term, []).append(line)
        return grouped
