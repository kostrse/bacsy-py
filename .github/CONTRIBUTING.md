# Contributing to bacsy

Thank you for helping with bacsy, an unofficial async Python client for the BCS Trade
API. This page is for people. It says what the project accepts, how to get a change
merged, and what the rules are for tools that write code.

## Before you start

Open an issue before anything larger than a small fix, and wait for it to be accepted
before you write code. Bug reports and feature requests each have an issue form; the
form asks for an anonymised request or response snippet, since the upstream
documentation may be outdated or incomplete.

## Scope

The repository holds the client library only: the REST services, the WebSocket streams,
the models and the `bacsy` console script that manages saved accounts and refresh
tokens. Every current endpoint and stream is implemented; deprecated endpoints are left
out on purpose.

Not accepted: trading strategies, bots that place orders, credentials, captured account
data, or copies of the upstream documentation.

## Development

uv manages the environment. Install and run the checks with:

```bash
uv sync
uv run ruff format --check .
uv run ruff check .
uv run basedpyright
uv run pytest
```

A change is done when all four checks pass. `uv run ruff format .` and
`uv run ruff check --fix .` apply the automatic fixes. Every module starts with a
docstring that states its role and its contract; read it before editing the module.

## Documentation

The documentation site is built by Zensical, once per language: `zensical.toml` builds
`docs/en/` and `zensical.ru.toml` builds `docs/ru/`, which hold the same pages under the
same names. The API reference is generated from docstrings, so a public docstring is
documentation too.

Preview one language with `uv run --group docs zensical serve`, adding
`-f zensical.ru.toml` for Russian. When you change `docs/`, a configuration or a public
docstring, also run:

```bash
uv run .github/scripts/build_docs.py --no-release
```

It builds the site the way the `Documentation` workflow does and fails on a broken link
or an unresolved reference.

## Conventions

These are the things a review checks.

- The library is `asyncio` only: no blocking I/O, no threads, no synchronous mirror.
- Typing is strict; avoid `Any`.
- Money, prices and quantities are `Decimal`, never `float`.
- Errors come from `bacsy.exceptions` and belong to exactly one of `TransportError`,
  `ConfigurationError`, `AuthError` or `ApiError`. A bad argument raises `ValueError`.
- Every REST call is an `Operation` in the service that owns it, with `idempotent` and
  `scope` set. Anything that changes state is `idempotent=False`.
- Response models tolerate unknown fields and request models reject them. Response-side
  enums are lenient, so an undocumented value never breaks a stream.
- A public name is added to `bacsy.__all__` and documented in the same change.
- Tests never touch the network. They use the mock transports and the doubles under
  `tests/`, and never embed real claims or identifiers.
- Nothing logs, prints or stores a token value; a token is referred to by its id and
  displayed only through its short label.
- Docstrings describe current behaviour. No work history, plans or justification.
- The exact terms are "refresh token" and "access token". User-facing text may say
  "API token (refresh token)" once, on first use, and "refresh token" after that.

Dependencies stay at `httpx2`, `pydantic` and `websockets` unless an issue agrees on
more. Never disable a lint rule, add a blanket `# type: ignore` or filter a warning to
make a check pass; fix the cause, or explain why a targeted suppression is right.

## Pull requests

- One change per pull request, branched from `main`.
- A behaviour change comes with a test.
- A user-visible change adds an entry under `[Unreleased]` in `CHANGELOG.md`.
- Pull requests are squash-merged, so the title becomes the commit subject: write it in
  the imperative and explain why in the body.
- Answer review comments yourself.

## Security and credentials

Never put a refresh token, an access token, an agreement id, a client code, a login or a
captured response containing one of these into code, tests, fixtures, issues, commit
messages or logs. Never run the client or the console script against a real account
while developing; the fakes under `tests/` are the only credentials to use. When you
try the script locally, point `BACSY_STATE_DIR` at a scratch directory.

Report a vulnerability privately as described in [SECURITY.md](SECURITY.md), not in a
public issue.

## Use of AI tools

AI assistance is welcome; the maintainer uses it too. The rules are about who stands
behind a change, not about which tool helped.

- The person who submits a change is its author. You must have read every line,
  understand it and be able to explain it without the tool.
- Disclose assistance in the commits: add the trailer `Assisted-by: <tool>` (for
  example `Assisted-by: Claude Code`) to a commit the tool helped write. Never list an
  AI as `Co-authored-by`; only people are authors.
- A tool may draft the pull request description, commit messages, issue text and review
  replies, but you have read and understood what is posted in your name, and you tick
  the pull request checklist yourself.
- Do not use AI tools on issues labelled `good first issue`; those exist for people to
  learn the codebase.
- A bug or vulnerability found with an AI tool must say so and include a reproduction
  you ran yourself.
- A pull request or issue that shows no sign of a person having read it, such as one an
  agent opened on its own, may be closed without review, and repeat submissions may be
  blocked.

The same rules apply to the maintainer's own commits.

## Licensing

By submitting a contribution you agree that it is licensed under the project's
[MIT License](../LICENSE), the inbound=outbound rule of GitHub's Terms of Service, and
you confirm that you have the right to submit it. AI output you have reviewed and
understood counts as your contribution; material you cannot license does not.

## Maintainer

Sergey Kostrukov maintains bacsy and has the final say on scope and design. There is no
review team and no response-time promise. Releases happen when there is something to
release.
