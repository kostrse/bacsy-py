"""Authentication: token types, access token providers and caches.

`AccessTokenProvider` is the contract the HTTP client and the WebSocket streams depend
on. `RefreshingAccessTokenProvider` implements it by minting access tokens from refresh
tokens and keeping them in an `AccessTokenCache`. This package knows nothing of named
accounts, credential files, or the environment.
"""

from __future__ import annotations

from bacsy.auth._jwt import decode_jwt_claims
from bacsy.auth.cache import (
    DefaultAccessTokenCache,
    FileAccessTokenCache,
    MemoryAccessTokenCache,
    default_token_cache_path,
)
from bacsy.auth.keycloak import classify_refresh_error, exchange_refresh_token
from bacsy.auth.protocols import AccessTokenCache, AccessTokenProvider
from bacsy.auth.provider import (
    RefreshingAccessTokenProvider,
    RefreshTokenSource,
    RejectionHook,
    StaticAccessTokenProvider,
)
from bacsy.auth.tokens import (
    AccessToken,
    RefreshToken,
    TokenScope,
    derived_token_id,
    parse_refresh_tokens,
    select_refresh_tokens,
    short_token,
)

__all__ = [
    "AccessToken",
    "AccessTokenCache",
    "AccessTokenProvider",
    "DefaultAccessTokenCache",
    "FileAccessTokenCache",
    "MemoryAccessTokenCache",
    "RefreshToken",
    "RefreshTokenSource",
    "RefreshingAccessTokenProvider",
    "RejectionHook",
    "StaticAccessTokenProvider",
    "TokenScope",
    "classify_refresh_error",
    "decode_jwt_claims",
    "default_token_cache_path",
    "derived_token_id",
    "exchange_refresh_token",
    "parse_refresh_tokens",
    "select_refresh_tokens",
    "short_token",
]
