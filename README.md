# bacsy

[![CI](https://github.com/kostrse/bacsy-py/actions/workflows/ci.yml/badge.svg)](https://github.com/kostrse/bacsy-py/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/bacsy.svg)](https://pypi.org/project/bacsy/)
[![Python](https://img.shields.io/pypi/pyversions/bacsy.svg)](https://pypi.org/project/bacsy/)
[![License](https://img.shields.io/pypi/l/bacsy.svg)](LICENSE)

Unofficial async Python client for the BCS Trade API, for Python 3.12 and later.

This project is not affiliated with, endorsed by, or supported by BCS (ООО «Компания БКС», BrokerCreditService Ltd., part of BCS Financial Group, operator of the BCS World of Investments brokerage). BCS names and marks belong to their respective owners.

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

## Status and versioning

The project is pre-1.0 and follows [Semantic Versioning](https://semver.org/): a minor release may still change or remove public interfaces, and every such change is recorded in the [changelog](CHANGELOG.md). The public interface is what `bacsy.__all__` exports and the `bacsy` command. Only the latest release is supported. The supported Python versions are the classifiers on PyPI.

## Contributing

Contributions are welcome; see the [contributing guide](.github/CONTRIBUTING.md). Please open an issue before starting a large change. AI-assisted changes are accepted when the author has read and understood them and says which tool helped, as the guide describes.

## Security

Report a vulnerability privately as described in the [security policy](.github/SECURITY.md), not in a public issue. The library sends tokens only to the BCS Trade API and collects nothing else.

## Trading risk

The software can submit real trading orders, and errors or interruptions may cause financial loss.

Users are responsible for evaluating and testing it, monitoring account activity, and complying with applicable brokerage and API terms.

The project does not provide investment advice or guarantee trading outcomes.

## License

[MIT](LICENSE) © Sergey Kostrukov
