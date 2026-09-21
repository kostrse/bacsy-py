# bacsy

[![CI](https://github.com/kostrse/bacsy-py/actions/workflows/ci.yml/badge.svg)](https://github.com/kostrse/bacsy-py/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/bacsy.svg)](https://pypi.org/project/bacsy/)
[![Python](https://img.shields.io/pypi/pyversions/bacsy.svg)](https://pypi.org/project/bacsy/)
[![Typed](https://img.shields.io/badge/typing-strict-blue.svg)](https://github.com/kostrse/bacsy-py/blob/main/pyproject.toml)
[![License](https://img.shields.io/pypi/l/bacsy.svg)](https://github.com/kostrse/bacsy-py/blob/main/LICENSE)

**An unofficial async Python client for the BCS Trade API.**

Typed access to portfolio, orders, instruments and market data over REST, live quotes and
order events over WebSocket, and a small command line that keeps your API tokens in order.
Built on `asyncio`, `httpx2`, `pydantic` and `websockets`; nothing else.

<img
  src="https://raw.githubusercontent.com/kostrse/bacsy-py/main/.github/images/banner.webp"
  alt="Retro-futurist trading robots operating a cybernetics market terminal"
  width="100%">

> This project is not affiliated with, endorsed by, or supported by BCS (ООО «Компания БКС»,
> BrokerCreditService Ltd., part of BCS Financial Group, operator of the BCS World of
> Investments brokerage). BCS names and marks belong to their respective owners.

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

- [Documentation](https://kostrse.github.io/bacsy-py/en/) in English
- [Документация](https://kostrse.github.io/bacsy-py/ru/) на русском

For upstream service rules, see the [official BCS Trade API documentation](https://trade-api.bcs.ru/).

## Status and versioning

The project is pre-1.0 and follows [Semantic Versioning](https://semver.org/): a minor release may still change or remove public interfaces, and every such change is recorded in the [changelog](https://github.com/kostrse/bacsy-py/blob/main/CHANGELOG.md). The public interface is what `bacsy.__all__` exports and the `bacsy` command. Only the latest release is supported. The supported Python versions are the classifiers on PyPI.

## Contributing

Contributions are welcome; see the [contributing guide](https://github.com/kostrse/bacsy-py/blob/main/.github/CONTRIBUTING.md). Please open an issue before starting a large change. AI-assisted changes are accepted when the author has read and understood them and says which tool helped, as the guide describes.

## Security

Report a vulnerability privately as described in the [security policy](https://github.com/kostrse/bacsy-py/blob/main/.github/SECURITY.md), not in a public issue. The library sends tokens only to the BCS Trade API and collects nothing else.

## Trading risk

The software can submit real trading orders, and errors or interruptions may cause financial loss.

Users are responsible for evaluating and testing it, monitoring account activity, and complying with applicable brokerage and API terms.

The project does not provide investment advice or guarantee trading outcomes.

## License

[MIT](https://github.com/kostrse/bacsy-py/blob/main/LICENSE) © Sergey Kostrukov
