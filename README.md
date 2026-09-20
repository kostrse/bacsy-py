# bacsy

[![CI](https://github.com/kostrse/bacsy-py/actions/workflows/ci.yml/badge.svg)](https://github.com/kostrse/bacsy-py/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/bacsy.svg)](https://pypi.org/project/bacsy/)
[![Python](https://img.shields.io/pypi/pyversions/bacsy.svg)](https://pypi.org/project/bacsy/)

Unofficial async Python client for the BCS Trade API, for Python 3.12 and later.

This project is not affiliated with, endorsed by, or supported by BCS. BCS names and marks belong to their respective owners.

## Getting started

```bash
uv add bacsy
```

Issue an API token (refresh token) in the BCS web terminal and configure it using:

```bash
uvx bacsy accounts add main
uvx bacsy tokens add main
```

Then, in a notebook:

```python
from bacsy import TradeApiClient

async with TradeApiClient.from_account("main") as client:
    quotes = await client.market_data.get_quotes([("SBER", "TQBR")])
    for quote in quotes:
        print(quote.ticker, quote.last)
```

## Documentation

For upstream service rules, see the [official BCS Trade API documentation](https://trade-api.bcs.ru/).

## Contributing

Please open an issue before starting a large change.

## Trading risk

The software can submit real trading orders, and errors or interruptions may cause financial loss.

Users are responsible for evaluating and testing it, monitoring account activity, and complying with applicable brokerage and API terms.

The project does not provide investment advice or guarantee trading outcomes.

## License

[MIT](LICENSE) © Sergey Kostrukov
