# Security policy

bacsy authenticates against brokerage accounts. A refresh token saved by the `bacsy`
script can mint access tokens that place real orders, so a vulnerability in how the
library handles tokens matters more than most.

## Supported versions

The project is pre-1.0. Only the latest release on PyPI receives fixes; upgrade before
reporting.

## Reporting a vulnerability

Use GitHub's private vulnerability reporting:
<https://github.com/kostrse/bacsy-py/security/advisories/new>. Do not open a public
issue for a security problem.

Include the version, a description of the impact and a reproduction you ran yourself.
If an AI tool found or wrote the report, say so; a report without a reproduction that a
person has verified may be closed without investigation.

What to expect: an acknowledgement within 7 days, a fix or a status update within 30
days, and disclosure through a GitHub Security Advisory after the fixed release is on
PyPI. Credit is given in the advisory unless you ask otherwise.

## Scope

In scope:

- Handling of refresh and access tokens: the accounts file and the token cache, their
  permissions and atomic writes, the `repr` redaction, and anything that could print,
  log or leak a token value or an account identifier.
- Transport: TLS use, how requests are retried (an order mutation is never retried after
  a transport failure), and how the streams replay subscriptions after a reconnect.
- Anything that lets one saved account act as another.

Out of scope:

- The BCS Trade API itself and the BCS web terminal. Report those to BCS.
- Trading losses, market behaviour or the API's own rate limits.
- A token that leaked from your machine, notebook, shell history or repository.

## How the library handles credentials

- Tokens are sent only to the BCS Trade API endpoints declared in the library
  configuration, never anywhere else. The library collects no telemetry.
- Everything the library keeps on disk lives in one state directory, written with
  `0600` permissions; `BACSY_STATE_DIR` relocates it as a whole.
- JWT signatures are not verified, since only the broker holds the key; the library
  reads claims only to decide which token to use and when it expires.
- The console script never prints a token value; it shows a short label that identifies
  nothing.

## Trading risk

The software can submit real orders, and errors or interruptions may cause financial
loss. This project is not affiliated with, endorsed by, or supported by BCS
(ООО «Компания БКС», BrokerCreditService Ltd., part of BCS Financial Group, operator of
the BCS World of Investments brokerage). See the [README](../README.md#trading-risk).
