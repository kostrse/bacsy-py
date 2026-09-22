# Models

Response models and enums are importable from `bacsy.models`; request bodies live in the
module of their service, for example `bacsy.models.orders`. Fields are declared in
`snake_case` and read the API's `camelCase`, money and quantities are `Decimal`, and a
response tolerates unknown fields and enum values. [Models](../concepts/models.md) explains
these conventions.

## Base models and field types

::: bacsy.models.base

::: bacsy._json.JsonValue

## Common models

::: bacsy.models.common

## Enums

::: bacsy.models.enums

## Error bodies

::: bacsy.models.errors

## Portfolio

::: bacsy.models.portfolio

## Limits

::: bacsy.models.limits

## Margin

::: bacsy.models.margin

## Instruments

::: bacsy.models.instruments

## Market data

::: bacsy.models.market_data

## Orders

::: bacsy.models.orders

## Trades

::: bacsy.models.trades

## Non-trade operations

::: bacsy.models.operations

## Stream events

::: bacsy.models.ws
