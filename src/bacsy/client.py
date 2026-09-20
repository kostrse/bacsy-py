"""The typed client: services and streams composed on top of `ApiHttpClient`."""

from __future__ import annotations

from functools import cached_property
from typing import TYPE_CHECKING, Self

from bacsy.api.instruments import InstrumentsService
from bacsy.api.limits import LimitsService
from bacsy.api.margin import MarginService
from bacsy.api.market_data import MarketDataService
from bacsy.api.operations import NonTradeOperationsService
from bacsy.api.orders import OrdersService
from bacsy.api.portfolio import PortfolioService
from bacsy.api.trades import TradesService
from bacsy.auth.provider import StaticAccessTokenProvider
from bacsy.config import ClientConfig
from bacsy.credentials import account_token_provider, refresh_token_provider
from bacsy.http import ApiHttpClient, new_http_pool
from bacsy.ws.factory import StreamFactory
from bacsy.ws.protocol import default_connector

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable
    from types import TracebackType

    import httpx2

    from bacsy.accounts import AccountManager
    from bacsy.auth.protocols import AccessTokenCache, AccessTokenProvider
    from bacsy.ws.protocol import WebSocketConnector


class TradeApiClient:
    """Typed access to the BCS Trade API: one service per microservice, plus streams.

    The constructor takes an assembled `ApiHttpClient`; services and streams take their
    configuration and token provider from it. The `from_*` factories build that stack:

    - `from_account` uses a stored account, named directly or by `BACSY_ACCOUNT`.
    - `from_refresh_token` takes refresh tokens the application already holds, or reads
      `BACSY_REFRESH_TOKEN`.
    - `from_access_token` takes a fixed access token that is never refreshed.

    The client is an async context manager. Closing it closes its streams and, only when
    a factory created it, the connection pool; an injected `ApiHttpClient` is left open.

    Example:
        >>> async with TradeApiClient.from_account("main") as client:  # doctest: +SKIP
        ...     positions = await client.portfolio.get_positions()
    """

    def __init__(
        self, http: ApiHttpClient, *, ws_connector: WebSocketConnector | None = None
    ) -> None:
        self._http: ApiHttpClient = http
        self._owned_pool: httpx2.AsyncClient | None = None
        self.streams: StreamFactory = StreamFactory(
            config=http.config,
            token_provider=http.token_provider,
            connector=ws_connector
            or default_connector(http.config.stream, user_agent=http.config.user_agent),
        )
        """WebSocket streams, for example `client.streams.quotes([...])`."""

    @classmethod
    def _assemble(
        cls,
        make_provider: Callable[[httpx2.AsyncClient, ClientConfig], AccessTokenProvider],
        *,
        config: ClientConfig | None,
        http: httpx2.AsyncClient | None,
        ws_connector: WebSocketConnector | None,
    ) -> Self:
        config = config or ClientConfig()
        pool = http or new_http_pool(config)
        provider = make_provider(pool, config)
        client = cls(ApiHttpClient(provider, http=pool, config=config), ws_connector=ws_connector)
        if http is None:
            client._owned_pool = pool
        return client

    @classmethod
    def from_account(
        cls,
        name: str | None = None,
        *,
        config: ClientConfig | None = None,
        cache: AccessTokenCache | None = None,
        accounts: AccountManager | None = None,
        http: httpx2.AsyncClient | None = None,
        ws_connector: WebSocketConnector | None = None,
    ) -> Self:
        """Build a client for a saved account.

        `name` selects which stored account to use; when it is not given,
        `BACSY_ACCOUNT` supplies the name, and there is no default. The account is read
        on the first request; construction performs no I/O. Without `cache`, access
        tokens go through `DefaultAccessTokenCache`, which keeps them on disk as well as
        in memory.

        Raises:
            ConfigurationError: No account is named by `name` or `BACSY_ACCOUNT`.
        """
        return cls._assemble(
            lambda pool, cfg: account_token_provider(
                name, http=pool, config=cfg, cache=cache, accounts=accounts
            ),
            config=config,
            http=http,
            ws_connector=ws_connector,
        )

    @classmethod
    def from_refresh_token(
        cls,
        token: str | Iterable[str] | None = None,
        *,
        config: ClientConfig | None = None,
        cache: AccessTokenCache | None = None,
        http: httpx2.AsyncClient | None = None,
        ws_connector: WebSocketConnector | None = None,
    ) -> Self:
        """Build a client that mints access tokens from one or more refresh tokens.

        `token` is one refresh token, several, or `None` to read `BACSY_REFRESH_TOKEN`.
        Scope and expiry are read from each token. Without `cache`, access tokens go
        through `DefaultAccessTokenCache`, which keeps them on disk as well as in memory.
        Pass `cache=MemoryAccessTokenCache()` where nothing may be written to disk.

        Raises:
            ConfigurationError: No token is given by `token` or `BACSY_REFRESH_TOKEN`,
                or a value is not a refresh token.
        """
        return cls._assemble(
            lambda pool, cfg: refresh_token_provider(token, http=pool, config=cfg, cache=cache),
            config=config,
            http=http,
            ws_connector=ws_connector,
        )

    @classmethod
    def from_access_token(
        cls,
        token: str,
        *,
        config: ClientConfig | None = None,
        http: httpx2.AsyncClient | None = None,
        ws_connector: WebSocketConnector | None = None,
    ) -> Self:
        """Build a client that uses a fixed access token and never refreshes it."""
        return cls._assemble(
            lambda pool, cfg: StaticAccessTokenProvider(token),
            config=config,
            http=http,
            ws_connector=ws_connector,
        )

    @property
    def http(self) -> ApiHttpClient:
        """The HTTP client the typed services send through; also serves raw requests."""
        return self._http

    @property
    def config(self) -> ClientConfig:
        """The configuration of the HTTP client."""
        return self._http.config

    @cached_property
    def portfolio(self) -> PortfolioService:
        """Portfolio service."""
        return PortfolioService(self._http)

    @cached_property
    def limits(self) -> LimitsService:
        """Limits service."""
        return LimitsService(self._http)

    @cached_property
    def margin(self) -> MarginService:
        """Margin indicators service."""
        return MarginService(self._http)

    @cached_property
    def instruments(self) -> InstrumentsService:
        """Instruments service."""
        return InstrumentsService(self._http)

    @cached_property
    def market_data(self) -> MarketDataService:
        """Market data service."""
        return MarketDataService(self._http)

    @cached_property
    def orders(self) -> OrdersService:
        """Orders service."""
        return OrdersService(self._http)

    @cached_property
    def trades(self) -> TradesService:
        """Trades service."""
        return TradesService(self._http)

    @cached_property
    def operations(self) -> NonTradeOperationsService:
        """Non-trade operations service."""
        return NonTradeOperationsService(self._http)

    async def aclose(self) -> None:
        """Close open streams and, if a factory created it, the connection pool."""
        await self.streams.aclose()
        if self._owned_pool is not None:
            await self._owned_pool.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.aclose()
