# Client

`TradeApiClient` is the object every program holds: one attribute per API service and a
`streams` factory, built on an `ApiHttpClient` that owns authentication, pacing and
retries. The `from_*` factories assemble the stack; the constructor takes an assembled
`ApiHttpClient` for programs that build the layers themselves. See
[Client setup](../guides/client-setup.md) for choosing a factory and
[Architecture and testing](../concepts/architecture-and-testing.md) for the layers.

## Typed client

::: bacsy.client.TradeApiClient

## Credential resolution

One resolver per factory. Each credential variable stands in for one resolver's first
argument and neither falls back to the other; see
[Environment variables](environment-variables.md).

::: bacsy.credentials

## HTTP client

::: bacsy.http

## Routes

Every REST call is described by an `Operation` on a `Service`. The HTTP client reads the
operation for pacing, retries and the token scope, and `RateLimitConfig.overrides` is keyed
by `Service`.

::: bacsy.routes
