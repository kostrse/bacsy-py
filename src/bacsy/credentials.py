"""Credential resolution for the `TradeApiClient` factories.

`account_token_provider` builds a provider over the tokens of a stored account, and
`refresh_token_provider` builds one over refresh tokens passed to it. Each reads one
credential variable when its first argument is omitted: ``BACSY_ACCOUNT`` for a name,
``BACSY_REFRESH_TOKEN`` for tokens. Each caches access tokens through
`DefaultAccessTokenCache` unless given a cache.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from bacsy.accounts.manager import AccountManager
from bacsy.auth.cache import DefaultAccessTokenCache
from bacsy.auth.provider import RefreshingAccessTokenProvider
from bacsy.auth.tokens import parse_refresh_tokens
from bacsy.config import ClientConfig
from bacsy.exceptions import ConfigurationError

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    import httpx

    from bacsy.auth.protocols import AccessTokenCache

_ACCOUNT_ENV = "BACSY_ACCOUNT"
"""Names the stored account to use when `account_token_provider` is given no name."""

_REFRESH_TOKEN_ENV = "BACSY_REFRESH_TOKEN"
"""Holds one or more refresh tokens, separated by whitespace or commas."""


def account_token_provider(
    name: str | None = None,
    *,
    http: httpx.AsyncClient,
    config: ClientConfig | None = None,
    cache: AccessTokenCache | None = None,
    accounts: AccountManager | None = None,
    env: Mapping[str, str] | None = None,
) -> RefreshingAccessTokenProvider:
    """Return a provider minting access tokens from the live tokens of a stored account.

    The account is the one called ``name``, else the one named by ``BACSY_ACCOUNT``. Its
    stored tokens are read on the provider's first use, and exchanged through ``http``.

    ``accounts`` defaults to `AccountManager.from_file()`, ``config`` to `ClientConfig()`,
    and ``env`` to the process environment. ``env`` supplies the credential variables; the
    cache file location comes from ``BACSY_STATE_DIR`` in the process environment. Without
    ``cache``, access tokens go through `DefaultAccessTokenCache`, which keeps them on
    disk as well as in memory.

    Raises:
        ConfigurationError: no account is named by ``name`` or ``BACSY_ACCOUNT``.
    """
    env = os.environ if env is None else env
    account_name = name or env.get(_ACCOUNT_ENV)
    if not account_name:
        msg = (
            'no account name given; pass one to TradeApiClient.from_account("main"), '
            f"or set {_ACCOUNT_ENV}"
        )
        raise ConfigurationError(msg)
    manager = accounts if accounts is not None else AccountManager.from_file()
    return manager.token_provider(
        account_name,
        http=http,
        cache=cache,
        config=config or ClientConfig(),
    )


def refresh_token_provider(
    token: str | Iterable[str] | None = None,
    *,
    http: httpx.AsyncClient,
    config: ClientConfig | None = None,
    cache: AccessTokenCache | None = None,
    env: Mapping[str, str] | None = None,
) -> RefreshingAccessTokenProvider:
    """Return a provider minting access tokens from one or more refresh tokens.

    ``token`` is one refresh token, several, or `None` to read ``BACSY_REFRESH_TOKEN``.
    Values may be separated by whitespace or commas, the scope and expiry of each are read
    from the token itself, and exchanges go through ``http``.

    ``config`` defaults to `ClientConfig()` and ``env`` to the process environment.
    ``env`` supplies the credential variables; the cache file location comes from
    ``BACSY_STATE_DIR`` in the process environment. Without ``cache``, access tokens go
    through `DefaultAccessTokenCache`, which keeps them on disk as well as in memory.

    Raises:
        ConfigurationError: no token is given by ``token`` or ``BACSY_REFRESH_TOKEN``, or
            a value is not a refresh token. The message names the source and the token's
            redacted short form in place of its value.
    """
    env = os.environ if env is None else env
    if token is None:
        raw, source = env.get(_REFRESH_TOKEN_ENV, ""), _REFRESH_TOKEN_ENV
    elif isinstance(token, str):
        raw, source = token, "refresh token"
    else:
        raw, source = " ".join(token), "refresh token"
    tokens = parse_refresh_tokens(raw, source=source)
    if not tokens:
        msg = (
            "no refresh token given; pass one to "
            f"TradeApiClient.from_refresh_token(token), or set {_REFRESH_TOKEN_ENV}"
        )
        raise ConfigurationError(msg)
    config = config or ClientConfig()
    return RefreshingAccessTokenProvider(
        tokens,
        http=http,
        cache=cache if cache is not None else DefaultAccessTokenCache(),
        token_path=config.token_endpoint_path,
        access_skew_seconds=config.access_token_skew_seconds,
    )
