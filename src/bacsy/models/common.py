"""Models shared by several services: instrument identity and recurring value objects."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Protocol, override, runtime_checkable

from pydantic import Field

from bacsy.models.base import BaseApiModel, OptionalStr, RequestModel

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

_NO_KEY = object()


class InstrumentKey(RequestModel):
    """An instrument identified by ticker and class code, such as ``SBER`` on ``TQBR``.

    A ticker alone does not identify an instrument: the same ticker is listed on several
    class codes, and unrelated instruments share a ticker across exchanges. Keys are
    hashable and compare by their two fields.
    """

    ticker: str
    """Instrument ticker."""
    class_code: str
    """Class code of the security, e.g. ``TQBR``."""

    @override
    def __hash__(self) -> int:
        return hash((self.ticker, self.class_code))

    @property
    def key(self) -> InstrumentKey:
        """The key itself."""
        return self

    @classmethod
    def maybe(cls, ticker: str | None, class_code: str | None) -> InstrumentKey | None:
        """Build a key from optional parts, or return ``None`` when either is missing."""
        if ticker is None or class_code is None:
            return None
        return cls(ticker=ticker, class_code=class_code)

    @classmethod
    def coerce(cls, value: InstrumentLike) -> InstrumentKey:
        """Return the `InstrumentKey` of ``value``.

        Raises:
            TypeError: If ``value`` has no `key`, or its `key` is not an `InstrumentKey`.
            ValueError: If its `key` is ``None`` because the ticker or class code is
                missing, or a tuple does not hold exactly a ticker and a class code.
        """
        if isinstance(value, tuple):
            ticker, class_code = value
            return cls(ticker=ticker, class_code=class_code)
        # Typed as object so the guards also hold for unchecked callers.
        key: object = getattr(value, "key", _NO_KEY)
        if key is _NO_KEY:
            msg = f"{type(value).__name__} does not name an instrument"
            raise TypeError(msg)
        if key is None:
            msg = f"{value!r} has no instrument key"
            raise ValueError(msg)
        if not isinstance(key, InstrumentKey):
            msg = f"{type(value).__name__}.key is {type(key).__name__}, not InstrumentKey"
            raise TypeError(msg)
        return key

    @classmethod
    def coerce_all(cls, values: Iterable[InstrumentLike]) -> Sequence[InstrumentKey]:
        """Apply `coerce` to every element of ``values``."""
        return [cls.coerce(value) for value in values]


@runtime_checkable
class HasInstrumentKey(Protocol):
    """An object that names an instrument: a key, a position, an instrument, a quote."""

    @property
    def key(self) -> InstrumentKey | None:
        """The instrument's key, or ``None`` when the ticker or class code is missing."""
        ...


type InstrumentLike = HasInstrumentKey | tuple[str, str]
"""Anything the client accepts where it takes instruments, through `InstrumentKey.coerce`.

A ``(ticker, class_code)`` tuple such as ``("SBER", "TQBR")`` works alongside keys and the
records that carry one.
"""


class InstrumentRef(BaseApiModel):
    """Base of records that name an instrument by ticker and class code."""

    ticker: OptionalStr = None
    """Instrument ticker."""
    class_code: OptionalStr = None
    """Class code of the security, e.g. ``TQBR``."""

    @property
    def key(self) -> InstrumentKey | None:
        """Ticker and class code, or ``None`` when either is missing."""
        return InstrumentKey.maybe(self.ticker, self.class_code)


class Board(BaseApiModel):
    """A trading board: the class code an instrument trades under and its venue.

    `class_code` is the broker's class code, which equals the MOEX board id on the stock
    and currency markets (``TQBR``, ``TQCB``, ``CETS``) and names the broker's own classes
    elsewhere (``SPBFUT``, ``SPBXM``, ``BQMEO``). The board fixes the settlement currency,
    settlement cycle and lot of the instrument traded on it.
    """

    class_code: OptionalStr = None
    """Class code, e.g. ``TQBR``."""
    exchange: OptionalStr = None
    """Venue label, e.g. ``MOEX``, ``FORTS``, ``SPB``."""


class MultiCurrencyValue(BaseApiModel):
    """An amount in its own currency and converted to RUB, USD and EUR."""

    value: Decimal | None = None
    """Amount in the position's price currency."""
    rub: Decimal | None = None
    """Amount in RUB."""
    usd: Decimal | None = None
    """Amount in USD."""
    eur: Decimal | None = None
    """Amount in EUR."""


class ProfitLoss(BaseApiModel):
    """A change in value, absolute and in percent."""

    amount: Decimal | None = None
    """Change in the price currency."""
    percent: Decimal | None = None
    """Change in percent."""


class Page[T](BaseApiModel):
    """One page of a paginated search."""

    records: list[T] = Field(default_factory=list)
    """Records of this page."""
    total_pages: int = 0
    """Total number of pages."""
    total_records: int = 0
    """Total number of records across all pages."""
