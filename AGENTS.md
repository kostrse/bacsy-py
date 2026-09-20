# Agent instructions

`bacsy` is an unofficial, independent async Python client for the BCS Trade API, published
to PyPI as `bacsy`. It wraps the REST API and the WebSocket streams and ships a `bacsy`
console script that manages the saved accounts and refresh tokens the client uses.

This repository holds the client library only. Do not add trading strategies, bots that
place orders, credentials, captured account data, or copies of the upstream documentation.
Every current REST endpoint and stream is implemented; deprecated endpoints are omitted on
purpose. The project is pre-1.0, so the public interface may still change, but every change
to it is deliberate and lands in `bacsy.__all__` and the documentation in the same commit.

## Toolchain

uv manages the environment and the lock file. Never call `pip` or `python` directly; use
`uv run`. The supported Python versions are the classifiers in `pyproject.toml`; the lowest
one is what `basedpyright` targets, so use no syntax or standard library feature newer than
it.

```bash
uv sync                      # install from uv.lock
uv run ruff format .         # format
uv run ruff check --fix .    # lint
uv run basedpyright          # type check, strict
uv run pytest                # test
```

A change is done when all four checks pass locally. Report their real output.

```bash
uv run ruff format --check .
uv run ruff check .
uv run basedpyright
uv run pytest
```

Never disable a rule, add a blanket `# type: ignore`, relax `typeCheckingMode` or filter a
warning to make a check pass: fix the code, or explain why a targeted, commented suppression
is right. Runtime dependencies are `httpx`, `pydantic` and `websockets`; add nothing else
unless asked. When the dependencies in `pyproject.toml` change, run `uv lock` and commit
`uv.lock` in the same change.

## Layout

Every module's docstring states its role and its contract; read it before editing. A
leading underscore marks a private module.

```
src/bacsy/
  __init__.py      public interface; __all__ lists every export
  client.py        TradeApiClient: composition root, from_* factories, services, streams
  http.py          ApiHttpClient: bearer auth, per-service pacing, retries, 401 resend
  credentials.py   the seam between accounts/ and client.py: one credential resolver per
                   factory, the only reader of BACSY_ACCOUNT and BACSY_REFRESH_TOKEN
  config.py        ClientConfig and its policies, endpoint constants
  routes.py        Service and Operation; a leaf that imports nothing from bacsy
  exceptions.py    BacsyError hierarchy, error_for_status
  auth/            tokens, the token endpoint, AccessTokenProvider and AccessTokenCache;
                   knows nothing of accounts, files or the environment
  accounts/        AccountManager and AccountStore over the accounts file; built on auth/
  api/             one service class per API microservice, on a shared typed call helper
  models/          Pydantic models: base types, enums, one module per service, ws.py
  ws/              reconnecting connection, typed streams, stream factory, connection budget
  ratelimit/       token bucket, per-service limiter, retry classification and backoff
  cli/             the bacsy console script; argparse only; never imported by the library
  _json.py, _util/, _version.py   private leaves
tests/             mirrors the package; scripted doubles in tests/auth/fakes.py,
                   tests/accounts/fakes.py and tests/ws/fakes.py
.github/           CI and release workflows, Dependabot and release scripts
.agents/skills/    agent skills; .claude/skills is a symlink to it for Claude Code
CHANGELOG.md       Keep a Changelog; user-visible changes are recorded under [Unreleased]
```

## Architecture

- **Async only.** The public interface is `asyncio`. No blocking I/O in library code, no
  threads, no synchronous mirror.
- **Strict typing.** `basedpyright` runs strict over `src` and `tests`. Avoid `Any`.
- **Layers.** `httpx.AsyncClient` -> `ApiHttpClient` -> `TradeApiClient`. The typed client's
  constructor takes only an assembled `ApiHttpClient`; convenience lives in the `from_*`
  factories. Each layer closes only what it created, which is what makes an injected pool
  or `ApiHttpClient` testable. `TradeApiClient` takes no credential arguments and reads no
  environment.
- **Dependency direction.** `routes.py` and `_util/` import nothing from `bacsy`. `auth/`
  imports neither `accounts/` nor `credentials.py`; `accounts/` is built on `auth/`;
  `credentials.py` sits above both. The HTTP client and the streams depend only on the
  `AccessTokenProvider` protocol. Nothing in the library imports `cli/`.
- **Pluggable seams.** The token provider, token cache, rate limiter, HTTP pool and
  WebSocket connector are injected through structural protocols. Keep them pluggable and
  do not add a second way to supply one.

## Errors

Raise from `bacsy.exceptions`. Every error derives from `BacsyError` and belongs to exactly
one of four categories, named for what the caller does next: `TransportError` (could not
reach or talk to the server, including 5xx and unreadable replies), `ConfigurationError`
(nothing was sent, the setup is wrong), `AuthError` (the server does not accept the
credentials) and `ApiError` (the server rejected the operation). No class has two catchable
parents. An error from an HTTP response carries it as `response`; `transient` says whether
retrying may help. Map new statuses and API error types in `error_for_status` rather than
letting `httpx` exceptions escape. A local pre-check raises the class the server's own
answer would map to. A bad argument to a library call (a page size, a depth, an account
name) raises `ValueError`, like the standard library; anything derived from a token, a
file, the environment or the network raises a `BacsyError`.

## Routes, rate limits and retries

Every REST call is described by an `Operation` declared in the service that owns it. The
API enforces per-service request limits and answers HTTP 429; the limiter, the retry
classifier and the stream connection budget all key on `Service`. Declare
`idempotent=False` for anything that changes state: the classifier in
`bacsy.ratelimit.retry` never retries a non-idempotent operation after a transport failure
or a server error. Declare the token `scope` the operation needs; only order mutations are
`"write"`, and the refreshing provider presents the least-privileged live token that
serves the scope asked for.

## Models

Subclass `BaseApiModel`; declare fields in `snake_case` and let the alias generator produce
the API's `camelCase`. Use `Decimal` for money, prices and quantities, never `float`; JSON
is decoded through `bacsy._json` so the digits survive. Response models tolerate unknown
fields by design and request models reject them; do not switch either. Response-side enums
derive from `LenientStrEnum` or `LenientIntEnum`, so an undocumented value becomes an
unknown member instead of a validation error. Positions and instruments are unions chosen
by the API's kind tag with an `Unknown*` fallback; a kind adds fields to the shared base
and never overrides a parent field. Flat wire fields are regrouped by `models/_wire.py`
before validation. The position, limit and trade objects are QUIK terminal tables with
camelCased names; keep QUIK's meaning of a field when renaming or documenting it.

## Streams

A reader task always awaits the socket so server pings are answered; never block the read
loop on user code. Subscriptions are recorded before they are sent so they replay after a
reconnect, and a `Reconnected` marker tells the consumer that data may have been missed.
Unknown message types and unknown enum values never raise inside a stream. The stream
factory counts connections per service against the API's caps before opening a socket.

## Credentials and state

- The credential variables are `BACSY_ACCOUNT`, `BACSY_REFRESH_TOKEN` (one or more
  tokens, whitespace or comma separated) and `BACSY_STATE_DIR`. Each of the first two
  stands in for exactly one factory's first argument; neither falls back to the other and
  neither switches a factory to another mechanism, so there is no precedence between them.
  There is deliberately no variable for an access token and no default account name.
- Everything the library keeps on disk lives in the one state directory from
  `_util/paths.py`, which `BACSY_STATE_DIR` relocates as a whole. Its contents are a black
  box: filenames and their number may change between versions, and no environment variable
  or command-line option may name an individual file. Explicit paths passed to a store or
  cache in code stay supported.
- State files are written atomically with `0600` permissions. A writer holds the
  `FileLock` beside the file across its read-modify-write, in and across processes;
  readers never lock.
- The accounts file is machine-managed, never hand-edited. A stored token record carries
  the claims decoded from its token, so the read path never decodes a JWT. Anything
  computed from the token string rather than read from a claim, the `short` label and the
  derived `token_id`, is computed once in `RefreshToken.parse`, stored and read back; never
  recompute it from `value`, which will one day need decrypting.
- A token is referred to only by its `token_id`. `repr()` of anything holding a token
  redacts it; print a token only as `RefreshToken.short`, a display label that identifies
  nothing. Nothing verifies a JWT signature, since only the broker holds the key. JWT
  mechanics live in `auth/_jwt.py` and the meaning of the claims in `auth/tokens.py`.
- `validate_account_name` is the one definition of the account name rule. The manager
  applies it when an account is created or renamed, never when the store is read, so an
  account saved under an earlier rule stays listable, renamable and removable.
- A `RefreshingAccessTokenProvider` is given refresh tokens and never learns about
  accounts, files or the environment. `AccountManager` owns the policy and delegates
  persistence to the store it is given, so another backend can be substituted.
- Epoch timestamps are `int` seconds; clocks, skews and durations are `float`.

## Command line

The `bacsy` script is a thin control surface over `AccountManager`. Each subcommand is a
`Command` that produces a `Report`, rendered as text or, with `--json`, as one JSON
document. Only `accounts list` and `tokens verify`, whose job is to report the state of
the store, suggest a next action; a command that changes something reports what it did
and stops. The two exceptions are `accounts add`, whose account is useless until it holds
a token, and the first token ever saved. Suggestions are computed in `cli/_advice.py` and
passed to the report as a field, so they render as text and stay out of JSON. Every token
table is ordered by `cli/_views.token_key`, so a row reads the same in every command. The
command line never prints where the accounts are stored, and the JSON token object exposes
`status` rather than the stored dead mark. `tokens add` persists the exact extracted value
without rewriting JWT segments. A bare `bacsy` runs `accounts list`. When trying the
script locally, point `BACSY_STATE_DIR` at a scratch directory so the run never touches
the real state.

## Terminology

The web terminal calls the credential it issues an API token; the API documentation calls
it a refresh token. Code, docstrings, log lines and error messages use the exact terms
only: refresh token and access token, never "API token". Entry points a newcomer reads
first (`README.md`, the `tokens add` help line, the empty-list hint) say "API token" and
bridge exactly once, on first use, as "API token (refresh token)"; after the bridge they
say "refresh token" where access tokens are also in play and plain "token" where they are
not. Tokens come from "the BCS web terminal", where they are issued and deleted; bacsy
saves, removes, prunes and verifies them.

## Code and docstrings

- Prefer clear names and straightforward code to comments. Comment only non-obvious logic,
  invariants and constraints; do not narrate the code.
- Document the public API following PEP 257, with Google-style sections only when they add
  something; a short docstring is often enough. Public docstrings are the API reference.
  Private helpers need one only when their contract is non-obvious.
- Describe current, verified behaviour. No work history, plans or defensive justification.
- Loggers are `bacsy` and its children. Never log a token value or an account identifier.

## Testing

- `asyncio_mode = "auto"`, so `async def test_*` needs no decorator. Warnings are errors;
  fix the cause rather than adding a filter.
- Tests never touch the network. Use `httpx.MockTransport` through the `make_client`
  fixture in `tests/conftest.py` or the recording transport in `tests/api/conftest.py`, and
  the WebSocket doubles in `tests/ws/fakes.py`. Build clients with `make_client` or a
  `from_*` factory given an injected `http=` pool.
- The autouse `isolated_environment` fixture clears the credential variables and points
  `BACSY_STATE_DIR` at `tmp_path`; keep it so tests never read real credentials.
- Build tokens with `tests/auth/fakes.py` and never embed real claims. Command-line tests
  inject every side effect through `CliDeps`: clock, prompts, streams and an empty
  environment, so nothing depends on the developer's terminal.
- Time-dependent code takes injectable `clock` and `sleep` callables; use the `fake_clock`
  fixture, never real sleeps.

## Security

The library authenticates against brokerage accounts, and a refresh token can mint
trading-capable access tokens. Never write a token, an account identifier (agreement id,
client code, login) or a captured response containing one into the repository, a test
fixture, a log line or a commit message. Never run the client or the console script against
a real account from an agent session; the fakes under `tests/` are the only credentials to
use.

## Documentation

Keep `README.md` and this file in step with the code: when a command, path, variable or
public interface changes, update every place that documents it. Do not reference private
repositories, working notes or non-public documentation from any file in this repository.

Every user-visible change (public interface, command line, behaviour, dependencies,
supported Python versions) adds an entry under `## [Unreleased]` in `CHANGELOG.md` in the
same commit, under Added, Changed, Deprecated, Removed, Fixed or Security. Entries use
inline links, since a release's notes are that section's body alone.

## Releases

The version is the static `version` in `pyproject.toml`; `uv.lock` records it and
`bacsy.__version__` reads it from the installed metadata. Releases are plain `0.X.Y`
versions until 1.0, with no beta or dev suffix, so `main` carries the last released
version between releases; the first release turns `0.1.0.dev0` into `0.1.0`. A PEP 440
pre-release such as `0.2.0b1` is allowed for a preview; its tag is `v0.2.0b1` and the
workflow marks the GitHub Release as a pre-release.

A release is one commit, `Release X.Y.Z`, that sets the version and moves the
`[Unreleased]` changelog section under `## [X.Y.Z] - YYYY-MM-DD`, plus the annotated tag
`vX.Y.Z` on that commit. Pushing the tag runs `.github/workflows/release.yml`: it fails if
the tag and the project version differ, runs the four checks, builds, publishes to PyPI
through Trusted Publishing (no PyPI token exists anywhere) and only then creates the
GitHub Release, with the notes that `.github/scripts/release_notes.py` extracts from the
changelog and the built files attached. A manual dispatch of the same workflow publishes
the current branch to TestPyPI as a dry run and creates no release.

`.agents/skills/release/SKILL.md` is the procedure an agent follows to prepare a release.
An agent prepares and commits locally; it never pushes, tags or dispatches a workflow
without the maintainer's explicit approval in the same conversation.

## Adding things

- A REST endpoint: an `Operation` in the service module with `idempotent` and `scope` set,
  models in `models/`, a service method, and a test over the recording transport in
  `tests/api/`.
- An HTTP status or API error type: a mapping in `error_for_status`.
- A stream event: a model in `models/ws.py` and its parser entry; an unrecognised type must
  still become `UnknownEvent`.
- A public name: `bacsy.__all__`, which `tests/test_package.py` checks.
