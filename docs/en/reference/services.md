# Services

Services are reached through an open `TradeApiClient`, one attribute per API microservice;
constructing them yourself is never necessary. Every method returns typed models and uses
the client's token provider, rate limiter and retry policy. The guides show them in use:
[Account data](../guides/account-data.md), [Instruments](../guides/instruments.md),
[Market data](../guides/market-data.md) and [Orders](../guides/orders.md).

## Portfolio

::: bacsy.api.portfolio.PortfolioService

## Limits

::: bacsy.api.limits.LimitsService

## Margin

::: bacsy.api.margin.MarginService

## Instruments

::: bacsy.api.instruments.InstrumentsService

## Market data

::: bacsy.api.market_data.MarketDataService

## Orders

Placing, editing and cancelling change account state and need a write token. The return
value acknowledges the request; the order report carries the resulting state.

::: bacsy.api.orders.OrdersService

## Trades

::: bacsy.api.trades.TradesService

## Non-trade operations

::: bacsy.api.operations.NonTradeOperationsService

## Pagination helpers

::: bacsy.api.iter_pages

::: bacsy.api.iter_until_short
