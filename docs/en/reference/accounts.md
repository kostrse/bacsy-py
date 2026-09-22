# Accounts

`AccountManager` keeps named accounts, each holding the refresh tokens of one brokerage
account, and builds a token provider for a name. It applies the policy and delegates
persistence to the `AccountStore` it is given, so another backend can be substituted;
`AccountManager.from_file()` builds the file-backed one in the state directory. The
`bacsy` command is a thin surface over this class; see
[Accounts and tokens](../guides/accounts-and-tokens.md) for the workflows and
[Command line](command-line.md) for the commands.

## The account manager

::: bacsy.accounts.manager

## Accounts and results

::: bacsy.accounts.models

## Account names

::: bacsy.accounts.validation

## The accounts file

::: bacsy.accounts.store
