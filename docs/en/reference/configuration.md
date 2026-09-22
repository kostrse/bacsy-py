# Configuration

`ClientConfig` and its four policies are frozen, keyword-only dataclasses passed to a
`TradeApiClient` factory or to `ApiHttpClient`. The defaults follow the API's published
limits; [Client setup](../guides/client-setup.md) lists the knobs most programs touch and
[Rate limiting](../concepts/rate-limiting.md) explains the pacing and retry rules they
feed.

## Client configuration

::: bacsy.config

## Rate limiter

The limiter is injected into `ApiHttpClient` through the `RateLimiter` protocol;
`ServiceRateLimiter` is the default and `NoopRateLimiter` switches pacing off.

::: bacsy.ratelimit.limiter

::: bacsy.ratelimit.bucket

## Retry classification

::: bacsy.ratelimit.retry
