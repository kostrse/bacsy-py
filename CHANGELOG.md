# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html). Until 1.0, a
minor release may contain breaking changes; they are listed under "Changed" or "Removed".

## [Unreleased]

### Changed

- Replaced `httpx` with [`httpx2`](https://pydantic.dev/docs/httpx2/get-started/migration/).
  Injected HTTP pools must now be `httpx2.AsyncClient` instances; the default pool uses
  the operating system's trust store for TLS verification.

## [0.1.0] - 2026-09-20

### Added

- `TradeApiClient`, an async client for the BCS Trade API with typed services for
  instruments, market data, portfolio, orders, trades, operations, limits and margin.
- WebSocket streams for market data and private events, with automatic reconnection,
  subscription replay and a `Reconnected` marker for the consumer.
- Per-service rate limiting and retry classification that follow the API's request limits.
- Refresh-token management: `TradeApiClient.from_account`, `from_refresh_token` and
  `from_access_token`, and the `bacsy` console script that saves, verifies and prunes
  tokens for named accounts.
- Pydantic models for every request and response, with `Decimal` for money, prices and
  quantities.

[Unreleased]: https://github.com/kostrse/bacsy-py/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/kostrse/bacsy-py/releases/tag/v0.1.0
