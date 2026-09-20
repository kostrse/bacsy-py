"""Argument parser for the ``bacsy`` command line."""

from __future__ import annotations

import argparse
from functools import partial

from bacsy import __version__
from bacsy.cli.accounts import ListAccounts
from bacsy.cli.accounts import register as register_accounts
from bacsy.cli.tokens import register as register_tokens


def add_global_options(parser: argparse.ArgumentParser, *, leaf: bool) -> None:
    """Add `--json` and `--color`, accepted both before and after the command.

    A subcommand parser writes every value it parsed over the outer namespace, so on a
    leaf the defaults are suppressed and an option given before the command survives.
    """
    parser.add_argument(
        "--json",
        action="store_true",
        default=argparse.SUPPRESS if leaf else False,
        help="write one JSON document to stdout instead of text",
    )
    parser.add_argument(
        "--color",
        choices=("auto", "always", "never"),
        metavar="WHEN",
        default=argparse.SUPPRESS if leaf else "auto",
        help="colour the output: auto (on a terminal, the default), always or never",
    )


GETTING_STARTED = """\
Getting started:
  bacsy accounts add main     create an account
  bacsy tokens add main       paste an API token issued in the BCS web terminal
  bacsy accounts list         check what is saved

Run `bacsy COMMAND --help` to see the subcommands of a group."""


def build_parser() -> argparse.ArgumentParser:
    """Build the `bacsy` argument parser."""
    parser = argparse.ArgumentParser(
        prog="bacsy",
        description="Manage the BCS Trade API accounts and refresh tokens used by bacsy.",
        epilog=GETTING_STARTED,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"bacsy {__version__}")
    add_global_options(parser, leaf=False)
    # A bare `bacsy` runs the listing; each group parser sets `command` back to None so
    # that `bacsy accounts` and `bacsy tokens` still print their help.
    parser.set_defaults(command=ListAccounts, default_screen=True, help_parser=parser)
    groups = parser.add_subparsers(dest="group", metavar="COMMAND", title="commands")
    leaf_options = partial(add_global_options, leaf=True)

    register_accounts(
        groups.add_parser(
            "accounts",
            help="list, create, remove and rename accounts",
            description="Named accounts, each holding the refresh tokens of one brokerage account.",
            epilog="An account starts empty: create one, then add a token to it with "
            "`bacsy tokens add`.",
        ),
        leaf_options=leaf_options,
    )
    register_tokens(
        groups.add_parser(
            "tokens",
            help="add, remove, prune and verify refresh tokens",
            description="The refresh tokens saved under an account.",
            epilog="A token is issued in the BCS web terminal and pasted into "
            "`bacsy tokens add <account>`; the account must exist first.",
        ),
        leaf_options=leaf_options,
    )
    return parser
