"""Enumerations used by the API, with tolerant parsing of response values.

Response-side enums derive from `LenientStrEnum` or `LenientIntEnum`. A value without a
declared member does not fail validation; it becomes a pseudo-member whose `is_known`
is ``False``.
"""

from __future__ import annotations

from enum import IntEnum, StrEnum
from typing import Self, override


class LenientStrEnum(StrEnum):
    """String enum that accepts unknown values instead of raising."""

    @classmethod
    @override
    def _missing_(cls, value: object) -> Self | None:
        if isinstance(value, int) and not isinstance(value, bool):
            # Some services send numeric codes as integers where others use strings.
            value = str(value)
            if value in cls._value2member_map_:
                return cls(value)
        if not isinstance(value, str):
            return None
        member = str.__new__(cls, value)
        member._name_ = f"UNKNOWN({value!r})"
        member._value_ = value
        return member

    @property
    def is_known(self) -> bool:
        """``True`` for a declared member, ``False`` for a pseudo-member of an unknown value."""
        return self._name_ in type(self).__members__


class LenientIntEnum(IntEnum):
    """Integer enum that accepts unknown values instead of raising."""

    @classmethod
    @override
    def _missing_(cls, value: object) -> Self | None:
        if isinstance(value, str) and value.isdigit():
            value = int(value)
        if isinstance(value, bool) or not isinstance(value, int):
            return None
        member = int.__new__(cls, value)
        member._name_ = f"UNKNOWN({value!r})"
        member._value_ = value
        return member

    @property
    def is_known(self) -> bool:
        """``True`` for a declared member, ``False`` for a pseudo-member of an unknown value."""
        return self._name_ in type(self).__members__


class ApiErrorType(LenientStrEnum):
    """The ``type`` field of an API error body."""

    VALIDATION_ERROR = "VALIDATION_ERROR"
    RESOURCE_EXHAUSTED = "RESOURCE_EXHAUSTED"
    USER_BLOCKED = "USER_BLOCKED"
    BAD_REQUEST = "BAD_REQUEST"
    NOT_FOUND = "NOT_FOUND"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    CONFLICT = "CONFLICT"
    INTERNAL_SERVER_ERROR = "INTERNAL_SERVER_ERROR"
    SESSION_NOT_FOUND_ERROR = "SESSION_NOT_FOUND_ERROR"
    SESSION_EXPIRED_ERROR = "SESSION_EXPIRED_ERROR"
    SESSION_FAILED_ERROR = "SESSION_FAILED_ERROR"
    USER_NOT_FOUND = "USER_NOT_FOUND"
    CANDLE_LIMIT_EXCEEDED = "CANDLE_LIMIT_EXCEEDED"
    """The requested period holds more than 1440 candles."""


class Side(LenientStrEnum):
    """Order or trade direction, as used by the operations and trade services."""

    BUY = "1"
    SELL = "2"


class OrderType(LenientStrEnum):
    """Order type accepted when placing orders and reported in execution reports."""

    MARKET = "1"
    LIMIT = "2"
    ALGO_GTD = "3"
    """Algorithmic good-till-date order."""
    ICEBERG = "4"
    CONDITIONAL = "5"
    """Stop-loss and take-profit orders."""


class OrderStatus(LenientStrEnum):
    """Order state in execution reports (operations service and order events stream)."""

    NEW = "0"
    PARTIALLY_FILLED = "1"
    FILLED = "2"
    CANCELLED = "4"
    REPLACED = "5"
    PENDING_CANCEL = "6"
    """Cancellation in progress."""
    REJECTED = "8"
    PENDING_REPLACE = "9"
    """Replacement in progress, e.g. after an edit."""
    PENDING_NEW = "10"
    """Awaiting confirmation of the new order."""

    @property
    def is_final(self) -> bool:
        """``True`` once the order can no longer change."""
        return self in (OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED)


class ExecutionType(LenientStrEnum):
    """Kind of execution report."""

    NEW = "0"
    PARTIAL_FILL = "1"
    FILL = "2"
    CANCELLED = "4"
    REPLACED = "5"
    PENDING_CANCEL = "6"
    """Awaiting cancellation."""
    REJECTED = "8"
    SUSPENDED = "9"
    PENDING_NEW = "10"
    """Awaiting confirmation of the new order."""
    TRADE = "11"
    """A trade was executed."""
    ORDER_STATUS = "12"
    """Order status report."""
    CORRECTED = "13"
    """Correction."""


class TimeInForce(LenientStrEnum):
    """How long an order stays active."""

    DAY = "1"
    """Valid for the trading session; the default. Market and limit orders."""
    FILL_OR_KILL = "2"
    """Execute in full or cancel. Market and limit orders."""
    GOOD_TILL_DATE = "3"
    """Valid until the order's expiry date. Algorithmic orders only."""


class OrderIdType(LenientStrEnum):
    """How an ``order_id`` argument identifies an order."""

    CLIENT = "1"
    """The ``client_order_id`` UUID generated when the order was placed; the default."""
    EXCHANGE = "2"
    """The exchange identifier in the form ``YYMMDD-CLASSCODE-NUMBER``, where ``NUMBER``
    is the exchange order number."""


class OffsetType(LenientIntEnum):
    """Units of a conditional order's offset or protective spread."""

    PRICE_CURRENCY = 0
    """The price currency."""
    PERCENT = 1
    """Percent."""


class StopExecutionType(LenientIntEnum):
    """How the stop-loss or take-profit leg of a conditional order executes."""

    MARKET = 1
    """As a market order."""
    LIMIT = 2
    """As a limit order."""


class OrderListStatus(LenientIntEnum):
    """Order status as reported by the order search (order-details service)."""

    CANCELLED = 1
    EXECUTED = 2
    ACTIVE = 3


class OrderListType(LenientIntEnum):
    """Order type as reported by the order search (order-details service)."""

    MARKET = 1
    LIMIT = 2
    ICEBERG = 3
    STOP_LIMIT = 4
    TAKE_PROFIT_LIMIT = 5
    """Take-profit that spawns a limit order."""
    STOP_LOSS = 6
    TAKE_PROFIT_AND_STOP_LOSS = 7
    LIMIT_30_DAYS = 10
    """Limit order valid for 30 days."""
    TAKE_PROFIT = 11


class InstrumentType(LenientStrEnum):
    """Instrument category."""

    CURRENCY = "CURRENCY"
    STOCK = "STOCK"
    """Russian shares."""
    FOREIGN_STOCK = "FOREIGN_STOCK"
    """Foreign shares."""
    BONDS = "BONDS"
    NOTES = "NOTES"
    DEPOSITARY_RECEIPTS = "DEPOSITARY_RECEIPTS"
    EURO_BONDS = "EURO_BONDS"
    """Eurobonds."""
    MUTUAL_FUNDS = "MUTUAL_FUNDS"
    """Funds."""
    ETF = "ETF"
    FUTURES = "FUTURES"
    OPTIONS = "OPTIONS"
    GOODS = "GOODS"
    """Commodities."""
    INDICES = "INDICES"

    @property
    def is_debt(self) -> bool:
        """``True`` for the debt family: bonds, eurobonds and notes."""
        return self in (InstrumentType.BONDS, InstrumentType.EURO_BONDS, InstrumentType.NOTES)

    @property
    def is_derivative(self) -> bool:
        """``True`` for futures and options."""
        return self in (InstrumentType.FUTURES, InstrumentType.OPTIONS)


class InstrumentSubType(LenientStrEnum):
    """Instrument sub-type, the API's second-level classification.

    The API does not list the values; an unlisted value becomes an unknown member.
    """

    COMMON_SHARE = "AST_SEC_BASIC"
    PREFERRED_SHARE = "AST_SEC_PREV"
    DEPOSITARY_RECEIPT = "AST_ADR"
    FUND_UNIT = "AST_SHARE"
    """ETF and mutual fund units."""
    CORPORATE_BOND = "AST_CORP"
    GOVERNMENT_BOND = "AST_OFZ"
    """Federal loan bonds (OFZ)."""
    REGIONAL_BOND = "AST_STATE"
    """Bonds of Russian regions and municipalities."""
    FOREIGN_BOND = "AST_FORBOND"
    CORPORATE_EUROBOND = "AST_EURO_CORP"
    CURRENCY_PAIR = "AST_CURR"
    FUTURE = "AST_FUT"
    CALL_OPTION = "AST_OPT_CALL"
    PUT_OPTION = "AST_OPT_PUT"
    INDEX = "AST_INDX"


class OptionType(LenientStrEnum):
    """Call or put, as the API labels an option."""

    CALL = "call"
    PUT = "put"


class UpperType(LenientStrEnum):
    """Market group of a portfolio position."""

    CURRENCY = "CURRENCY"
    RUSSIA = "RUSSIA"
    FOREIGN = "FOREIGN"
    OTC = "OTC"
    """Over the counter."""


class PositionType(LenientStrEnum):
    """Kind of portfolio position."""

    MONEY_LIMIT = "moneyLimit"
    """Money balance."""
    DEPO_LIMIT = "depoLimit"
    """Securities position."""
    FUTURES_LIMIT = "futuresLimit"
    """Derivatives market money limit."""
    FUTURES_HOLDING = "futuresHolding"
    """Derivatives position."""
    OTC_LIMIT = "otcLimit"
    """Over-the-counter position."""


class Term(LenientStrEnum):
    """Settlement term: the period within which a trade settles.

    ``T0`` is the settled position, ``T1`` and ``T2`` the position once the trades
    settling on those days have cleared, and ``T365`` the planned position with every
    unsettled trade counted.
    """

    T0 = "T0"
    T1 = "T1"
    T2 = "T2"
    T365 = "T365"


class SecurityTradingStatus(LenientIntEnum):
    """Trading status of an instrument as reported in quotes."""

    UNKNOWN = 0
    SUSPENDED = 2
    """Trading suspended."""
    OPEN = 17
    """Trading open."""
    CLOSED = 18
    """Trading closed."""
    CLOSING = 100
    """Trading is closing."""
    OPENING = 101
    """Trading is opening."""
    AUCTION = 102
    CLOSING_AUCTION = 103
    DISCRETE_AUCTION = 104


class TimeFrame(LenientStrEnum):
    """Candle timeframe."""

    M1 = "M1"
    """1 minute."""
    M5 = "M5"
    """5 minutes."""
    M15 = "M15"
    """15 minutes."""
    M30 = "M30"
    """30 minutes."""
    H1 = "H1"
    """1 hour."""
    H4 = "H4"
    """4 hours."""
    D = "D"
    """1 day."""
    W = "W"
    """1 week."""
    MN = "MN"
    """1 month."""


class SessionStatus(LenientStrEnum):
    """Trading session status."""

    OPEN = "OPEN"
    CLOSE = "CLOSE"


class OperationType(LenientStrEnum):
    """Non-trade operation type."""

    PAY_OUT = "PayOut"
    """Cash withdrawal."""
    PAY_IN = "PayIn"
    """Cash deposit."""
    PAY_TRANSFER = "PayTransfer"
    """Cash transfer."""
    DIVIDEND = "Dividend"
    """Dividend payment."""
    DIVIDEND_DEBT = "DividendDebt"
    """Repo dividend payment."""
    BOND_PAYING_OFF = "BondPayingOff"
    """Coupon payment."""
    COMMISSION = "Commission"
    """Commission."""
    INCOME_TAX = "IncomeTax"
    """Personal income tax."""
    SECURITY_OUT = "SecurityOut"
    """Securities debited."""
    SECURITY_IN = "SecurityIn"
    """Securities credited."""
    BOND_PART_REPAYMENT = "BondPartRepayment"
    """Partial bond redemption."""
    BOND_FULL_REPAYMENT = "BondFullRepayment"
    """Full bond redemption."""
    STRUCTURAL_PRODUCT_REPAYMENT = "StructuralProductRepayment"
    INVESTMENT_SHARE_REPAYMENT = "InvestmentShareRepayment"
    PAY_OUT_FX = "PayOutFx"
    """Withdrawal from a Forex/CFD account."""
    PAY_OUT_DFA = "PayOutDfa"
    """Withdrawal from a digital financial assets (DFA) account."""
    PAY_OUT_DU = "PayOutDu"
    """Funding of a trust management agreement from the brokerage account."""
    PAY_IN_FX = "PayInFx"
    """Deposit to a Forex/CFD account."""
    PAY_IN_DFA = "PayInDfa"
    """Deposit to a digital financial assets (DFA) account."""
    VAR_MARGIN = "VarMargin"
    """Variation margin credited or debited."""


class OperationStatus(LenientStrEnum):
    """Processing status of a non-trade operation."""

    APPROVED = "Approved"
    IN_PROGRESS = "InProgress"
    REJECTED = "Rejected"


class BalanceChange(LenientStrEnum):
    """Effect of a non-trade operation on the account balance."""

    NEUTRAL = "Neutral"
    """No change."""
    NEGATIVE = "Negative"
    """Decreases the balance."""
    POSITIVE = "Positive"
    """Increases the balance."""


class DealType(LenientIntEnum):
    """Type of deal an executed trade belongs to.

    The API documents the field without listing values; the members are the codes of the
    QUIK trading system the field originates from.
    """

    ORDINARY = 1
    NEGOTIATED = 2
    PLACEMENT = 3
    """Primary placement."""
    TRANSFER = 4
    """Transfer of money or securities."""
    REPO_FIRST_LEG_NEGOTIATED = 5
    SWAP_SETTLEMENT = 6
    OTC_SWAP_SETTLEMENT = 7
    BASKET_SETTLEMENT = 8
    """Settlement trade of a dual-currency basket."""
    OTC_BASKET_SETTLEMENT = 9
    CCP_REPO = 10
    """Repo with the central counterparty."""
    CCP_REPO_FIRST_LEG = 11
    CCP_REPO_SECOND_LEG = 12
    CCP_REPO_NEGOTIATED = 13
    CCP_REPO_NEGOTIATED_FIRST_LEG = 14
    CCP_REPO_NEGOTIATED_SECOND_LEG = 15
    CCP_REPO_RETURN = 16
    """Technical trade returning repo assets."""
    CALENDAR_SPREAD = 17
    """Spread between futures of different expiries on one asset."""
    CALENDAR_SPREAD_FIRST_LEG = 18
    CALENDAR_SPREAD_SECOND_LEG = 19
    BASKET_REPO_FIRST_LEG = 20
    BASKET_REPO_SECOND_LEG = 21
    FUTURES_POSITION_TRANSFER = 22


class RiskLevel(LenientIntEnum):
    """Client risk category on the derivatives market.

    The API documents the field as a level from 0 to 4; the members are the categories
    of the QUIK trading system the field originates from.
    """

    UNSPECIFIED = 0
    INITIAL = 1
    """Initial risk level."""
    STANDARD = 2
    """Standard risk level."""
    ELEVATED = 3
    """Elevated risk level."""
    SPECIAL = 4
    """Special risk level."""


class TradeSide(LenientStrEnum):
    """Direction of an anonymous trade on the market-data stream."""

    BUY = "BUY"
    SELL = "SELL"
