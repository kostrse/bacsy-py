# Installation

bacsy needs Python 3.12 or later and runs wherever `asyncio` does: Linux, macOS and
Windows.

## Install the package

=== "uv"

    ```bash
    uv add bacsy
    ```

=== "pip"

    ```bash
    pip install bacsy
    ```

The package pulls in three runtime dependencies, `httpx2`, `pydantic` and `websockets`,
and nothing else. It ships typed, so an editor or `basedpyright` sees every signature.

## What you need

A BCS brokerage account, and an API token (refresh token) for it, issued in the BCS web
terminal: open your profile, the account's settings, then the "API tokens" section. The
[official instructions](https://trade-api.bcs.ru/) describe the steps and the service
rules.

A token is issued with one of two scopes. A read token serves every query in these guides; a
write token is needed only to place, edit or cancel orders, and it reads as well. Issue a
read token unless the program you are writing trades, and keep one of each if it does:
bacsy uses the read token for everything it can. A token is valid for 90 days from the
day it is issued.

!!! note

    bacsy reads the scope and the expiry from the token itself, so nothing about them is
    repeated in code or configuration.

## The command line

The package installs the `bacsy` command, which saves tokens under an account name and
keeps them in order. In a project it runs as `uv run bacsy`; without installing anything,
`uvx bacsy` runs it on its own.

```bash
uvx bacsy --help
```

Continue with the [Quickstart](quickstart.md) to save your first token and make your
first request.
