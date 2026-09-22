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

The [Quickstart](getting-started/quickstart.md) takes it from there, and
[Features](getting-started/features.md) says what the library does for you beyond a
plain HTTP wrapper.

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
