# Environment variables

Three variables affect the library. Each of the first two stands in for exactly one
factory's first argument; neither falls back to the other and neither switches a factory
to another mechanism, so there is no precedence between them. There is deliberately no
variable for an access token and no default account name. The workflows that use them are
in [Accounts and tokens](../guides/accounts-and-tokens.md).

| Variable | Read by | Meaning |
| --- | --- | --- |
| `BACSY_ACCOUNT` | `TradeApiClient.from_account()` with no name | the saved account to use |
| `BACSY_REFRESH_TOKEN` | `TradeApiClient.from_refresh_token()` with no token | one or more refresh tokens, separated by whitespace or commas |
| `BACSY_STATE_DIR` | the library and the command line | the directory that replaces the default state directory as a whole |

A missing value where the factory argument was also omitted raises
[ConfigurationError][bacsy.exceptions.ConfigurationError]; an unparseable
`BACSY_REFRESH_TOKEN` raises [InvalidTokenError][bacsy.exceptions.InvalidTokenError],
naming the variable but never its value.

`BACSY_STATE_DIR` is used verbatim, with `~` expanded and nothing appended. Without it
the state directory is `$XDG_STATE_HOME/bacsy` or `~/.local/state/bacsy` on Linux and
macOS and `%LOCALAPPDATA%\bacsy` on Windows. Its contents are a black box: the file
names may change between versions, and no variable names an individual file.
