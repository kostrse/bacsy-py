"""The `bacsy tokens` group: commands managing the refresh tokens held by accounts."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING, override

from bacsy.accounts import TokenRecord
from bacsy.auth import RefreshToken
from bacsy.cli._advice import advise_stored, advise_verified, render_advice
from bacsy.cli._command import Command, Context, require_account
from bacsy.cli._errors import CliError, ExitCode
from bacsy.cli._format import format_iso, format_local, plural
from bacsy.cli._views import (
    REVOKE_NOTE,
    TOKEN_ALIGN,
    TOKEN_HEADERS,
    Status,
    VerifiedToken,
    account_key,
    render_accounts,
    token_key,
    token_sections,
)
from bacsy.exceptions import InvalidTokenError

if TYPE_CHECKING:
    import argparse
    from collections.abc import Callable, Sequence

    from bacsy.accounts import Account, VerifyResult
    from bacsy.cli._advice import Advice
    from bacsy.cli._console import Console, Json
    from bacsy.cli._views import AccountView, TokenView


@dataclass(frozen=True, slots=True, kw_only=True)
class TokenAddedReport:
    token: TokenView
    added: bool
    first_token: bool
    """Whether the accounts file held no token at all before this one."""

    def to_json(self) -> Json:
        return {"account": self.token.account, "token": self.token.to_json(), "added": self.added}

    def render(self, console: Console) -> None:
        if self.added:
            console.result(
                f"saved {self.token.scope} token {self.token.token_id} "
                f"to account {self.token.account!r}"
            )
        else:
            console.result(
                f"token {self.token.token_id} is already saved in account {self.token.account!r}"
            )
        console.table(TOKEN_HEADERS, [self.token.row()], align=TOKEN_ALIGN)
        if self.first_token:
            console.hint(
                f"account {self.token.account!r} is ready; use it with\n"
                f'TradeApiClient.from_account("{self.token.account}")',
                block=True,
            )


@dataclass(frozen=True, slots=True, kw_only=True)
class TokenRemovedReport:
    token: TokenView

    def to_json(self) -> Json:
        return {"account": self.token.account, "token": self.token.to_json()}

    def render(self, console: Console) -> None:
        console.result(f"removed token {self.token.token_id} from account {self.token.account!r}")
        console.note(REVOKE_NOTE)


@dataclass(frozen=True, slots=True, kw_only=True)
class PruneReport:
    """What a prune removed and what the accounts hold afterwards.

    `render` writes the accounts as they stand after the run. A dry run that found
    tokens to remove writes those instead, since it removed nothing.
    """

    dry_run: bool
    removed: tuple[TokenView, ...]
    accounts: tuple[AccountView, ...]
    """The accounts as they stand after the run. Rendered as text; absent from `to_json`."""

    def to_json(self) -> Json:
        return {
            "dry_run": self.dry_run,
            "removed": [{"account": t.account, "token": t.to_json()} for t in self.removed],
        }

    def render(self, console: Console) -> None:
        count = plural(len(self.removed), "token")
        if self.dry_run and self.removed:
            sections = token_sections((t, t.row()) for t in self.removed)
            console.sections(TOKEN_HEADERS, sections, align=TOKEN_ALIGN)
            console.result(f"would remove {count}")
            return
        render_accounts(console, self.accounts)
        console.result("nothing to prune" if not self.removed else f"removed {count}")


@dataclass(frozen=True, slots=True, kw_only=True)
class VerifyReport:
    checked_at: str
    tokens: tuple[VerifiedToken, ...]
    advice: Advice | None

    def summary(self) -> Counter[str]:
        return Counter(token.live.value for token in self.tokens)

    def to_json(self) -> Json:
        return {
            "checked_at": self.checked_at,
            "summary": dict(self.summary()),
            "tokens": [token.to_json() for token in self.tokens],
        }

    def render(self, console: Console) -> None:
        if not self.tokens:
            console.result("nothing to verify")
            render_advice(console, self.advice)
            return
        sections = token_sections((t.view, t.row()) for t in self.tokens)
        console.sections((*TOKEN_HEADERS, "live"), sections, align=(*TOKEN_ALIGN, "<"))
        detail = ", ".join(f"{n} {live}" for live, n in self.summary().items())
        console.result(f"verified {plural(len(self.tokens), 'token')}: {detail}")
        render_advice(console, self.advice)


_JWT_CANDIDATE = re.compile(
    r"(?<![A-Za-z0-9_=.-])[A-Za-z0-9_=-]+(?:\.[A-Za-z0-9_=-]+){2}"
    r"(?![A-Za-z0-9_=-]|\.[A-Za-z0-9_=-])"
)


def _extract_token(value: str) -> RefreshToken:
    """Return the first parseable refresh token in pasted text."""
    for match in _JWT_CANDIDATE.finditer(value):
        try:
            return RefreshToken.parse(match.group())
        except InvalidTokenError:
            continue
    msg = "no refresh token found in the input"
    raise InvalidTokenError(msg)


@dataclass(frozen=True, kw_only=True)
class AddToken(Command):
    account: str
    stdin: bool = False

    @override
    async def run(self, ctx: Context) -> ExitCode:
        hint = f"create it first: bacsy accounts add {self.account}"
        account = await require_account(ctx, self.account, hint=hint)
        token = self._read_token(ctx, account)
        saved = await ctx.manager.list_accounts()
        for other in saved:
            if other.name != self.account and other.agreement_id == token.agreement_id:
                ctx.console.warning(
                    f"account {other.name!r} already holds tokens for this brokerage account"
                )
        first_token = not any(other.tokens for other in saved)
        already = any(r.token.token_id == token.token_id for r in account.tokens)
        record = await ctx.manager.add_token(self.account, token.value)
        account = await require_account(ctx, self.account)
        view = ctx.token_view(account, record)
        ctx.emit(TokenAddedReport(token=view, added=not already, first_token=first_token))
        return ExitCode.OK

    def _read_token(self, ctx: Context, account: Account) -> RefreshToken:
        """Read and parse the token from stdin or a hidden prompt.

        Raises `CliError` for a value that is not a refresh token, an expired token, or
        a token issued for a different brokerage account than the account's stored ones.
        """
        if self.stdin:
            value = ctx.deps.read_stdin()
        else:
            value = ctx.deps.getpass(
                f"refresh token for account {self.account!r} (input is hidden): "
            )
        try:
            token = _extract_token(value)
        except InvalidTokenError as exc:
            msg = f"not a BCS refresh token: {exc}"
            hint = "issue an API token in the BCS web terminal and paste it whole"
            raise CliError(msg, hint=hint) from exc
        if token.is_expired(ctx.now):
            expired_on = format_local(token.expires_at, ctx.tz)
            msg = f"token {token.token_id} expired on {expired_on}; issue a new one"
            raise CliError(msg)
        if account.agreement_id not in (None, token.agreement_id):
            msg = (
                "this token was issued for a different brokerage account than the tokens "
                f"saved under {self.account!r}"
            )
            raise CliError(msg, hint="save it under another account name")
        return token


@dataclass(frozen=True, kw_only=True)
class RemoveToken(Command):
    account: str
    token_id: str

    @override
    async def run(self, ctx: Context) -> ExitCode:
        account = await require_account(ctx, self.account)
        wanted = self.token_id.strip()
        record = next((r for r in account.tokens if r.token.token_id == wanted), None)
        if record is None:
            msg = f"account {self.account!r} has no token with ID {self.token_id!r}"
            raise CliError(msg, hint="IDs are shown by: bacsy accounts list")
        await ctx.manager.remove_token(self.account, wanted)
        ctx.emit(TokenRemovedReport(token=ctx.token_view(account, record)))
        return ExitCode.OK


@dataclass(frozen=True, kw_only=True)
class PruneTokens(Command):
    dry_run: bool = False

    @override
    async def run(self, ctx: Context) -> ExitCode:
        accounts = await ctx.manager.list_accounts()
        removed: list[tuple[Account, TokenRecord]]
        if self.dry_run:
            removed = [
                (account, record)
                for account in accounts
                for record in account.tokens
                if record.token.is_expired(ctx.now) or not record.live
            ]
        else:
            by_name = {account.name: account for account in accounts}
            gone = await ctx.manager.prune(now=ctx.now)
            removed = [
                (by_name[name], record) for name, records in gone.items() for record in records
            ]
            accounts = await ctx.manager.list_accounts()  # the earlier list is pre-prune
        removed.sort(key=lambda pair: (account_key(pair[0].name), token_key(pair[1].token)))
        views = tuple(ctx.token_view(account, record) for account, record in removed)
        remaining = ctx.account_views(accounts)
        ctx.emit(PruneReport(dry_run=self.dry_run, removed=views, accounts=remaining))
        return ExitCode.OK


async def _verified_tokens(ctx: Context, results: Sequence[VerifyResult]) -> list[VerifiedToken]:
    """Return a `VerifiedToken` for each result, with its record read from the store.

    The store is read after the check so that dead marks written by it are reflected.
    A token no longer in the store gets a record added at `ctx.now`. Results are
    ordered by account name, then by `token_key`.
    """
    accounts = {account.name: account for account in await ctx.manager.list_accounts()}
    records = {r.token.sid: r for account in accounts.values() for r in account.tokens}
    ordered = sorted(results, key=lambda r: (account_key(r.account.name), token_key(r.token)))
    verified: list[VerifiedToken] = []
    for result in ordered:
        account = accounts.get(result.account.name, result.account)
        record = records.get(result.token.sid) or TokenRecord(
            token=result.token, added_at=int(ctx.now)
        )
        verified.append(
            VerifiedToken(
                view=ctx.token_view(account, record),
                live=Status.of_result(result),
                error=None if result.error is None else str(result.error),
            )
        )
    return verified


@dataclass(frozen=True, kw_only=True)
class VerifyTokens(Command):
    account: str | None = None

    @override
    async def run(self, ctx: Context) -> ExitCode:
        if self.account is not None:
            await require_account(ctx, self.account)
        async with ctx.deps.http_client_factory() as http:
            results = await ctx.manager.verify(http, account_name=self.account, now=ctx.now)
        verified = await _verified_tokens(ctx, results)
        for item in verified:
            if item.error is not None:
                ctx.console.warning(
                    f"token {item.view.token_id} (account {item.view.account!r}): {item.error}"
                )
        checked_at = format_iso(ctx.now, ctx.tz)
        advice = advise_verified(verified) if verified else await self._empty_advice(ctx)
        ctx.emit(VerifyReport(checked_at=checked_at, tokens=tuple(verified), advice=advice))
        lives = {item.live for item in verified}
        if Status.ERROR in lives:
            return ExitCode.FAILURE
        if any(live.dead for live in lives):
            return ExitCode.DEAD_TOKENS
        return ExitCode.OK

    async def _empty_advice(self, ctx: Context) -> Advice | None:
        """Advise on the accounts the run would have checked, none of which hold tokens."""
        accounts = await ctx.manager.list_accounts()
        if self.account is not None:
            accounts = [a for a in accounts if a.name == self.account]
        return advise_stored(accounts, now=ctx.now)


def register(
    group: argparse.ArgumentParser, *, leaf_options: Callable[[argparse.ArgumentParser], None]
) -> None:
    """Add the subcommands to the `tokens` group parser."""
    group.set_defaults(command=None, help_parser=group)
    sub = group.add_subparsers(dest="subcommand", metavar="SUBCOMMAND", title="subcommands")

    add = sub.add_parser(
        "add", help="save an API token (refresh token) issued in the BCS web terminal"
    )
    add.add_argument("account", help="the account to add the token to")
    add.add_argument(
        "--stdin",
        action="store_true",
        help="extract the first token from standard input (read until end-of-file)",
    )
    add.set_defaults(command=AddToken)
    leaf_options(add)

    remove = sub.add_parser("remove", help="remove one token from an account")
    remove.add_argument("account")
    remove.add_argument("token_id", metavar="ID", help="as shown by `bacsy accounts list`")
    remove.set_defaults(command=RemoveToken)
    leaf_options(remove)

    prune = sub.add_parser("prune", help="drop expired and revoked tokens")
    prune.add_argument("--dry-run", action="store_true", help="only show what would be removed")
    prune.set_defaults(command=PruneTokens)
    leaf_options(prune)

    verify = sub.add_parser(
        "verify", help="check every token against the token endpoint (needs network access)"
    )
    verify.add_argument("account", nargs="?", help="check only this account")
    verify.set_defaults(command=VerifyTokens)
    leaf_options(verify)
