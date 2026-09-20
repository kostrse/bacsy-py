"""Command base classes: typed options taken from argparse, the run context and the report."""

from __future__ import annotations

import dataclasses
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, Self

from bacsy.cli._errors import CliError
from bacsy.cli._views import AccountView, TokenView, account_key

if TYPE_CHECKING:
    import argparse
    from collections.abc import Iterable
    from datetime import tzinfo

    from bacsy.accounts import Account, AccountManager, TokenRecord
    from bacsy.cli._console import Console, Json
    from bacsy.cli._deps import CliDeps
    from bacsy.cli._errors import ExitCode


class Report(Protocol):
    """Result of a command, renderable as text or as the run's JSON document."""

    def to_json(self) -> Json: ...

    def render(self, console: Console) -> None: ...


@dataclass(frozen=True, slots=True, kw_only=True)
class Context:
    """What a command runs against: the account manager, injected dependencies and console."""

    manager: AccountManager
    deps: CliDeps
    console: Console
    now: float
    """Clock reading taken once per run so that every displayed value agrees."""
    json: bool

    @property
    def tz(self) -> tzinfo | None:
        return self.deps.tz

    def emit(self, report: Report) -> None:
        if self.json:
            self.console.json(report.to_json())
        else:
            report.render(self.console)

    def account_view(self, account: Account) -> AccountView:
        return AccountView.build(account, now=self.now, tz=self.tz)

    def account_views(self, accounts: Iterable[Account]) -> tuple[AccountView, ...]:
        """Return the views of `accounts` in name order."""
        ordered = sorted(accounts, key=lambda account: account_key(account.name))
        return tuple(self.account_view(account) for account in ordered)

    def token_view(self, account: Account, record: TokenRecord) -> TokenView:
        return TokenView.build(account, record, now=self.now, tz=self.tz)


@dataclass(frozen=True, kw_only=True)
class Command(ABC):
    """A subcommand whose dataclass fields are exactly its options.

    Argparse destinations must carry the same names: `from_namespace` reads the fields
    of the class from the parsed namespace and ignores everything else.
    """

    @classmethod
    def from_namespace(cls, args: argparse.Namespace) -> Self:
        values = {f.name: getattr(args, f.name) for f in dataclasses.fields(cls)}
        return cls(**values)

    @abstractmethod
    async def run(self, ctx: Context) -> ExitCode: ...


async def require_account(ctx: Context, name: str, *, hint: str | None = None) -> Account:
    """Return the account called `name`, or raise `CliError` naming the saved accounts."""
    account = await ctx.manager.get(name)
    if account is not None:
        return account
    names = [account.name for account in await ctx.manager.list_accounts()]
    lines = [] if hint is None else [hint]
    if names:
        lines.append("saved accounts: " + ", ".join(names))
    msg = f"no account named {name!r}"
    raise CliError(msg, hint="\n".join(lines) or None)
