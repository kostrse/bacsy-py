# Command line

The `bacsy` command manages the accounts and refresh tokens that
`TradeApiClient.from_account` uses. It is installed with the library, so `uv run bacsy`
works in a project and `uvx bacsy` anywhere. This page lists every command; the workflows
are in [Accounts and tokens](../guides/accounts-and-tokens.md).

```text
bacsy [--json] [--color WHEN] COMMAND ...
```

A bare `bacsy` runs `accounts list`. A group name without a subcommand, such as
`bacsy tokens`, prints that group's help and exits with code 2.

## Global options

| Option | Effect |
| --- | --- |
| `--json` | write one JSON document to stdout instead of text; hints and warnings are left out |
| `--color WHEN` | `auto` (colour on a terminal, the default), `always` or `never` |
| `--version` | print `bacsy X.Y.Z` |
| `-h`, `--help` | help for the command or group |

`--json` and `--color` are accepted before and after the command. Colour also respects
`NO_COLOR`, `FORCE_COLOR` and `TERM=dumb`.

## Accounts

An account is a name that holds the refresh tokens of one brokerage account.

| Command | Does |
| --- | --- |
| `bacsy accounts list` | show every account and its tokens, offline |
| `bacsy accounts add NAME [--label LABEL]` | create an empty account |
| `bacsy accounts remove NAME [-y]` | remove an account and all its tokens, after a confirmation unless `-y`/`--yes` is given |
| `bacsy accounts rename OLD NEW` | rename an account |

An account name is letters, digits and `_ - . /`, starting with a letter, digit or `_`,
up to 64 characters in any script; `main` and `3412345/25-иис` are both valid. Names are
case-sensitive. The rule is applied when an account is created or renamed, never when
the store is read, so an account saved under an earlier rule stays usable.

Removing an account or a token does not revoke the token; delete it in the BCS web
terminal too.

## Tokens

| Command | Does |
| --- | --- |
| `bacsy tokens add ACCOUNT [--stdin]` | save a token issued in the BCS web terminal under an existing account |
| `bacsy tokens remove ACCOUNT ID` | remove one token, named by the `ID` column of `accounts list` |
| `bacsy tokens prune [--dry-run]` | drop expired and revoked tokens from every account |
| `bacsy tokens verify [ACCOUNT]` | check every token, or one account's, against the token endpoint; needs network access |

`tokens add` reads the token from a hidden prompt, or from standard input with `--stdin`,
and takes the first token it finds in the text, so a value pasted with quotes, a `Bearer`
prefix or JSON around it still works. It refuses an access token, an expired token and a
token of a different brokerage account than the one the account already holds. The
account must exist first.

`tokens verify` reports tokens that are expired offline without contacting the endpoint,
and records an `expired` or `revoked` verdict so that later listings show it without a
network call.

## Token table

Every command that shows tokens uses the same table, ordered by scope (read before
write), then by expiry (nearest first).

| Column | Meaning |
| --- | --- |
| `TOKEN` | the redacted form the web terminal shows, such as `eyJh**********lCGA`; it identifies nothing |
| `ID` | the token's identifier, as the web terminal lists it; the argument of `tokens remove` |
| `SCOPE` | `read` or `write` |
| `VALID UNTIL` | the expiry, in local time |
| `DAYS` | days until expiry |
| `STATUS` | the stored status, see below |
| `LIVE` | the endpoint's verdict; `tokens verify` only |

| Status | Meaning |
| --- | --- |
| `ok` | usable |
| `expiring` | usable, expires within 7 days |
| `expired` | past its expiry |
| `revoked` | rejected by the token endpoint; deleted in the web terminal |
| `scope-mismatch` | rejected by the token endpoint for the scope it claims |
| `invalid` | rejected by the token endpoint as malformed |
| `error` | `tokens verify` could not reach a verdict; the message says why |

## Output

Results go to stdout. Everything advisory goes to stderr, prefixed `error:`,
`warning:`, `hint:` or `note:`, so a script that captures stdout sees only the result.
Only `accounts list` and `tokens verify` suggest a next action, and at most one at a time:
an account with no usable token, then tokens expiring within 7 days, then dead tokens to
prune, then an account with no tokens yet. A command that changes something reports what
it did and stops.

The command line never prints a token value, an agreement id or where the state
directory is.

## JSON

With `--json`, stdout is one document and stderr is empty.

| Command | Document |
| --- | --- |
| `accounts list` | `{"accounts": [account, ...]}` |
| `accounts add`, `accounts remove` | `{"account": account}` |
| `accounts rename` | `{"previous_name": "...", "account": account}` |
| `tokens add` | `{"account": "...", "token": token, "added": true}`; `added` is `false` when the token was already saved |
| `tokens remove` | `{"account": "...", "token": token}` |
| `tokens prune` | `{"dry_run": false, "removed": [{"account": "...", "token": token}, ...]}` |
| `tokens verify` | `{"checked_at": "...", "summary": {"ok": 1, ...}, "tokens": [{"account": "...", "token": token, "live": "ok", "error": null}, ...]}` |

An `account` object is `{"name", "label", "agreement_id", "tokens": [token, ...]}`. A
`token` object is `{"token_id", "scope", "short", "sid", "issued_at", "expires_at",
"added_at", "days_left", "status"}`; timestamps are ISO 8601. The token value never
appears.

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | success |
| `1` | failure: a bad token, a missing account, a declined confirmation, a file or network error |
| `2` | usage error |
| `3` | `tokens verify` found an expired, revoked or invalid token |
| `130` | interrupted with Ctrl-C |

`bacsy tokens verify` before starting a program is the intended use of code 3: a shell
`&&` then stops the program from running on dead tokens.
