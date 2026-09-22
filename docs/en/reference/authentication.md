# Authentication

The HTTP client and the streams depend only on the `AccessTokenProvider` protocol.
`RefreshingAccessTokenProvider` implements it over one or more refresh tokens and an
`AccessTokenCache`; `StaticAccessTokenProvider` wraps a fixed access token. Nothing here
knows about named accounts, files or the environment; that is the
[Accounts](accounts.md) layer built on top. [Authentication](../concepts/authentication.md)
explains how the pieces fit and [BCS API tokens](../concepts/bcs-api-tokens.md) the tokens
themselves.

## Contracts

::: bacsy.auth.protocols

## Access token providers

::: bacsy.auth.provider

## Access token caches

::: bacsy.auth.cache

## Tokens

Claims are decoded, never verified: the signature is made with a key only the broker
holds.

::: bacsy.auth.tokens

::: bacsy.auth.decode_jwt_claims

## Token endpoint

::: bacsy.auth.keycloak
