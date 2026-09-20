"""The account manager: lifecycle, live tokens, verification and provider building."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from bacsy.accounts import Account, AccountManager, AccountStore, TokenStatus
from bacsy.auth import MemoryAccessTokenCache, RefreshToken, TokenScope
from bacsy.exceptions import (
    AccountError,
    AccountExistsError,
    AccountNotFoundError,
    InvalidTokenError,
    TokenRefreshReason,
    TransportError,
)
from tests.auth.fakes import DAY, OTHER_AGREEMENT, Keycloak, make_refresh_token

if TYPE_CHECKING:
    from collections.abc import Callable

    from bacsy.accounts import TokenRecord
    from tests.conftest import FakeClock

NOW = 1_000_000


def _manager(tmp_path: Path, *, clock: Callable[[], float] = time.time) -> AccountManager:
    return AccountManager.from_file(tmp_path / "accounts.json", clock=clock)


async def test_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "accounts.json"
    read = make_refresh_token(exp=NOW + DAY)
    write = make_refresh_token(scope=TokenScope.WRITE, exp=NOW + DAY, token_id="00002tst")

    writer = AccountManager.from_file(path)
    saved = await writer.add_token("main", f" \t\n{read}\r\n\u00a0", label='Main "acct"')
    await writer.add_token("main", write)
    await writer.add_token("second", make_refresh_token(exp=NOW + DAY))

    manager = AccountManager.from_file(path)
    account = await manager.get("main")
    assert saved.token.value == read
    assert saved.token == RefreshToken.parse(read)
    assert account is not None
    assert account.label == 'Main "acct"'
    assert [r.token.scope for r in account.tokens] == [TokenScope.READ, TokenScope.WRITE]
    assert await manager.get("missing") is None
    assert {a.name for a in await manager.list_accounts()} == {"main", "second"}


async def test_two_managers_over_one_file_keep_both_changes(tmp_path: Path) -> None:
    path = tmp_path / "accounts.json"

    await asyncio.gather(
        AccountManager.from_file(path).add_token("one", make_refresh_token(exp=NOW + DAY)),
        AccountManager.from_file(path).add_token("two", make_refresh_token(exp=NOW + DAY)),
    )

    names = {a.name for a in await AccountManager.from_file(path).list_accounts()}
    assert names == {"one", "two"}


async def test_create_makes_an_empty_account_once(tmp_path: Path) -> None:
    manager = _manager(tmp_path)

    created = await manager.create("main", label="Main")

    assert created == Account(name="main", label="Main")
    assert await manager.get("main") == created
    assert await manager.list_accounts() == [created]
    with pytest.raises(AccountExistsError, match="already exists") as info:
        await manager.create("main")
    assert info.value.name == "main"
    assert (await manager.live_tokens("main")) == ()


@pytest.mark.parametrize("wrapper", ['"{}"', "Bearer {}", "{};", "garbage{}"])
async def test_add_token_rejects_wrappers(tmp_path: Path, wrapper: str) -> None:
    manager = _manager(tmp_path)
    value = make_refresh_token(exp=NOW + DAY)
    with pytest.raises(InvalidTokenError):
        await manager.add_token("main", wrapper.format(value))
    assert await manager.list_accounts() == []


@pytest.mark.parametrize("token_id", [None, "00002tst"])
async def test_add_token_is_idempotent_and_keeps_label(
    tmp_path: Path, token_id: str | None
) -> None:
    """The same token added twice is stored once, whether or not it carries a web id."""
    manager = _manager(tmp_path)
    value = make_refresh_token(exp=NOW + DAY, token_id=token_id)

    first = await manager.add_token("main", value, label="first")
    second = await manager.add_token("main", value)

    account = await manager.get("main")
    assert account is not None
    assert len(account.tokens) == 1
    assert second == first
    assert account.label == "first"


async def test_add_token_rejects_a_different_brokerage_account(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    await manager.add_token("main", make_refresh_token(exp=NOW + DAY))

    with pytest.raises(AccountError, match="different brokerage accounts") as info:
        await manager.add_token(
            "main", make_refresh_token(exp=NOW + DAY, agreement_id=OTHER_AGREEMENT)
        )
    assert info.value.name == "main"


async def test_update_replaces_a_whole_account(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    await manager.add_token("main", make_refresh_token(exp=NOW + DAY), label="before")
    account = await manager.get("main")
    assert account is not None

    await manager.update(replace(account, label="after"))

    reloaded = await manager.get("main")
    assert reloaded is not None
    assert reloaded.label == "after"
    assert reloaded.tokens == account.tokens


async def test_update_requires_an_existing_account(tmp_path: Path) -> None:
    manager = _manager(tmp_path)

    with pytest.raises(AccountNotFoundError, match="no account named 'ghost'"):
        await manager.update(Account(name="ghost"))


async def test_remove_token_by_id_only(tmp_path: Path) -> None:
    """Only the token id removes a token; its value and short form do not."""
    manager = _manager(tmp_path)
    first = await manager.add_token("main", make_refresh_token(exp=NOW + DAY, token_id="00002tst"))
    second = await manager.add_token("main", make_refresh_token(exp=NOW + DAY, marker="2"))

    assert not await manager.remove_token("main", first.token.value)
    assert not await manager.remove_token("main", first.token.short)
    assert not await manager.remove_token("main", second.token.value)
    assert not await manager.remove_token("main", second.token.short)
    assert not await manager.remove_token("other", "00002tst")
    assert await manager.remove_token("main", " 00002tst ")
    assert await manager.remove_token("main", second.token.token_id)
    assert not await manager.remove_token("main", "00002tst")

    account = await manager.get("main")
    assert account is not None
    assert account.tokens == ()


async def test_names_are_checked_when_an_account_is_created(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    await manager.create("main")

    with pytest.raises(ValueError, match="contains ' '"):
        await manager.create("my acct")
    with pytest.raises(ValueError, match="contains ' '"):
        await manager.add_token("my acct", make_refresh_token(exp=NOW + DAY))
    with pytest.raises(ValueError, match="contains ' '"):
        await manager.rename("main", "my acct")
    assert [a.name for a in await manager.list_accounts()] == ["main"]


async def test_names_are_stored_in_nfc_form(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    decomposed = "и\u0306"  # й as и + combining breve

    created = await manager.create(decomposed)
    assert created.name == "й"
    assert await manager.get("й") is not None

    record = await manager.add_token(decomposed, make_refresh_token(exp=NOW + DAY))
    account = await manager.get("й")
    assert account is not None
    assert account.tokens == (record,)
    assert [a.name for a in await manager.list_accounts()] == ["й"]

    await manager.rename("й", "и\u0306-2")
    assert [a.name for a in await manager.list_accounts()] == ["й-2"]


async def test_a_stored_name_that_breaks_the_rule_stays_usable(tmp_path: Path) -> None:
    path = tmp_path / "accounts.json"
    await AccountStore(path).save({"my acct": Account(name="my acct")})
    manager = AccountManager.from_file(path)

    record = await manager.add_token("my acct", make_refresh_token(exp=NOW + DAY))
    assert await manager.remove_token("my acct", record.token.token_id)
    await manager.rename("my acct", "main")
    assert await manager.get("my acct") is None
    assert await manager.get("main") is not None


async def test_rename_and_delete(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    await manager.add_token("old", make_refresh_token(exp=NOW + DAY), label="L")
    await manager.add_token("taken", make_refresh_token(exp=NOW + DAY, marker="t"))

    await manager.rename("old", "new")
    renamed = await manager.get("new")
    assert renamed is not None
    assert renamed.name == "new"
    assert renamed.label == "L"
    assert await manager.get("old") is None
    with pytest.raises(AccountNotFoundError, match="no account named 'old'"):
        await manager.rename("old", "x")
    with pytest.raises(AccountExistsError, match="already exists"):
        await manager.rename("new", "taken")
    assert await manager.delete("new")
    assert not await manager.delete("new")


async def test_prune_drops_expired_and_dead_tokens(tmp_path: Path) -> None:
    manager = _manager(tmp_path, clock=lambda: NOW)
    expired = await manager.add_token("main", make_refresh_token(exp=NOW - 1))
    dead = await manager.add_token("main", make_refresh_token(exp=NOW + DAY, sid="dead"))
    kept = await manager.add_token("main", make_refresh_token(exp=NOW + DAY, sid="kept"))
    before = manager.store.path.stat().st_mtime_ns

    await manager.mark_dead(dead.token, TokenRefreshReason.REVOKED, now=NOW)
    dead = _record(await manager.get("main"), "dead")

    removed = await manager.prune(now=NOW)

    assert removed == {"main": [expired, dead]}
    account = await manager.get("main")
    assert account is not None
    assert account.tokens == (kept,)
    assert await manager.prune(now=NOW) == {}
    assert manager.store.path.stat().st_mtime_ns >= before


async def test_live_tokens_skip_dead_marks_and_require_the_account(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    dead = await manager.add_token("main", make_refresh_token(exp=NOW + DAY, sid="dead"))
    kept = await manager.add_token("main", make_refresh_token(exp=NOW + DAY, sid="kept"))
    await manager.mark_dead(dead.token, TokenRefreshReason.REVOKED)

    assert await manager.live_tokens("main") == (kept.token,)
    with pytest.raises(AccountNotFoundError, match="no account named 'ghost'") as info:
        await manager.live_tokens("ghost")
    assert info.value.name == "ghost"

    # BACSY_REFRESH_TOKEN has no effect on this call.
    assert "BACSY_REFRESH_TOKEN" not in str(info.value)


async def test_token_provider_reads_lazily_and_records_rejections(
    tmp_path: Path, fake_clock: FakeClock
) -> None:
    keycloak = Keycloak(clock=fake_clock)
    manager = _manager(tmp_path, clock=fake_clock)
    revoked = await manager.add_token(
        "main", make_refresh_token(exp=int(fake_clock.now) + 80 * DAY, sid="revoked")
    )
    await manager.add_token(
        "main", make_refresh_token(exp=int(fake_clock.now) + 20 * DAY, sid="backup")
    )
    keycloak.revoked.add("revoked")

    async with keycloak.http() as http:
        provider = manager.token_provider("main", http=http, cache=MemoryAccessTokenCache())
        assert keycloak.calls == []
        assert await provider.get(TokenScope.READ) == "acc1"

    account = await manager.get("main")
    assert account is not None
    assert _record(account, "revoked").dead is not None
    assert _record(account, "revoked").dead.reason is TokenRefreshReason.REVOKED  # pyright: ignore[reportOptionalMemberAccess]
    assert await manager.live_tokens("main") == (account.tokens[1].token,)
    assert revoked.token.sid not in {t.sid for t in await manager.live_tokens("main")}


async def test_token_provider_defaults_to_memory_without_a_state_directory(
    tmp_path: Path,
    fake_clock: FakeClock,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    keycloak = Keycloak(clock=fake_clock)
    manager = _manager(tmp_path, clock=fake_clock)
    await manager.add_token("main", make_refresh_token(exp=int(fake_clock.now) + DAY))
    for name in ("BACSY_STATE_DIR", "XDG_STATE_HOME", "LOCALAPPDATA", "HOME"):
        monkeypatch.delenv(name, raising=False)

    def _no_home() -> Path:
        msg = "Could not determine home directory."
        raise RuntimeError(msg)

    monkeypatch.setattr(Path, "home", staticmethod(_no_home))

    with caplog.at_level(logging.WARNING, logger="bacsy.auth"):
        async with keycloak.http() as http:
            provider = manager.token_provider("main", http=http)
            assert await provider.get(TokenScope.READ) == "acc1"
            assert await provider.get(TokenScope.READ) == "acc1"

    assert len(keycloak.calls) == 1
    assert [r.message for r in caplog.records].count(
        "no state directory available; caching access tokens in memory only"
    ) == 1
    assert not (tmp_path / "tokens.json").exists()


async def test_verify_reports_each_token_and_updates_marks(
    tmp_path: Path, fake_clock: FakeClock
) -> None:
    keycloak = Keycloak(clock=fake_clock)
    manager = _manager(tmp_path, clock=fake_clock)
    ok = await manager.add_token(
        "main", make_refresh_token(exp=int(fake_clock.now) + DAY, sid="ok")
    )
    await manager.add_token(
        "main", make_refresh_token(exp=int(fake_clock.now) + DAY, sid="revoked", marker="r")
    )
    expired = await manager.add_token(
        "main", make_refresh_token(exp=int(fake_clock.now) - 1, sid="old")
    )
    await manager.mark_dead(ok.token, TokenRefreshReason.REVOKED)  # stale mark, cleared by verify
    keycloak.revoked.add("revoked")

    async with keycloak.http() as http:
        results = await manager.verify(http)
        with pytest.raises(AccountNotFoundError, match="no account named 'ghost'"):
            await manager.verify(http, account_name="ghost")

    by_sid = {r.token.sid: r for r in results}
    assert by_sid["ok"].ok
    assert by_sid["revoked"].reason is TokenRefreshReason.REVOKED
    assert by_sid["old"].reason is TokenRefreshReason.EXPIRED
    assert len(keycloak.calls) == 2  # the offline-expired token is not sent
    account = await manager.get("main")
    assert account is not None
    assert {r.token.sid for r in account.tokens if not r.live} == {"revoked"}
    assert expired.token.sid == "old"


def _record(account: Account | None, sid: str) -> TokenRecord:
    assert account is not None
    return next(r for r in account.tokens if r.token.sid == sid)


async def test_marking_an_unstored_token_is_ignored(tmp_path: Path) -> None:
    manager = _manager(tmp_path, clock=lambda: NOW)
    await manager.add_token("main", make_refresh_token(exp=NOW + DAY, sid="kept"))
    stranger = RefreshToken.parse(make_refresh_token(exp=NOW + DAY, sid="stranger"))

    await manager.mark_dead(stranger, TokenRefreshReason.REVOKED, now=NOW)

    account = await manager.get("main")
    assert account is not None
    assert all(r.live for r in account.tokens)


async def test_clearing_a_mark_restores_the_token(tmp_path: Path) -> None:
    manager = _manager(tmp_path, clock=lambda: NOW)
    record = await manager.add_token("main", make_refresh_token(exp=NOW + DAY, sid="one"))

    await manager.mark_dead(record.token, TokenRefreshReason.EXPIRED, now=NOW)
    marked = _record(await manager.get("main"), "one")
    await manager.clear_dead(record.token)

    assert marked.dead == TokenStatus(reason=TokenRefreshReason.EXPIRED, at=NOW)
    assert _record(await manager.get("main"), "one").live
    assert await manager.live_tokens("main") == (record.token,)


async def test_removing_a_token_takes_its_mark_with_it(tmp_path: Path) -> None:
    manager = _manager(tmp_path, clock=lambda: NOW)
    record = await manager.add_token("main", make_refresh_token(exp=NOW + DAY, sid="one"))
    await manager.mark_dead(record.token, TokenRefreshReason.REVOKED, now=NOW)

    assert await manager.remove_token("main", record.token.token_id)

    await manager.add_token("main", record.token.value)
    assert _record(await manager.get("main"), "one").live


async def test_an_added_token_records_when_it_was_added(tmp_path: Path) -> None:
    manager = _manager(tmp_path, clock=lambda: NOW + 5.5)

    record = await manager.add_token("main", make_refresh_token(exp=NOW + DAY))

    assert record.added_at == NOW + 5
    assert record.live


async def test_verify_returns_transport_failures_as_errors(tmp_path: Path) -> None:
    import httpx2

    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("down", request=request)

    manager = _manager(tmp_path)
    await manager.add_token("main", make_refresh_token(exp=NOW + DAY))
    async with httpx2.AsyncClient(
        transport=httpx2.MockTransport(handler), base_url="https://x"
    ) as http:
        [result] = await manager.verify(http, now=NOW)

    assert isinstance(result.error, TransportError)
    assert not result.ok
