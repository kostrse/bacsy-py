# bacsy

**An unofficial async Python client for the BCS Trade API.**

Typed access to your portfolio, orders, instruments and market data over REST, live quotes
and order events over WebSocket, and a small command line that keeps your API tokens
(refresh tokens) in order. Built on `asyncio`, `httpx2`, `pydantic` and `websockets`;
nothing else.

Two commands save a token, and a notebook cell reads a quote:

```bash
uvx bacsy accounts add main
uvx bacsy tokens add main
```

```python
from bacsy import TradeApiClient

async with TradeApiClient.from_account("main") as client:
    quotes = await client.market_data.get_quotes([("SBER", "TQBR")])
    for quote in quotes:
        print(quote.ticker, quote.last)
```

The [Quickstart](getting-started/quickstart.md) takes it from there.

## Why bacsy

<div class="grid cards" markdown>

-   :lucide-check-check:{ .lg .middle } **Complete and current**

    ---

    Every current REST endpoint and stream of the API, and none of the deprecated ones.

    [:lucide-arrow-right: Account data](guides/account-data.md)

-   :lucide-braces:{ .lg .middle } **Typed end to end**

    ---

    Pydantic models for every request and response, `Decimal` for every price and
    quantity, and a public interface that passes strict type checking.

    [:lucide-arrow-right: Models](concepts/models.md)

-   :lucide-key-round:{ .lg .middle } **Tokens managed for you**

    ---

    The `bacsy` command saves, verifies and prunes refresh tokens. The client exchanges
    them for access tokens, caches those, and always presents the least-privileged token
    that can do the job.

    [:lucide-arrow-right: Accounts and tokens](guides/accounts-and-tokens.md)

-   :lucide-gauge:{ .lg .middle } **Rate limits and retries built in**

    ---

    Requests are paced per API service to the published limits. Transient failures are
    retried with backoff; an order is never sent twice.

    [:lucide-arrow-right: Rate limiting](concepts/rate-limiting.md)

-   :lucide-radio:{ .lg .middle } **Streams that come back**

    ---

    A dropped WebSocket reconnects, replays its subscriptions and hands you a
    `Reconnected` marker, so your code knows when data may have been missed.

    [:lucide-arrow-right: Streaming](guides/streaming.md)

-   :lucide-shield-check:{ .lg .middle } **Survives API changes**

    ---

    An unknown field, enum value or instrument kind never raises. Your program keeps
    running when the API grows.

    [:lucide-arrow-right: Models](concepts/models.md)

-   :lucide-notebook-pen:{ .lg .middle } **Notebook friendly**

    ---

    Top-level `await` in a cell, one line from a response to a DataFrame, and access
    tokens shared across kernel restarts.

    [:lucide-arrow-right: Notebooks](guides/notebooks.md)

-   :lucide-flask-conical:{ .lg .middle } **Testable**

    ---

    Every seam is a protocol. Inject a mock transport for REST and a fake connector for
    streams, and test your strategy without a network.

    [:lucide-arrow-right: Architecture and testing](concepts/architecture-and-testing.md)

</div>

## Where to go

| If you are writing | Start with |
| --- | --- |
| a one-off script | the [Quickstart](getting-started/quickstart.md), then [Market data](guides/market-data.md) and [Orders](guides/orders.md) |
| a notebook | [Notebooks](guides/notebooks.md), then [Account data](guides/account-data.md) |
| a trading robot or a service | [Client setup](guides/client-setup.md), [Streaming](guides/streaming.md), [Errors and retries](guides/errors-and-retries.md) and [Long-running programs](guides/long-running-programs.md) |

The [Reference](reference/client.md) lists every class, method and command. For the
upstream service rules, see the
[official BCS Trade API documentation](https://trade-api.bcs.ru/).

## Stability

The project is pre-1.0 and follows [Semantic Versioning](https://semver.org/): a minor
release may still change or remove public interfaces, and every such change is recorded
in the [changelog](https://github.com/kostrse/bacsy-py/blob/main/CHANGELOG.md). The public
interface is what `bacsy.__all__` exports and the `bacsy` command. Only the latest release
is supported; the supported Python versions are the classifiers on PyPI.

## Trading risk

The software can submit real trading orders, and errors or interruptions may cause
financial loss. Users are responsible for evaluating and testing it, monitoring account
activity, and complying with applicable brokerage and API terms. The project does not
provide investment advice or guarantee trading outcomes. It is released under the
[MIT License](https://github.com/kostrse/bacsy-py/blob/main/LICENSE).

This project is not affiliated with, endorsed by, or supported by BCS (ООО «Компания БКС»,
BrokerCreditService Ltd., part of BCS Financial Group, operator of the BCS World of
Investments brokerage). BCS names and marks belong to their respective owners.
