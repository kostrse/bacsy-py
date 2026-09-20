"""Credential resolution: the account and refresh token resolvers and their variables."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from bacsy.accounts import AccountManager
from bacsy.auth import MemoryAccessTokenCache, TokenScope
from bacsy.credentials import account_token_provider, refresh_token_provider
from bacsy.exceptions import AccountNotFoundError, ConfigurationError, InvalidTokenError
from tests.auth.fakes import DAY, Keycloak, make_refresh_token

if TYPE_CHECKING:
    from pathlib import Path

NOW = 4_000_000_000
"""Far enough ahead that tokens are live for the providers' real clock."""


def _manager(tmp_path: Path) -> AccountManager:
    return AccountManager.from_file(tmp_path / "accounts.json")


async def test_refresh_tokens_come_from_the_argument() -> None:
    keycloak = Keycloak(clock=lambda: NOW)
    read = make_refresh_token(scope=TokenScope.READ, exp=NOW + DAY)
    write = make_refresh_token(scope=TokenScope.WRITE, exp=NOW + DAY)

    async with keycloak.http() as http:
        provider = refresh_token_provider(
            [f" \t{read}\n", f"\r{write} "], http=http, env={}, cache=MemoryAccessTokenCache()
        )
        assert await provider.get(TokenScope.READ) == "acc1"
        assert await provider.get(TokenScope.WRITE) == "acc2"


async def test_refresh_token_variable_holds_several_tokens() -> None:
    """Whitespace and commas both separate tokens, and each scope gets its own."""
    keycloak = Keycloak(clock=lambda: NOW)
    read = make_refresh_token(scope=TokenScope.READ, exp=NOW + DAY)
    write = make_refresh_token(scope=TokenScope.WRITE, exp=NOW + DAY)
    env = {"BACSY_REFRESH_TOKEN": f" \t{read}, \n{write}\r\n"}

    async with keycloak.http() as http:
        provider = refresh_token_provider(http=http, env=env, cache=MemoryAccessTokenCache())
        assert await provider.get(TokenScope.READ) == "acc1"
        assert await provider.get(TokenScope.WRITE) == "acc2"


@pytest.mark.parametrize("env", [{}, {"BACSY_REFRESH_TOKEN": ""}, {"BACSY_REFRESH_TOKEN": " , "}])
async def test_no_refresh_token_anywhere_is_an_error(env: dict[str, str]) -> None:
    """An unset, empty, or separator-only variable are all treated as no token."""
    keycloak = Keycloak(clock=lambda: NOW)

    async with keycloak.http() as http:
        with pytest.raises(ConfigurationError, match="no refresh token given") as info:
            refresh_token_provider(http=http, env=env, cache=MemoryAccessTokenCache())

    assert "BACSY_REFRESH_TOKEN" in str(info.value)


async def test_an_undecodable_variable_names_the_variable_not_the_value() -> None:
    keycloak = Keycloak(clock=lambda: NOW)
    env = {"BACSY_REFRESH_TOKEN": "not-a-token-at-all"}

    async with keycloak.http() as http:
        with pytest.raises(ConfigurationError, match="BACSY_REFRESH_TOKEN") as info:
            refresh_token_provider(http=http, env=env, cache=MemoryAccessTokenCache())

    assert "not-a-token-at-all" not in str(info.value)


@pytest.mark.parametrize("use_env", [True, False])
async def test_invalid_item_rejects_all_refresh_tokens(use_env: bool) -> None:
    keycloak = Keycloak(clock=lambda: NOW)
    raw = make_refresh_token(exp=NOW + DAY) + ", garbage-value"
    async with keycloak.http() as http:
        with pytest.raises(InvalidTokenError):
            refresh_token_provider(
                None if use_env else raw,
                http=http,
                env={"BACSY_REFRESH_TOKEN": raw} if use_env else {},
                cache=MemoryAccessTokenCache(),
            )
    assert keycloak.calls == []


async def test_the_refresh_resolver_ignores_the_account_variable(tmp_path: Path) -> None:
    keycloak = Keycloak(clock=lambda: NOW)
    manager = _manager(tmp_path)
    await manager.add_token("acct", make_refresh_token(exp=NOW + DAY))

    async with keycloak.http() as http:
        with pytest.raises(ConfigurationError, match="no refresh token given"):
            refresh_token_provider(
                http=http, env={"BACSY_ACCOUNT": "acct"}, cache=MemoryAccessTokenCache()
            )

    assert keycloak.calls == []


async def test_account_comes_from_the_argument_or_the_variable(tmp_path: Path) -> None:
    keycloak = Keycloak(clock=lambda: NOW)
    manager = _manager(tmp_path)
    await manager.add_token("acct2", make_refresh_token(exp=NOW + DAY))

    async with keycloak.http() as http:
        named = account_token_provider(
            http=http,
            env={"BACSY_ACCOUNT": "acct2"},
            accounts=manager,
            cache=MemoryAccessTokenCache(),
        )
        assert await named.get(TokenScope.READ) == "acc1"

        passed = account_token_provider(
            "acct2", http=http, env={}, accounts=manager, cache=MemoryAccessTokenCache()
        )
        assert await passed.get(TokenScope.READ) == "acc2"


async def test_no_account_name_anywhere_is_an_error(tmp_path: Path) -> None:
    keycloak = Keycloak(clock=lambda: NOW)
    manager = _manager(tmp_path)

    async with keycloak.http() as http:
        with pytest.raises(ConfigurationError, match="no account name given") as info:
            account_token_provider(http=http, env={}, accounts=manager)

    assert "BACSY_ACCOUNT" in str(info.value)


async def test_the_account_resolver_ignores_the_refresh_token_variable(tmp_path: Path) -> None:
    """An explicitly named account is used even when the token variable is set."""
    keycloak = Keycloak(clock=lambda: NOW)
    manager = _manager(tmp_path)
    env = {"BACSY_REFRESH_TOKEN": make_refresh_token(exp=NOW + DAY)}

    async with keycloak.http() as http:
        provider = account_token_provider(
            "main", http=http, env=env, accounts=manager, cache=MemoryAccessTokenCache()
        )
        with pytest.raises(AccountNotFoundError, match="no account named 'main'"):
            await provider.get(TokenScope.READ)

    assert keycloak.calls == []
