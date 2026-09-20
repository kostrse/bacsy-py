"""Account lifecycle, dead-token marks and verification over an `AccountStore`.

`AccountManager` decides which token may be added to which account, which rejections
are recorded, and which tokens are live; persistence is delegated to the store it is
given. `AccountManager.token_provider` builds a `RefreshingAccessTokenProvider` over
the live tokens of one account.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import replace
from typing import TYPE_CHECKING, Self

from bacsy.accounts.models import Account, TokenRecord, TokenStatus, VerifyResult
from bacsy.accounts.store import AccountStore
from bacsy.accounts.validation import validate_account_name
from bacsy.auth.cache import DefaultAccessTokenCache
from bacsy.auth.keycloak import exchange_refresh_token
from bacsy.auth.provider import RefreshingAccessTokenProvider
from bacsy.auth.tokens import RefreshToken
from bacsy.config import ClientConfig
from bacsy.exceptions import (
    AccountExistsError,
    AccountNotFoundError,
    BacsyError,
    TokenRefreshError,
    TokenRefreshReason,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    import httpx2

    from bacsy.auth.protocols import AccessTokenCache

_PERSISTED_REASONS = frozenset({TokenRefreshReason.EXPIRED, TokenRefreshReason.REVOKED})
"""Rejections that repeat on every exchange and are therefore recorded in the store."""


class AccountManager:
    """Named accounts, the refresh tokens they hold, and which of those are dead.

    The constructor takes an assembled store; `from_file` builds a file-backed one. The
    store is read on every operation, so a change made by another process is seen by
    the next call. A provider built by `token_provider` reads the account once, on its
    first use.

    ``clock`` supplies the current time as Unix seconds.
    """

    def __init__(
        self,
        store: AccountStore,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._store: AccountStore = store
        self._clock: Callable[[], float] = clock
        self._lock = asyncio.Lock()

    @classmethod
    def from_file(
        cls,
        path: Path | str | None = None,
        *,
        clock: Callable[[], float] = time.time,
    ) -> Self:
        """Return a manager over the accounts file at ``path``.

        ``path`` defaults to ``accounts.json`` in the state directory, which
        ``BACSY_STATE_DIR`` relocates.
        """
        return cls(AccountStore(path), clock=clock)

    @property
    def store(self) -> AccountStore:
        """The store holding the accounts."""
        return self._store

    async def get(self, account_name: str) -> Account | None:
        """Return the account called ``account_name``, or ``None`` when it is unknown."""
        return (await self._store.load()).get(account_name)

    async def list_accounts(self) -> list[Account]:
        """Return every account in the store."""
        return list((await self._store.load()).values())

    async def create(self, account_name: str, *, label: str | None = None) -> Account:
        """Create an empty account to add tokens to.

        Raises:
            ValueError: ``account_name`` is not a valid account name.
            AccountExistsError: an account called ``account_name`` already exists.
        """
        account_name = validate_account_name(account_name)
        async with self._lock, self._store.locked():
            accounts = await self._store.load()
            if account_name in accounts:
                msg = f"an account named {account_name!r} already exists"
                raise AccountExistsError(msg, name=account_name)
            account = Account(name=account_name, label=label)
            accounts[account_name] = account
            await self._store.save(accounts)
        return account

    async def update(self, account: Account) -> None:
        """Replace the stored account of the same name with ``account``.

        The whole entry is overwritten, tokens included. Use `create` or `add_token` to
        create an account and `rename` to rename one.

        Raises:
            AccountNotFoundError: no account called ``account.name`` exists.
        """
        async with self._lock, self._store.locked():
            accounts = await self._store.load()
            if account.name not in accounts:
                msg = f"no account named {account.name!r}"
                raise AccountNotFoundError(msg, name=account.name)
            accounts[account.name] = account
            await self._store.save(accounts)

    async def delete(self, account_name: str) -> bool:
        """Remove the account and all its tokens; return whether it existed."""
        async with self._lock, self._store.locked():
            accounts = await self._store.load()
            if accounts.pop(account_name, None) is None:
                return False
            await self._store.save(accounts)
            return True

    async def add_token(
        self, account_name: str, value: str, *, label: str | None = None
    ) -> TokenRecord:
        """Add a refresh token to ``account_name``, creating the account if needed.

        The token is decoded here and its claims are stored with it. Adding a token whose
        id is already present keeps and returns the existing record. ``label`` replaces
        the account's label only when given.

        Raises:
            InvalidTokenError: ``value`` is not a refresh token.
            AccountError: the token belongs to a different brokerage account than the
                tokens already saved under ``account_name``.
            ValueError: the account has to be created and ``account_name`` is not a
                valid account name.
        """
        token = RefreshToken.parse(value)
        record = TokenRecord(token=token, added_at=int(self._clock()))
        async with self._lock, self._store.locked():
            accounts = await self._store.load()
            current = accounts.get(account_name)
            if current is None:
                # The NFC form may name an existing account; look it up again.
                account_name = validate_account_name(account_name)
                current = accounts.get(account_name) or Account(name=account_name)
            if label is not None:
                current = replace(current, label=label)
            existing = next((r for r in current.tokens if r.token.token_id == token.token_id), None)
            if existing is None:
                current = replace(current, tokens=(*current.tokens, record))
            else:
                record = existing
            accounts[account_name] = current
            await self._store.save(accounts)
        return record

    async def remove_token(self, account_name: str, token_id: str) -> bool:
        """Remove the token with id ``token_id``; return whether it was found.

        The id is the one ``bacsy accounts list`` shows; surrounding whitespace is
        ignored. The account entry stays even when its last token is removed.
        """
        token_id = token_id.strip()
        async with self._lock, self._store.locked():
            accounts = await self._store.load()
            account = accounts.get(account_name)
            if account is None:
                return False
            remaining = tuple(r for r in account.tokens if r.token.token_id != token_id)
            if len(remaining) == len(account.tokens):
                return False
            accounts[account_name] = replace(account, tokens=remaining)
            await self._store.save(accounts)
            return True

    async def rename(self, old_name: str, new_name: str) -> None:
        """Rename an account.

        Raises:
            AccountNotFoundError: ``old_name`` does not exist.
            AccountExistsError: ``new_name`` already exists.
            ValueError: ``new_name`` is not a valid account name.
        """
        new_name = validate_account_name(new_name)
        async with self._lock, self._store.locked():
            accounts = await self._store.load()
            if old_name not in accounts:
                msg = f"no account named {old_name!r}"
                raise AccountNotFoundError(msg, name=old_name)
            if new_name in accounts:
                msg = f"an account named {new_name!r} already exists"
                raise AccountExistsError(msg, name=new_name)
            renamed = {
                (new_name if key == old_name else key): (
                    replace(acc, name=new_name) if key == old_name else acc
                )
                for key, acc in accounts.items()
            }
            await self._store.save(renamed)

    async def prune(self, *, now: float | None = None) -> dict[str, list[TokenRecord]]:
        """Drop expired tokens and those marked dead from every account.

        ``now`` defaults to the clock. Returns the removed records per account, keyed by
        account name; accounts with nothing removed are absent. The store is written
        only when something was removed.
        """
        now = self._clock() if now is None else now
        removed: dict[str, list[TokenRecord]] = {}
        async with self._lock, self._store.locked():
            accounts = await self._store.load()
            for account_name, account in accounts.items():
                gone = [r for r in account.tokens if r.token.is_expired(now) or not r.live]
                if gone:
                    removed[account_name] = gone
                    kept = tuple(r for r in account.tokens if r not in gone)
                    accounts[account_name] = replace(account, tokens=kept)
            if removed:
                await self._store.save(accounts)
        return removed

    async def mark_dead(
        self, token: RefreshToken, reason: TokenRefreshReason, *, now: float | None = None
    ) -> None:
        """Record that the endpoint rejected ``token`` for ``reason``.

        The mark is written onto every stored record with the same session id, in any
        account. ``now`` defaults to the clock. A token that is not stored is ignored.
        """
        status = TokenStatus(reason=reason, at=int(self._clock() if now is None else now))
        await self._set_status(token, status)

    async def clear_dead(self, token: RefreshToken) -> None:
        """Remove the dead mark from every stored record with the same session id."""
        await self._set_status(token, None)

    async def _set_status(self, token: RefreshToken, status: TokenStatus | None) -> None:
        async with self._lock, self._store.locked():
            accounts = await self._store.load()
            changed = False
            for account_name, account in accounts.items():
                records = list(account.tokens)
                touched = False
                for index, record in enumerate(records):
                    if record.token.sid != token.sid or record.dead == status:
                        continue
                    records[index] = replace(record, dead=status)
                    touched = True
                if touched:
                    accounts[account_name] = replace(account, tokens=tuple(records))
                    changed = True
            if changed:
                await self._store.save(accounts)

    async def live_tokens(self, account_name: str) -> tuple[RefreshToken, ...]:
        """Return the tokens of ``account_name`` not marked dead, in stored order.

        Raises:
            AccountNotFoundError: no account called ``account_name`` exists.
        """
        account = await self.get(account_name)
        if account is None:
            msg = (
                f"no account named {account_name!r}; run: "
                f"bacsy accounts add {account_name}, then bacsy tokens add {account_name}"
            )
            raise AccountNotFoundError(msg, name=account_name)
        return account.live_tokens

    async def verify(
        self,
        http: httpx2.AsyncClient,
        *,
        account_name: str | None = None,
        now: float | None = None,
        config: ClientConfig | None = None,
    ) -> list[VerifyResult]:
        """Check every token, or those of ``account_name``, against the token endpoint.

        A token already expired by its ``exp`` claim is reported as expired without a
        network call. Expired and revoked rejections are recorded as dead marks; a token
        the endpoint accepts has any existing mark cleared. Failures that do not
        classify the token are returned in `VerifyResult.error`. ``now`` defaults to the
        clock and ``config`` to `ClientConfig()`.

        Raises:
            AccountNotFoundError: ``account_name`` is given and no such account exists.
        """
        now = self._clock() if now is None else now
        token_path = (config or ClientConfig()).token_endpoint_path
        if account_name is None:
            accounts = await self.list_accounts()
        else:
            account = await self.get(account_name)
            if account is None:
                msg = f"no account named {account_name!r}"
                raise AccountNotFoundError(msg, name=account_name)
            accounts = [account]
        results: list[VerifyResult] = []
        for account in accounts:
            for record in account.tokens:
                results.append(await self._verify_one(http, account, record.token, now, token_path))
        return results

    async def _verify_one(
        self,
        http: httpx2.AsyncClient,
        account: Account,
        token: RefreshToken,
        now: float,
        token_path: str,
    ) -> VerifyResult:
        if token.is_expired(now):
            return VerifyResult(account=account, token=token, reason=TokenRefreshReason.EXPIRED)
        try:
            await exchange_refresh_token(
                http, token_path=token_path, scope=token.scope, refresh_token=token.value, now=now
            )
        except TokenRefreshError as exc:
            if exc.reason in _PERSISTED_REASONS:
                await self.mark_dead(token, exc.reason, now=now)
            return VerifyResult(account=account, token=token, reason=exc.reason)
        except BacsyError as exc:
            return VerifyResult(account=account, token=token, error=exc)
        await self.clear_dead(token)
        return VerifyResult(account=account, token=token)

    def token_provider(
        self,
        account_name: str,
        *,
        http: httpx2.AsyncClient,
        cache: AccessTokenCache | None = None,
        config: ClientConfig | None = None,
    ) -> RefreshingAccessTokenProvider:
        """Return a provider minting access tokens from the live tokens of ``account_name``.

        The account is read on the provider's first use, not here. Rejections the
        endpoint reports as expired or revoked are recorded as dead marks on the stored
        token. ``cache`` defaults to a `DefaultAccessTokenCache` and ``config`` to
        `ClientConfig()`.
        """
        config = config or ClientConfig()

        async def tokens() -> tuple[RefreshToken, ...]:
            return await self.live_tokens(account_name)

        async def on_rejected(token: RefreshToken, reason: TokenRefreshReason) -> None:
            if reason in _PERSISTED_REASONS:
                await self.mark_dead(token, reason)

        return RefreshingAccessTokenProvider(
            tokens,
            http=http,
            cache=cache if cache is not None else DefaultAccessTokenCache(clock=self._clock),
            on_rejected=on_rejected,
            token_path=config.token_endpoint_path,
            access_skew_seconds=config.access_token_skew_seconds,
            clock=self._clock,
        )
