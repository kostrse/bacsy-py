"""Instrument reference data and trading schedules.

The API describes every instrument with one flat record. The classes here split it by
`InstrumentType`: `Equity` and `Bond` are securities, `Future` and `Option` derivatives,
with `CurrencyPair`, `Index`, `Commodity` and, for a type this library does not know,
`UnknownInstrument`. `Instrument` is the union the lookups return. A record describes the
instrument as listed on its primary board: `BaseInstrument.trading` and a bond's accrued
interest are that board's.
"""

from __future__ import annotations

from datetime import date, time
from decimal import Decimal
from typing import Annotated

from pydantic import BeforeValidator, Discriminator, Field, Tag, model_validator

from bacsy.models._wire import as_wire_dict, get_wire, nest
from bacsy.models.base import (
    BaseApiModel,
    OptionalCalendarDate,
    OptionalDatetime,
    OptionalMoexDate,
    OptionalStr,
    RequestModel,
    empty_to_none,
)
from bacsy.models.common import Board, InstrumentKey
from bacsy.models.enums import InstrumentSubType, InstrumentType, OptionType, SessionStatus

__all__ = [
    "BaseInstrument",
    "Board",
    "Bond",
    "Commodity",
    "CurrencyPair",
    "DailySchedule",
    "Derivative",
    "Eligibility",
    "Equity",
    "Future",
    "Index",
    "Instrument",
    "IsinsRequest",
    "Issuer",
    "Listing",
    "Option",
    "PriceChange",
    "Security",
    "SecurityAnalytics",
    "TickersRequest",
    "TradingParameters",
    "TradingSession",
    "TradingStatus",
    "UnknownInstrument",
]

PERPETUAL_EXPIRY = date(2100, 1, 1)
"""The expiry date the API reports for a perpetual futures contract."""


class Listing(BaseApiModel):
    """Where an instrument trades and how it settles there."""

    primary_board: OptionalStr = None
    """Class code of the primary board; the one the record's parameters describe."""
    secondary_boards: list[str] = Field(default_factory=list)
    """Class codes of other boards the instrument trades on."""
    boards: list[Board] = Field(default_factory=list)
    """Boards with their venues."""
    settle_code: OptionalStr = None
    """Default settlement code, e.g. ``T+1``."""
    settlement_date: OptionalCalendarDate = None
    """Settlement date for the default settlement code."""


class TradingParameters(BaseApiModel):
    """Lot, tick and currencies of an instrument on its primary board."""

    lot_size: Decimal | None = None
    """Units per lot."""
    minimum_step: Decimal | None = None
    """Minimum price step."""
    step_price: Decimal | None = None
    """Value of one price step."""
    step_price_currency: OptionalStr = None
    """Currency of `step_price`; ``PNTS`` when the step is in index points."""
    scale: int | None = None
    """Price precision, decimal places."""
    trading_currency: OptionalStr = None
    """Trading currency."""
    settlement_currency: OptionalStr = None
    """Settlement currency."""


class Eligibility(BaseApiModel):
    """Who may trade an instrument and how."""

    is_blocked: bool | None = None
    """Whether the class is blocked."""
    margin_allowed: bool | None = None
    """Whether margin long positions are allowed."""
    short_allowed: bool | None = None
    """Whether short positions are allowed."""
    qualified_only: bool | None = None
    """Whether the instrument is for qualified investors only."""
    available_for_unqualified: bool | None = None
    """Whether unqualified investors may trade it."""
    qualified_test_id: int | None = None
    """Test marking under the Basic Standard in force today."""
    qualified_test_id_tomorrow: int | None = None
    """Test marking under the Basic Standard in force tomorrow."""
    complex_product: Decimal | None = None
    """Complex-product test marking."""


class PriceChange(BaseApiModel):
    """Price change over standard periods, percent."""

    month: Decimal | None = None
    """Over a month."""
    half_year: Decimal | None = None
    """Over half a year."""
    year: Decimal | None = None
    """Over a year."""
    year_to_date: Decimal | None = None
    """Since the start of the year."""


class Issuer(BaseApiModel):
    """The issuer of a security."""

    name: OptionalStr = None
    """Issuer name."""
    country: OptionalStr = None
    """Country of business."""
    country_code: OptionalStr = None
    """Country code of business."""
    sector: OptionalStr = None
    """Business sector."""
    sector_id: int | None = None
    """Identifier of the business sector."""


class SecurityAnalytics(BaseApiModel):
    """Fundamentals and the broker's rating of a security."""

    market_cap: Decimal | None = None
    """Market capitalisation."""
    pe_norm: Decimal | None = None
    """Normalised P/E, last financial year."""
    price_tangible: Decimal | None = None
    """Tangible book value per share."""
    eps_growth_rate: Decimal | None = None
    """EPS growth rate, 5 years."""
    dividend_yield: Decimal | None = None
    """Dividend yield: declared annual dividend divided by the closing price."""
    predicted_dps: Decimal | None = None
    """Forecast dividend per share."""
    target_price: Decimal | None = None
    """Target price."""
    percent_target_current: Decimal | None = None
    """Upside to the target price from the previous session close, percent."""
    bcs_score: int | None = None
    """BCS rating."""
    bcs_score_color: OptionalStr = None
    """Colour of the BCS rating."""


_LISTING = {
    "primaryBoard": "primary_board",
    "secondaryBoards": "secondary_boards",
    "boards": "boards",
    "settleCode": "settle_code",
    "settlementDate": "settlement_date",
}
_TRADING = {
    "lotSize": "lot_size",
    "minimumStep": "minimum_step",
    "stepPrice": "step_price",
    "currencyStepPrice": "step_price_currency",
    "scale": "scale",
    "tradingCurrency": "trading_currency",
    "settlementCurrency": "settlement_currency",
}
_ELIGIBILITY = {
    "isBlocked": "is_blocked",
    "isCanMargin": "margin_allowed",
    "isCanShort": "short_allowed",
    "isQualifiedOnly": "qualified_only",
    "availableForUnqualified": "available_for_unqualified",
    "qualifiedTestId": "qualified_test_id",
    "qualifiedTestIdTm": "qualified_test_id_tomorrow",
    "complexProduct": "complex_product",
}
_PRICE_CHANGE = {
    "priceChangeMonth": "month",
    "priceChangeHalfYear": "half_year",
    "priceChangeYear": "year",
    "priceChangeEarlyYear": "year_to_date",
}
_ISSUER = {
    "issuerName": "name",
    "businessCountry": "country",
    "businessCountryCode": "country_code",
    "businessSector": "sector",
    "businessSectorId": "sector_id",
}
_ANALYTICS = {
    "mktcap": "market_cap",
    "peNorm": "pe_norm",
    "priceTangible": "price_tangible",
    "epsGrowthRate": "eps_growth_rate",
    "dividendYield": "dividend_yield",
    "predictedDps": "predicted_dps",
    "targetPrice": "target_price",
    "percentTargetCurrent": "percent_target_current",
    "bcsScore": "bcs_score",
    "bcsScoreColor": "bcs_score_color",
}


def _nest_security_groups(data: object) -> object:
    payload = as_wire_dict(data)
    if payload is None:
        return data
    nest(payload, "issuer", _ISSUER)
    nest(payload, "analytics", _ANALYTICS)
    return payload


def _nest_underlying(data: object) -> object:
    payload = as_wire_dict(data)
    if payload is None:
        return data
    ticker = payload.pop("baseAssetSecuritySecCode", None)
    class_code = payload.pop("baseAssetSecurityClassCode", None)
    if "underlying" not in payload and ticker and class_code:
        payload["underlying"] = {"ticker": ticker, "class_code": class_code}
    return payload


class BaseInstrument(BaseApiModel):
    """Fields every instrument record carries."""

    ticker: OptionalStr = None
    """Instrument ticker."""
    instrument_type: InstrumentType | None = None
    """Instrument category; the tag the concrete class was chosen by."""
    sub_type: Annotated[InstrumentSubType | None, BeforeValidator(empty_to_none)] = None
    """Sub-type: common or preferred share, government or corporate bond, call or put."""
    type_name: OptionalStr = Field(default=None, alias="type")
    """Human-readable kind in Russian, e.g. ``Акции обыкновенные``."""
    display_name: OptionalStr = None
    """Display name."""
    short_name: OptionalStr = None
    """Short name."""
    sub_title: OptionalStr = None
    """Subtitle."""
    listing: Listing = Field(default_factory=Listing)
    """Boards and settlement."""
    trading: TradingParameters = Field(default_factory=TradingParameters)
    """Lot, tick and currencies on the primary board."""
    eligibility: Eligibility = Field(default_factory=Eligibility)
    """Who may trade it and how."""
    price_change: PriceChange = Field(default_factory=PriceChange)
    """Price change over standard periods."""
    is_bcs_product: bool | None = None
    """Whether it is a BCS product."""

    @property
    def primary_key(self) -> InstrumentKey | None:
        """Ticker and primary board, or ``None`` when either is missing."""
        return InstrumentKey.maybe(self.ticker, self.listing.primary_board)

    @property
    def key(self) -> InstrumentKey | None:
        """The key on the primary board; the same as `primary_key`."""
        return self.primary_key

    @property
    def keys(self) -> list[InstrumentKey]:
        """One key per board the instrument trades on, the primary board first."""
        if self.ticker is None:
            return []
        codes = [self.listing.primary_board]
        codes += [board.class_code for board in self.listing.boards]
        codes += self.listing.secondary_boards
        seen: dict[str, None] = dict.fromkeys(code for code in codes if code)
        return [InstrumentKey(ticker=self.ticker, class_code=code) for code in seen]

    @model_validator(mode="before")
    @classmethod
    def _nest_groups(cls, data: object) -> object:
        payload = as_wire_dict(data)
        if payload is None:
            return data
        nest(payload, "listing", _LISTING)
        nest(payload, "trading", _TRADING)
        nest(payload, "eligibility", _ELIGIBILITY)
        nest(payload, "priceChange", _PRICE_CHANGE)
        return payload


class Security(BaseInstrument):
    """An issued security: identified by ISIN, with an issuer and a nominal."""

    isin: OptionalStr = None
    """ISIN."""
    nrd_code: OptionalStr = None
    """Instrument code at the NSD."""
    registration_code: OptionalStr = None
    """State registration code."""
    issuer: Issuer = Field(default_factory=Issuer)
    """The issuer."""
    face_value: Decimal | None = None
    """Nominal per unit: share par or bond face, in `nominal_currency`."""
    nominal_currency: OptionalStr = Field(default=None, alias="currencyNominal")
    """Currency of `face_value`."""
    emission_date: OptionalCalendarDate = None
    """Issue date."""
    analytics: SecurityAnalytics = Field(default_factory=SecurityAnalytics)
    """Fundamentals and the broker's rating; the API fills issuer-level figures for
    bonds too."""

    @model_validator(mode="before")
    @classmethod
    def _nest_security(cls, data: object) -> object:
        return _nest_security_groups(data)


class Equity(Security):
    """A share, depositary receipt or fund unit.

    Which of those it is, read from `instrument_type`; common versus preferred and the
    kind of fund from `sub_type`.
    """


class Bond(Security):
    """A bond, eurobond or note."""

    coupon_rate: Decimal | None = None
    """Coupon rate, percent per year."""
    coupon_type_name: OptionalStr = None
    """Coupon type, in Russian."""
    coupons_per_year: int | None = None
    """Coupons per year."""
    next_coupon: OptionalMoexDate = None
    """Date of the next coupon payment."""
    accrued_interest: Decimal | None = Field(default=None, alias="accruedInt")
    """Accrued coupon income per bond at the settlement date, on the primary board."""
    amortised: bool | None = Field(default=None, alias="amortisedMty")
    """Whether the issue is amortised."""
    maturity_date: OptionalCalendarDate = None
    """Maturity date."""
    credit_rating: OptionalStr = None
    """Credit risk level on the traffic-light scale."""
    liquidity_rating: OptionalStr = None
    """Liquidity rating."""
    is_replacement_bond: bool | None = None
    """Whether it is a replacement bond."""


class Derivative(BaseInstrument):
    """A futures or options contract on an underlying asset."""

    base_asset_name: OptionalStr = Field(default=None, alias="baseAsset")
    """Name of the underlying, e.g. ``USD/RUB``."""
    base_asset_group: OptionalStr = Field(default=None, alias="baseAssetFuture")
    """Group of the underlying in Russian: shares, currency, commodities, indices."""
    underlying: InstrumentKey | None = None
    """Key of the underlying instrument, when the API names one."""
    expiry: OptionalCalendarDate = Field(default=None, alias="maturityDate")
    """Execution date; a perpetual contract carries `PERPETUAL_EXPIRY`."""

    @property
    def is_perpetual(self) -> bool:
        """``True`` for a perpetual contract, which the API dates `PERPETUAL_EXPIRY`."""
        return self.expiry is not None and self.expiry >= PERPETUAL_EXPIRY

    @model_validator(mode="before")
    @classmethod
    def _nest_derivative(cls, data: object) -> object:
        return _nest_underlying(data)


class Future(Derivative):
    """A futures contract."""


class Option(Derivative):
    """An option contract."""

    strike: Decimal | None = None
    """Strike price."""
    option_type: OptionType | None = None
    """Call or put, read from `sub_type` or the API's label."""

    @model_validator(mode="before")
    @classmethod
    def _derive_option_type(cls, data: object) -> object:
        payload = as_wire_dict(data)
        if payload is None or payload.get("optionType") or payload.get("option_type"):
            return data
        option_type = _option_type(get_wire(payload, "subType", "sub_type"))
        if option_type is None:
            option_type = _option_type(get_wire(payload, "type", "type_name"))
        if option_type is not None:
            payload["optionType"] = option_type
        return payload


def _option_type(value: object) -> OptionType | None:
    if not isinstance(value, str):
        return None
    label = value.lower()
    if label in (InstrumentSubType.CALL_OPTION.lower(), OptionType.CALL):
        return OptionType.CALL
    if label in (InstrumentSubType.PUT_OPTION.lower(), OptionType.PUT):
        return OptionType.PUT
    return None


class CurrencyPair(BaseInstrument):
    """A currency pair traded on the currency market."""

    quoted_currency: OptionalStr = Field(default=None, alias="firstCurrCode")
    """Code of the quoted currency, e.g. ``CNY`` for ``CNYRUB_TOM``."""


class Index(BaseInstrument):
    """An index: a reference value, not a tradable instrument."""


class Commodity(BaseInstrument):
    """A commodity fixing: a reference value, not a tradable instrument."""


class UnknownInstrument(BaseInstrument):
    """An instrument of a type this library does not know, with every field the API sends."""

    isin: OptionalStr = None
    """ISIN."""
    nrd_code: OptionalStr = None
    """Instrument code at the NSD."""
    registration_code: OptionalStr = None
    """State registration code."""
    issuer: Issuer = Field(default_factory=Issuer)
    """The issuer."""
    face_value: Decimal | None = None
    """Nominal per unit."""
    nominal_currency: OptionalStr = Field(default=None, alias="currencyNominal")
    """Currency of `face_value`."""
    emission_date: OptionalCalendarDate = None
    """Issue date."""
    analytics: SecurityAnalytics = Field(default_factory=SecurityAnalytics)
    """Fundamentals and the broker's rating."""
    coupon_rate: Decimal | None = None
    """Coupon rate, percent per year."""
    coupon_type_name: OptionalStr = None
    """Coupon type, in Russian."""
    coupons_per_year: int | None = None
    """Coupons per year."""
    next_coupon: OptionalMoexDate = None
    """Date of the next coupon payment."""
    accrued_interest: Decimal | None = Field(default=None, alias="accruedInt")
    """Accrued coupon income at the settlement date."""
    amortised: bool | None = Field(default=None, alias="amortisedMty")
    """Whether the issue is amortised."""
    maturity_date: OptionalCalendarDate = None
    """Maturity or execution date."""
    credit_rating: OptionalStr = None
    """Credit risk level."""
    liquidity_rating: OptionalStr = None
    """Liquidity rating."""
    is_replacement_bond: bool | None = None
    """Whether it is a replacement bond."""
    base_asset_name: OptionalStr = Field(default=None, alias="baseAsset")
    """Name of the underlying."""
    base_asset_group: OptionalStr = Field(default=None, alias="baseAssetFuture")
    """Group of the underlying, in Russian."""
    underlying: InstrumentKey | None = None
    """Key of the underlying instrument."""
    strike: Decimal | None = None
    """Strike price."""
    quoted_currency: OptionalStr = Field(default=None, alias="firstCurrCode")
    """Code of the quoted currency."""

    @model_validator(mode="before")
    @classmethod
    def _nest_everything(cls, data: object) -> object:
        return _nest_underlying(_nest_security_groups(data))


_TAG_BY_TYPE: dict[InstrumentType, str] = {
    InstrumentType.STOCK: "equity",
    InstrumentType.FOREIGN_STOCK: "equity",
    InstrumentType.DEPOSITARY_RECEIPTS: "equity",
    InstrumentType.ETF: "equity",
    InstrumentType.MUTUAL_FUNDS: "equity",
    InstrumentType.BONDS: "bond",
    InstrumentType.EURO_BONDS: "bond",
    InstrumentType.NOTES: "bond",
    InstrumentType.FUTURES: "future",
    InstrumentType.OPTIONS: "option",
    InstrumentType.CURRENCY: "currency_pair",
    InstrumentType.INDICES: "index",
    InstrumentType.GOODS: "commodity",
}


def _instrument_tag(value: object) -> str:
    kind = get_wire(value, "instrumentType", "instrument_type")
    if isinstance(kind, str):
        return _TAG_BY_TYPE.get(InstrumentType(kind), "unknown")
    return "unknown"


Instrument = Annotated[
    Annotated[Equity, Tag("equity")]
    | Annotated[Bond, Tag("bond")]
    | Annotated[Future, Tag("future")]
    | Annotated[Option, Tag("option")]
    | Annotated[CurrencyPair, Tag("currency_pair")]
    | Annotated[Index, Tag("index")]
    | Annotated[Commodity, Tag("commodity")]
    | Annotated[UnknownInstrument, Tag("unknown")],
    Discriminator(_instrument_tag),
]
"""Any instrument record, chosen by its ``instrumentType``."""


class TickersRequest(RequestModel):
    """Body of the instrument lookup by tickers."""

    tickers: list[str]
    """Tickers to look up."""


class IsinsRequest(RequestModel):
    """Body of the instrument lookup by ISINs."""

    isins: list[str]
    """ISINs to look up."""


class TradingSession(BaseApiModel):
    """One period of the daily schedule.

    Periods are not necessarily listed in chronological order.
    """

    start_date: time | None = None
    """Start time, UTC."""
    end_date: time | None = None
    """End time, UTC."""
    trading_session_status: SessionStatus | None = None
    """Whether trading is open during the period."""
    trading_session_type: OptionalStr = None
    """Session name in Russian, e.g. ``Торговый период`` or ``Аукцион закрытия``."""


class DailySchedule(BaseApiModel):
    """Trading sessions of one instrument for a day."""

    is_work_day: bool | None = None
    """Whether the day is a trading day."""
    daily_schedule: list[TradingSession] = Field(default_factory=list)
    """Periods of the day."""


class TradingStatus(BaseApiModel):
    """Current session of a class code and when it changes next."""

    trading_session_status: SessionStatus | None = None
    """Whether trading is open."""
    trading_session_type: OptionalStr = None
    """Name of the current session, in Russian."""
    trading_session_type_id: int | None = None
    """Identifier of the current session."""
    next_session_date: OptionalDatetime = None
    """When the status next changes."""
