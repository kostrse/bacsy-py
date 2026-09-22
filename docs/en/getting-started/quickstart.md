# Quickstart

This page takes you from nothing to your positions, a quote and a live stream in ten
minutes. You need Python 3.12 or later, a BCS brokerage account, and an API token
(refresh token) for it.

## Install

=== "uv"

    ```bash
    uv add bacsy
    ```

=== "pip"

    ```bash
    pip install bacsy
    ```

The package pulls in three runtime dependencies, `httpx2`, `pydantic` and `websockets`,
and nothing else. It ships typed, so an editor or `basedpyright` sees every signature. It
also installs the `bacsy` command, which saves tokens under an account name and keeps
them in order; `uv run bacsy` runs it in a project, and `uvx bacsy` runs it without
installing anything.

## Issue a token

Tokens are issued in the BCS web terminal: open your profile, the account's settings,
then the "API tokens" section. The [official instructions](https://trade-api.bcs.ru/)
describe the steps and the service rules.

A token is issued with one of two scopes. A read token serves every query in these
guides; a write token is needed only to place, edit or cancel orders, and it reads as
well. Issue a read token unless the program you are writing trades, and keep one of each
if it does: bacsy uses the read token for everything it can. A token is valid for 90 days
from the day it is issued.

!!! note

    bacsy reads the scope and the expiry from the token itself, so nothing about them is
    repeated in code or configuration.

## Save the token

Create an account to hold the token, then paste the token at the prompt. The account
name is yours to choose; `main` is used throughout these pages. The prompt hides what you
type, so the token stays out of your shell history.

```bash
uvx bacsy accounts add main
uvx bacsy tokens add main
```

bacsy decodes the token offline, refuses one that has expired, and shows the same
redacted form, ID and expiry the web terminal lists, so the two can be compared side by
side:

```text
saved read token 0f2c9a1b to account 'main'

TOKEN                 ID        SCOPE  VALID UNTIL       DAYS  STATUS
eyJh**********lCGA    0f2c9a1b  read   2026-12-20 14:03    90  ok
```

`uvx bacsy accounts list` shows the same table whenever you want it. The token is stored
in a file only you can read; the [Accounts and tokens](../guides/accounts-and-tokens.md)
guide covers rotation, several accounts and the environment-variable route for servers.

## Read positions and a quote

`TradeApiClient.from_account("main")` builds a client for the saved account. The client
is an async context manager: entering it costs nothing, the account is read on the first
request, and leaving it closes every stream and connection it opened.

=== "Script"

    ```python
    import asyncio

    from bacsy import TradeApiClient


    async def main() -> None:
        async with TradeApiClient.from_account("main") as client:
            positions = await client.portfolio.get_positions()
            for position in positions:
                print(position.display_name, position.quantity)

            quotes = await client.market_data.get_quotes([("SBER", "TQBR")])
            for quote in quotes:
                print(quote.ticker, quote.last, quote.bid, quote.offer)


    if __name__ == "__main__":
        asyncio.run(main())
    ```

=== "Notebook"

    ```python
    from bacsy import TradeApiClient

    client = TradeApiClient.from_account("main")

    positions = await client.portfolio.get_positions()
    for position in positions:
        print(position.display_name, position.quantity)

    quotes = await client.market_data.get_quotes([("SBER", "TQBR")])
    for quote in quotes:
        print(quote.ticker, quote.last, quote.bid, quote.offer)
    ```

    Keep the client for the life of the kernel and close it with `await client.aclose()`
    when you are done.

An instrument is always named by its ticker and its class code together, here
`("SBER", "TQBR")` for Sberbank on the main MOEX equity board; a ticker alone is
ambiguous. Prices and quantities are `Decimal`, and a field the API did not send, such as
the last price outside trading hours, is `None`.

!!! tip

    Everything on this page works with a read token. Placing orders needs a write token;
    see [Orders](../guides/orders.md).

## Watch quotes live

A stream is opened from `client.streams` and read with `async for`. It yields typed
events, and a `Reconnected` marker after the connection dropped and came back, so the
program knows that quotes may have been missed in between.

```python
import asyncio

from bacsy import Reconnected, TradeApiClient
from bacsy.models import QuoteEvent


async def main() -> None:
    async with TradeApiClient.from_account("main") as client:
        async with client.streams.quotes([("SBER", "TQBR"), ("GAZP", "TQBR")]) as stream:
            async for event in stream:
                if isinstance(event, QuoteEvent):
                    print(event.ticker, event.last)
                elif isinstance(event, Reconnected):
                    print(f"reconnected after {event.downtime:.0f}s")


if __name__ == "__main__":
    asyncio.run(main())
```

The loop runs until the stream is closed or the program is interrupted. The
[Streaming](../guides/streaming.md) guide covers the other streams, changing
subscriptions on the fly and the connection limits.

## Without a saved account

A program that already holds a refresh token, from a secret manager or a deployment
variable, skips the accounts file. Put the token in `BACSY_REFRESH_TOKEN` and call
`from_refresh_token()` with no argument, or pass the token to it directly:

```python
from bacsy import TradeApiClient

client = TradeApiClient.from_refresh_token()
```

Each factory has its own variable, `BACSY_ACCOUNT` for `from_account` and
`BACSY_REFRESH_TOKEN` for `from_refresh_token`, and neither falls back to the other; see
[Environment variables](../reference/environment-variables.md).

## Next steps

| You want to | Read |
| --- | --- |
| see everything the client can fetch | [Account data](../guides/account-data.md), [Instruments](../guides/instruments.md), [Market data](../guides/market-data.md) |
| place orders | [Orders](../guides/orders.md), then [Errors and retries](../guides/errors-and-retries.md) |
| work in Jupyter | [Notebooks](../guides/notebooks.md) |
| run a robot around the clock | [Long-running programs](../guides/long-running-programs.md) |
| tune timeouts, retries or rate limits | [Client setup](../guides/client-setup.md) |
