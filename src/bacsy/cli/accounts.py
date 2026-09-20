"""The `bacsy accounts` group: commands managing named accounts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, override

from bacsy.accounts import ACCOUNT_NAME_RULE, validate_account_name
from bacsy.cli._advice import advise_stored, render_advice
from bacsy.cli._command import Command, Context, require_account
from bacsy.cli._errors import CliError, ExitCode
from bacsy.cli._format import Style, plural
from bacsy.cli._views import REVOKE_NOTE, render_accounts
from bacsy.exceptions import AccountError, AccountExistsError

if TYPE_CHECKING:
    import argparse
    from collections.abc import Callable

    from bacsy.cli._advice import Advice
    from bacsy.cli._console import Console, Json
    from bacsy.cli._views import AccountView


HELP_REMINDER = "Run `bacsy --help` to see all commands."
"""Closes the listing shown when `bacsy` runs with no arguments."""

NAME_HELP = f"account name: {ACCOUNT_NAME_RULE}, e.g. main or 3412345/25-иис"


def _checked_name(name: str) -> str:
    """Return the validated, NFC-normalised name, or raise `CliError` with the reason."""
    try:
        return validate_account_name(name)
    except ValueError as exc:
        raise CliError(str(exc)) from exc


@dataclass(frozen=True, slots=True, kw_only=True)
class ListReport:
    accounts: tuple[AccountView, ...]
    advice: Advice | None
    help_reminder: bool
    """Whether to close with `HELP_REMINDER`. Rendered as text; absent from `to_json`."""

    def to_json(self) -> Json:
        return {"accounts": [account.to_json() for account in self.accounts]}

    def render(self, console: Console) -> None:
        render_accounts(console, self.accounts)
        render_advice(console, self.advice)
        if self.help_reminder:
            console.message(HELP_REMINDER, style=Style.DIM, block=True)


@dataclass(frozen=True, slots=True, kw_only=True)
class CreatedReport:
    account: AccountView

    def to_json(self) -> Json:
        return {"account": self.account.to_json()}

    def render(self, console: Console) -> None:
        console.result(f"created account {self.account.name!r}")
        # A new account holds nothing, so the hint is unconditional rather than advice
        # computed from the state of the store.
        console.hint(f"add a token with: bacsy tokens add {self.account.name}", block=True)


@dataclass(frozen=True, slots=True, kw_only=True)
class RemovedAccountReport:
    account: AccountView

    def to_json(self) -> Json:
        return {"account": self.account.to_json()}

    def render(self, console: Console) -> None:
        count = len(self.account.tokens)
        suffix = f" and its {plural(count, 'token')}" if count else ""
        console.result(f"removed account {self.account.name!r}{suffix}")
        if count:
            console.note(REVOKE_NOTE)


@dataclass(frozen=True, slots=True, kw_only=True)
class RenamedReport:
    previous_name: str
    account: AccountView

    def to_json(self) -> Json:
        return {"previous_name": self.previous_name, "account": self.account.to_json()}

    def render(self, console: Console) -> None:
        console.result(f"renamed account {self.previous_name!r} to {self.account.name!r}")


@dataclass(frozen=True, kw_only=True)
class ListAccounts(Command):
    default_screen: bool = False
    """Whether the listing is the screen shown when `bacsy` is run with no arguments."""

    @override
    async def run(self, ctx: Context) -> ExitCode:
        accounts = await ctx.manager.list_accounts()
        report = ListReport(
            accounts=ctx.account_views(accounts),
            advice=advise_stored(accounts, now=ctx.now),
            help_reminder=self.default_screen,
        )
        ctx.emit(report)
        return ExitCode.OK


@dataclass(frozen=True, kw_only=True)
class AddAccount(Command):
    name: str
    label: str | None = None

    @override
    async def run(self, ctx: Context) -> ExitCode:
        name = _checked_name(self.name)
        try:
            account = await ctx.manager.create(name, label=self.label)
        except AccountExistsError as exc:
            hint = f"add a token to it with: bacsy tokens add {name}"
            raise CliError(str(exc), hint=hint) from exc
        ctx.emit(CreatedReport(account=ctx.account_view(account)))
        return ExitCode.OK


@dataclass(frozen=True, kw_only=True)
class RemoveAccount(Command):
    name: str
    yes: bool = False

    @override
    async def run(self, ctx: Context) -> ExitCode:
        account = await require_account(ctx, self.name)
        count = len(account.tokens)
        if not self.yes:
            suffix = f" and its {plural(count, 'token')}" if count else ""
            if not ctx.deps.confirm(f"remove account {self.name!r}{suffix}?"):
                ctx.console.message("aborted")
                return ExitCode.FAILURE
        await ctx.manager.delete(self.name)
        ctx.emit(RemovedAccountReport(account=ctx.account_view(account)))
        return ExitCode.OK


@dataclass(frozen=True, kw_only=True)
class RenameAccount(Command):
    old: str
    new: str

    @override
    async def run(self, ctx: Context) -> ExitCode:
        new = _checked_name(self.new)
        try:
            await ctx.manager.rename(self.old, new)
        except AccountError as exc:
            raise CliError(str(exc)) from exc
        account = await require_account(ctx, new)
        ctx.emit(RenamedReport(previous_name=self.old, account=ctx.account_view(account)))
        return ExitCode.OK


def register(
    group: argparse.ArgumentParser, *, leaf_options: Callable[[argparse.ArgumentParser], None]
) -> None:
    """Add the subcommands to the `accounts` group parser."""
    group.set_defaults(command=None, help_parser=group)
    sub = group.add_subparsers(dest="subcommand", metavar="SUBCOMMAND", title="subcommands")

    list_cmd = sub.add_parser("list", help="show every account and its tokens (offline)")
    list_cmd.set_defaults(command=ListAccounts, default_screen=False)
    leaf_options(list_cmd)

    add = sub.add_parser("add", help="create an empty account to hold tokens")
    add.add_argument("name", help=NAME_HELP)
    add.add_argument("--label", help="free-text description of the account")
    add.set_defaults(command=AddAccount)
    leaf_options(add)

    remove = sub.add_parser("remove", help="remove an account and all its tokens")
    remove.add_argument("name")
    remove.add_argument("-y", "--yes", action="store_true", help="do not ask for confirmation")
    remove.set_defaults(command=RemoveAccount)
    leaf_options(remove)

    rename = sub.add_parser("rename", help="rename an account")
    rename.add_argument("old")
    rename.add_argument("new", help=NAME_HELP)
    rename.set_defaults(command=RenameAccount)
    leaf_options(rename)
