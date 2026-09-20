"""Instrument reference data and trading schedule service."""

from __future__ import annotations

from itertools import batched
from typing import TYPE_CHECKING, Literal, overload

from bacsy.api._base import MAX_PAGE_SIZE, BaseService, check_page, iter_until_short
from bacsy.exceptions import ProtocolError
from bacsy.models.common import InstrumentKey
from bacsy.models.enums import InstrumentType
from bacsy.models.instruments import (
    BaseInstrument,
    Bond,
    Commodity,
    CurrencyPair,
    DailySchedule,
    Equity,
    Future,
    Index,
    Instrument,
    IsinsRequest,
    Option,
    TickersRequest,
    TradingStatus,
)
from bacsy.routes import Operation, Service

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterable, Sequence

    from bacsy.models.common import InstrumentLike

GET_BY_TICKERS = Operation(
    name="getInstrumentsByTickers",
    service=Service.INFORMATION,
    method="POST",
    path="/api/v1/instruments/by-tickers",
)
GET_BY_ISINS = Operation(
    name="getInstrumentsByIsins",
    service=Service.INFORMATION,
    method="POST",
    path="/api/v1/instruments/by-isins",
)
GET_BY_TYPE = Operation(
    name="getInstrumentsByTypeAndBaseAssetTicker",
    service=Service.INFORMATION,
    method="GET",
    path="/api/v1/instruments/by-type",
)
GET_DAILY_SCHEDULE = Operation(
    name="getDailySchedule",
    service=Service.INFORMATION,
    method="GET",
    path="/api/v1/trading-schedule/daily-schedule",
)
GET_TRADING_STATUS = Operation(
    name="getTradingStatus",
    service=Service.INFORMATION,
    method="GET",
    path="/api/v1/trading-schedule/status",
)

type EquityType = Literal[
    InstrumentType.STOCK,
    InstrumentType.FOREIGN_STOCK,
    InstrumentType.DEPOSITARY_RECEIPTS,
    InstrumentType.ETF,
    InstrumentType.MUTUAL_FUNDS,
]
type BondType = Literal[InstrumentType.BONDS, InstrumentType.EURO_BONDS, InstrumentType.NOTES]

_MODEL_BY_TYPE: dict[InstrumentType, type[BaseInstrument]] = {
    InstrumentType.STOCK: Equity,
    InstrumentType.FOREIGN_STOCK: Equity,
    InstrumentType.DEPOSITARY_RECEIPTS: Equity,
    InstrumentType.ETF: Equity,
    InstrumentType.MUTUAL_FUNDS: Equity,
    InstrumentType.BONDS: Bond,
    InstrumentType.EURO_BONDS: Bond,
    InstrumentType.NOTES: Bond,
    InstrumentType.FUTURES: Future,
    InstrumentType.OPTIONS: Option,
    InstrumentType.CURRENCY: CurrencyPair,
    InstrumentType.INDICES: Index,
    InstrumentType.GOODS: Commodity,
}


class InstrumentsService(BaseService):
    """``client.instruments``: reference data lookups and trading schedules.

    Lookups return `Instrument` records, one per ticker and primary board, as the concrete
    class for their type: `Equity`, `Bond`, `Future`, `Option`, `CurrencyPair`, `Index`,
    `Commodity` or `UnknownInstrument`. They are paginated without a total count: a page
    shorter than ``size`` is the last one. `iter_by_type` walks the pages and `lookup`
    resolves a set of keys.
    """

    async def get_by_tickers(
        self, tickers: Sequence[str], *, page: int = 0, size: int = MAX_PAGE_SIZE
    ) -> list[Instrument]:
        """One page of instruments matching the given tickers."""
        check_page(page, size)
        return await self._call(
            GET_BY_TICKERS,
            list[Instrument],
            params={"page": page, "size": size},
            body=TickersRequest(tickers=list(tickers)),
        )

    async def get_by_isins(
        self, isins: Sequence[str], *, page: int = 0, size: int = MAX_PAGE_SIZE
    ) -> list[Instrument]:
        """One page of instruments matching the given ISINs."""
        check_page(page, size)
        return await self._call(
            GET_BY_ISINS,
            list[Instrument],
            params={"page": page, "size": size},
            body=IsinsRequest(isins=list(isins)),
        )

    @overload
    async def get_by_type(
        self,
        type: EquityType,
        *,
        base_asset_ticker: str | None = None,
        page: int = 0,
        size: int = MAX_PAGE_SIZE,
    ) -> list[Equity]: ...
    @overload
    async def get_by_type(
        self,
        type: BondType,
        *,
        base_asset_ticker: str | None = None,
        page: int = 0,
        size: int = MAX_PAGE_SIZE,
    ) -> list[Bond]: ...
    @overload
    async def get_by_type(
        self,
        type: Literal[InstrumentType.FUTURES],
        *,
        base_asset_ticker: str | None = None,
        page: int = 0,
        size: int = MAX_PAGE_SIZE,
    ) -> list[Future]: ...
    @overload
    async def get_by_type(
        self,
        type: Literal[InstrumentType.OPTIONS],
        *,
        base_asset_ticker: str | None = None,
        page: int = 0,
        size: int = MAX_PAGE_SIZE,
    ) -> list[Option]: ...
    @overload
    async def get_by_type(
        self,
        type: Literal[InstrumentType.CURRENCY],
        *,
        base_asset_ticker: str | None = None,
        page: int = 0,
        size: int = MAX_PAGE_SIZE,
    ) -> list[CurrencyPair]: ...
    @overload
    async def get_by_type(
        self,
        type: Literal[InstrumentType.INDICES],
        *,
        base_asset_ticker: str | None = None,
        page: int = 0,
        size: int = MAX_PAGE_SIZE,
    ) -> list[Index]: ...
    @overload
    async def get_by_type(
        self,
        type: Literal[InstrumentType.GOODS],
        *,
        base_asset_ticker: str | None = None,
        page: int = 0,
        size: int = MAX_PAGE_SIZE,
    ) -> list[Commodity]: ...
    @overload
    async def get_by_type(
        self,
        type: InstrumentType,
        *,
        base_asset_ticker: str | None = None,
        page: int = 0,
        size: int = MAX_PAGE_SIZE,
    ) -> list[Instrument]: ...

    async def get_by_type(
        self,
        type: InstrumentType,  # noqa: A002 - mirrors the API parameter
        *,
        base_asset_ticker: str | None = None,
        page: int = 0,
        size: int = MAX_PAGE_SIZE,
    ) -> Sequence[BaseInstrument]:
        """One page of instruments of one type; ``base_asset_ticker`` is required for options.

        The records are typed by ``type``, so ``get_by_type(InstrumentType.FUTURES)`` is a
        ``list[Future]``; a record of another type in the reply raises `ProtocolError`. An
        unknown ``type`` returns `Instrument` records.
        """
        check_page(page, size)
        params: dict[str, str | int] = {"type": type.value, "page": page, "size": size}
        if base_asset_ticker is not None:
            params["baseAssetTicker"] = base_asset_ticker
        payload = await self._transport.call(GET_BY_TYPE, params=params)
        records = self._validate(GET_BY_TYPE, list[Instrument], payload)
        model = _MODEL_BY_TYPE.get(type)
        if model is not None:
            for record in records:
                if not isinstance(record, model):
                    msg = (
                        f"{GET_BY_TYPE.name} returned a {record.instrument_type} record"
                        f" for type {type.value}"
                    )
                    raise ProtocolError(msg, source=GET_BY_TYPE.name, payload=payload)
        return records

    @overload
    def iter_by_type(
        self, type: EquityType, *, base_asset_ticker: str | None = None, size: int = MAX_PAGE_SIZE
    ) -> AsyncIterator[Equity]: ...
    @overload
    def iter_by_type(
        self, type: BondType, *, base_asset_ticker: str | None = None, size: int = MAX_PAGE_SIZE
    ) -> AsyncIterator[Bond]: ...
    @overload
    def iter_by_type(
        self,
        type: Literal[InstrumentType.FUTURES],
        *,
        base_asset_ticker: str | None = None,
        size: int = MAX_PAGE_SIZE,
    ) -> AsyncIterator[Future]: ...
    @overload
    def iter_by_type(
        self,
        type: Literal[InstrumentType.OPTIONS],
        *,
        base_asset_ticker: str | None = None,
        size: int = MAX_PAGE_SIZE,
    ) -> AsyncIterator[Option]: ...
    @overload
    def iter_by_type(
        self,
        type: Literal[InstrumentType.CURRENCY],
        *,
        base_asset_ticker: str | None = None,
        size: int = MAX_PAGE_SIZE,
    ) -> AsyncIterator[CurrencyPair]: ...
    @overload
    def iter_by_type(
        self,
        type: Literal[InstrumentType.INDICES],
        *,
        base_asset_ticker: str | None = None,
        size: int = MAX_PAGE_SIZE,
    ) -> AsyncIterator[Index]: ...
    @overload
    def iter_by_type(
        self,
        type: Literal[InstrumentType.GOODS],
        *,
        base_asset_ticker: str | None = None,
        size: int = MAX_PAGE_SIZE,
    ) -> AsyncIterator[Commodity]: ...
    @overload
    def iter_by_type(
        self,
        type: InstrumentType,
        *,
        base_asset_ticker: str | None = None,
        size: int = MAX_PAGE_SIZE,
    ) -> AsyncIterator[Instrument]: ...

    def iter_by_type(
        self,
        type: InstrumentType,  # noqa: A002 - mirrors the API parameter
        *,
        base_asset_ticker: str | None = None,
        size: int = MAX_PAGE_SIZE,
    ) -> AsyncIterator[BaseInstrument]:
        """Every instrument of one type, across all pages, typed as `get_by_type` types them."""

        async def fetch(page: int) -> Sequence[BaseInstrument]:
            return await self.get_by_type(
                type, base_asset_ticker=base_asset_ticker, page=page, size=size
            )

        return iter_until_short(fetch, size=size)

    async def lookup(
        self, instruments: Iterable[InstrumentLike]
    ) -> dict[InstrumentKey, Instrument]:
        """Resolve instrument keys to their reference data.

        A record describes the instrument on its primary board, so a key matched through a
        secondary board reads the primary board's currency, lot and accrued interest.
        """
        keys = InstrumentKey.coerce_all(instruments)
        wanted = set(keys)
        found: dict[InstrumentKey, Instrument] = {}
        by_ticker: dict[str, list[Instrument]] = {}
        for chunk in batched(sorted({key.ticker for key in keys}), MAX_PAGE_SIZE):
            page = 0
            while True:
                records = await self.get_by_tickers(chunk, page=page, size=MAX_PAGE_SIZE)
                for record in records:
                    if record.ticker is not None:
                        by_ticker.setdefault(record.ticker, []).append(record)
                    for key in record.keys:
                        if key in wanted:
                            found.setdefault(key, record)
                if len(records) < MAX_PAGE_SIZE:
                    break
                page += 1
        for key in wanted - found.keys():
            candidates = by_ticker.get(key.ticker, [])
            if len(candidates) == 1:
                found[key] = candidates[0]
        return found

    async def get_daily_schedule(self, *, ticker: str, class_code: str) -> DailySchedule:
        """Today's session schedule of one instrument."""
        return await self._call(
            GET_DAILY_SCHEDULE, DailySchedule, params={"ticker": ticker, "classCode": class_code}
        )

    async def get_trading_status(self, *, class_code: str) -> TradingStatus:
        """Current session of a class code and when it changes next."""
        return await self._call(GET_TRADING_STATUS, TradingStatus, params={"classCode": class_code})
