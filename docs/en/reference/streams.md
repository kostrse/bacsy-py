# Streams

Streams are opened through `client.streams`. Each factory method returns an async context
manager that is also an async iterator, yielding typed events and, after a reconnection,
a `Reconnected` marker. [Streaming](../guides/streaming.md) covers the consumer contract,
[Streams](../concepts/streams.md) the mechanism, and the event models are on the
[Models](models.md#stream-events) page.

## Factory

::: bacsy.ws.factory.StreamFactory
    options:
      members: [market_data, quotes, order_book, candles, last_trades, orders_events, portfolio, limits, margin, budget, aclose]

## Connection budget

::: bacsy.ws.factory.ConnectionBudget

::: bacsy.ws.factory.DEFAULT_CONNECTION_CAPS

## Common lifecycle

::: bacsy.ws.stream.BaseStream
    options:
      members: [start, aclose, connection]

## Market-data subscriptions

::: bacsy.ws.market_data.MarketDataStream
    options:
      members: [subscribe_quotes, unsubscribe_quotes, subscribe_order_book, unsubscribe_order_book, subscribe_candles, unsubscribe_candles, subscribe_last_trades, unsubscribe_last_trades, subscriptions, resubscribe]

::: bacsy.ws.market_data.SubscriptionRegistry

## Account streams

::: bacsy.ws.private.OrdersEventsStream

::: bacsy.ws.private.PortfolioStream

::: bacsy.ws.private.LimitsStream

::: bacsy.ws.private.MarginStream

## Connection diagnostics

::: bacsy.ws.connection.ConnectionState

::: bacsy.ws.connection.WebSocketConnection
    options:
      members: [state, is_open, dropped_frames, url]

## Custom connectors

::: bacsy.ws.protocol.WebSocketLike

::: bacsy.ws.protocol.WebSocketConnector

::: bacsy.ws.protocol.default_connector
