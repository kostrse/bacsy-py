"""The ``bacsy tokens`` commands."""

from __future__ import annotations

import asyncio
import stat
import sys
from dataclasses import replace
from typing import TYPE_CHECKING, cast

import httpx2
import pytest

from bacsy.accounts import AccountManager
from bacsy.auth import RefreshToken, TokenScope
from bacsy.cli import CliDeps, run_command
from bacsy.exceptions import TokenRefreshReason
from tests.cli.conftest import OTHER_AGREEMENT, headings, mark_dead, payload, rows

if TYPE_CHECKING:
    from pathlib import Path

    from bacsy.accounts import TokenStatus
    from tests.auth.fakes import Keycloak
    from tests.cli.conftest import Clock, Prompts, Runner, TokenFactory


async def _dead_sessions(path: Path | None = None) -> dict[str, TokenStatus]:
    """The dead marks now on the stored records, by session id."""
    return {
        record.token.sid: record.dead
        for account in await AccountManager.from_file(path).list_accounts()
        for record in account.tokens
        if record.dead is not None
    }


@pytest.fixture
async def empty_main(accounts_file: Path) -> AccountManager:
    """An account ``main`` without tokens yet."""
    manager = AccountManager.from_file(accounts_file)
    await manager.create("main", label="Main")
    return manager


async def test_add_prompts_without_echo_and_prints_the_row(
    run: Runner, prompts: Prompts, token: TokenFactory, empty_main: AccountManager
) -> None:
    value = token(TokenScope.WRITE, token_id="00003tst")
    prompts.secrets.append(f"  {value}\n")

    code, out, err = await run("tokens", "add", "main")

    assert code == 0
    assert prompts.asked == ["refresh token for account 'main' (input is hidden): "]
    assert err == (
        "hint: account 'main' is ready; use it with\n      TradeApiClient.from_account(\"main\")\n"
    )
    message, table = out.split("\n\n", 1)
    assert message == "saved write token 00003tst to account 'main'"
    assert rows(table)[0][:3] == ["eyJh**********" + value[-4:], "00003tst", "write"]
    assert headings(table) == []  # one account is already named by the message
    assert value not in out
    account = await empty_main.get("main")
    assert account is not None
    assert account.tokens[0].token.value == value


async def test_add_greets_only_the_first_token_of_the_accounts_file(
    run: Runner, seeded: dict[str, str], token: TokenFactory
) -> None:
    """The ready-to-use hint is a one-off; the store already holds tokens here."""
    _, _, err = await run("tokens", "add", "main", "--stdin", stdin=token(sid="another"))

    assert "is ready" not in err
    assert err == ""


async def test_add_says_nothing_about_the_state_of_other_accounts(
    run: Runner, seeded: dict[str, str], token: TokenFactory, clock: Clock
) -> None:
    """`accounts list` is where the revoked token elsewhere is reported, not here."""
    await mark_dead(seeded["spare-read"], TokenRefreshReason.REVOKED, clock.now)

    _, _, err = await run("tokens", "add", "main", "--stdin", stdin=token(sid="another"))

    assert err == ""


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions")
async def test_add_keeps_the_file_owner_only(
    run: Runner, token: TokenFactory, accounts_file: Path, empty_main: AccountManager
) -> None:
    await run("tokens", "add", "main", "--stdin", stdin=token() + "\n")

    mode = await asyncio.to_thread(lambda: accounts_file.stat().st_mode)
    assert stat.S_IMODE(mode) == 0o600


async def test_add_refuses_an_unknown_account(
    run: Runner, token: TokenFactory, accounts_file: Path, prompts: Prompts
) -> None:
    code, out, err = await run("tokens", "add", "mian", "--stdin", stdin=token())

    assert code == 1
    assert out == ""
    assert err == "error: no account named 'mian'\nhint: create it first: bacsy accounts add mian\n"
    assert prompts.asked == []
    assert not await asyncio.to_thread(accounts_file.exists)


async def test_add_names_the_saved_accounts_on_a_typo(
    run: Runner, seeded: dict[str, str], token: TokenFactory
) -> None:
    _, _, err = await run("tokens", "add", "mian", "--stdin", stdin=token())

    assert (
        "hint: create it first: bacsy accounts add mian\n      saved accounts: main, spare" in err
    )


async def test_add_appends_to_an_existing_account(
    run: Runner, seeded: dict[str, str], token: TokenFactory, accounts_file: Path
) -> None:
    code, _, err = await run("tokens", "add", "main", "--stdin", stdin=token(days=85))

    assert code == 0
    assert err == ""
    account = await AccountManager.from_file(accounts_file).get("main")
    assert account is not None
    assert len(account.tokens) == 3
    assert account.label == "Main account"


async def test_add_an_already_saved_token_is_a_no_op(
    run: Runner, seeded: dict[str, str], accounts_file: Path
) -> None:
    code, out, _ = await run("tokens", "add", "main", "--stdin", stdin=seeded["main-read"])
    assert code == 0
    assert out.startswith("token 00001tst is already saved in account 'main'\n\nTOKEN")

    code, out, _ = await run(
        "tokens", "add", "main", "--stdin", "--json", stdin=seeded["main-read"]
    )
    assert code == 0
    assert payload(out)["added"] is False
    account = await AccountManager.from_file(accounts_file).get("main")
    assert account is not None
    assert len(account.tokens) == 2


async def test_add_drops_the_quotes_around_a_pasted_token(
    run: Runner, token: TokenFactory, empty_main: AccountManager
) -> None:
    value = token(token_id="00003tst")

    code, out, _ = await run("tokens", "add", "main", "--stdin", stdin=f' "{value}" \n')

    assert code == 0
    assert "saved read token 00003tst" in out
    account = await empty_main.get("main")
    assert account is not None
    assert account.tokens[0].token.value == value


@pytest.mark.parametrize(
    "wrapper",
    [
        '"{}',
        "Bearer <{}>",
        '{{"token":"{}"}}',
        "\n\n```\n{}\n```",
        "text {}. more text",
        "\ufeff{}\u200b",
    ],
)
async def test_add_extracts_a_token_from_pasted_text(
    run: Runner, token: TokenFactory, empty_main: AccountManager, wrapper: str
) -> None:
    value = token()
    code, _, _ = await run("tokens", "add", "main", "--stdin", stdin=wrapper.format(value))

    assert code == 0
    account = await empty_main.get("main")
    assert account is not None
    assert account.tokens[0].token == RefreshToken.parse(value)


async def test_add_refuses_expired_and_garbage(
    run: Runner, token: TokenFactory, empty_main: AccountManager
) -> None:
    code, _, err = await run("tokens", "add", "main", "--stdin", stdin=token(days=-1))
    assert code == 1
    assert err.startswith("error: token ")
    assert "expired on" in err

    code, _, err = await run("tokens", "add", "main", "--stdin", stdin="garbage-value")
    assert code == 1
    assert err.startswith("error: not a BCS refresh token:")
    assert "hint: issue an API token in the BCS web terminal" in err
    assert "garbage-value" not in err
    account = await empty_main.get("main")
    assert account is not None
    assert account.tokens == ()


async def test_add_saves_first_parseable_refresh_token(
    run: Runner, token: TokenFactory, empty_main: AccountManager
) -> None:
    first = token()
    second = token(sid="later")
    code, _, _ = await run(
        "tokens",
        "add",
        "main",
        "--stdin",
        stdin=f"garbage a.b.c\nBearer <{first}>\n{second}",
    )
    assert code == 0
    account = await empty_main.get("main")
    assert account is not None
    assert [r.token for r in account.tokens] == [RefreshToken.parse(first)]


async def test_add_does_not_skip_first_expired_token(
    run: Runner, token: TokenFactory, empty_main: AccountManager
) -> None:
    code, _, err = await run(
        "tokens",
        "add",
        "main",
        "--stdin",
        stdin=f"{token(days=-1)}\n{token()}",
    )
    assert code == 1
    assert "expired on" in err
    account = await empty_main.get("main")
    assert account is not None
    assert account.tokens == ()


async def test_add_refuses_a_token_of_another_brokerage_account(
    run: Runner, seeded: dict[str, str], token: TokenFactory
) -> None:
    other = token(agreement_id="00000000-0000-4000-8000-000000000003")

    code, _, err = await run("tokens", "add", "main", "--stdin", stdin=other)

    assert code == 1
    assert "different brokerage account" in err
    assert "hint: save it under another account name" in err
    assert "00000000-0000-4000-8000-000000000003" not in err


async def test_add_warns_when_another_account_has_the_same_brokerage_account(
    run: Runner, seeded: dict[str, str], token: TokenFactory, accounts_file: Path
) -> None:
    await AccountManager.from_file(accounts_file).create("duplicate")

    code, _, err = await run("tokens", "add", "duplicate", "--stdin", stdin=token(days=70))

    assert code == 0
    assert "warning: account 'main' already holds tokens" in err


async def test_add_json(run: Runner, token: TokenFactory, empty_main: AccountManager) -> None:
    value = token(token_id="00003tst")

    code, out, _ = await run("tokens", "add", "main", "--stdin", "--json", stdin=value)

    assert code == 0
    document = payload(out)
    assert document["account"] == "main"
    assert document["added"] is True
    assert cast("dict[str, object]", document["token"])["token_id"] == "00003tst"
    assert value not in out


async def test_remove_one_token_by_id(
    run: Runner, seeded: dict[str, str], accounts_file: Path
) -> None:
    code, out, err = await run("tokens", "remove", "main", "00002tst")

    assert code == 0
    assert out == "removed token 00002tst from account 'main'\n"
    assert err.startswith("note: removing tokens here does not revoke them")
    account = await AccountManager.from_file(accounts_file).get("main")
    assert account is not None
    assert [r.token.scope for r in account.tokens] == [TokenScope.READ]


async def test_remove_says_only_what_it_did(run: Runner, seeded: dict[str, str]) -> None:
    """Emptying an account is what was asked for, so nothing suggests refilling it."""
    token_id = RefreshToken.parse(seeded["spare-read"]).token_id

    _, _, err = await run("tokens", "remove", "spare", token_id)

    (note,) = err.splitlines()
    assert note.startswith("note: removing tokens here does not revoke them")


async def test_remove_one_token_by_derived_id(
    run: Runner, seeded: dict[str, str], accounts_file: Path
) -> None:
    """A token without a web-terminal id is removed by the id bacsy derived for it."""
    token_id = RefreshToken.parse(seeded["spare-read"]).token_id

    code, out, _ = await run("tokens", "remove", "spare", token_id)

    assert code == 0
    assert f"removed token {token_id}" in out
    account = await AccountManager.from_file(accounts_file).get("spare")
    assert account is not None
    assert account.tokens == ()


async def test_the_short_form_and_the_token_are_not_references(
    run: Runner, seeded: dict[str, str], accounts_file: Path
) -> None:
    token = RefreshToken.parse(seeded["main-read"])

    for ref in (token.short, token.value):
        code, _, err = await run("tokens", "remove", "main", ref)
        assert code == 1
        assert "has no token with ID" in err

    account = await AccountManager.from_file(accounts_file).get("main")
    assert account is not None
    assert len(account.tokens) == 2


async def test_remove_unknown_token_or_account(run: Runner, seeded: dict[str, str]) -> None:
    code, _, err = await run("tokens", "remove", "main", "nope")
    assert code == 1
    assert "error: account 'main' has no token with ID 'nope'" in err
    assert "hint: IDs are shown by: bacsy accounts list" in err

    code, _, err = await run("tokens", "remove", "ghost", "nope")
    assert code == 1
    assert "no account named 'ghost'" in err


async def test_remove_json(run: Runner, seeded: dict[str, str]) -> None:
    code, out, _ = await run("tokens", "remove", "main", "00002tst", "--json")

    assert code == 0
    document = payload(out)
    assert document["account"] == "main"
    assert cast("dict[str, object]", document["token"])["token_id"] == "00002tst"


async def test_prune_dry_run_then_apply(
    run: Runner, seeded: dict[str, str], token: TokenFactory, accounts_file: Path, clock: Clock
) -> None:
    manager = AccountManager.from_file(accounts_file)
    expired = await manager.add_token("main", token(days=-2, sid="gone"))
    await mark_dead(seeded["spare-read"], TokenRefreshReason.REVOKED, clock.now)

    code, out, err = await run("tokens", "prune", "--dry-run")
    assert code == 0
    table, message = out.rstrip().rsplit("\n", 1)
    assert message == "would remove 2 tokens"
    assert [r[-1] for r in rows(table)] == ["expired", "revoked"]  # a dry run previews what goes
    assert err == ""  # an operation reports what it did and stops
    main = await manager.get("main")
    assert main is not None
    assert len(main.tokens) == 3

    code, out, _ = await run("tokens", "prune")
    assert code == 0
    table, message = out.rstrip().rsplit("\n", 1)
    assert message == "removed 2 tokens"
    assert expired.token.token_id not in table  # the table is what the run left behind
    assert [r[1] for r in rows(table)] == ["00001tst", "00002tst"]
    assert "spare\n  (no tokens)" in table  # emptied, but still an account
    main = await manager.get("main")
    spare = await manager.get("spare")
    assert main is not None
    assert spare is not None
    assert len(main.tokens) == 2
    assert spare.tokens == ()

    code, out, _ = await run("tokens", "prune")
    assert code == 0
    table, message = out.rstrip().rsplit("\n", 1)
    assert message == "nothing to prune"
    assert len(rows(table)) == 2  # the listing appears whether or not there was work


async def test_prune_on_an_empty_store_says_only_that(run: Runner) -> None:
    code, out, err = await run("tokens", "prune")

    assert code == 0
    assert out == "no accounts saved\nnothing to prune\n"
    assert err == ""


async def test_prune_json(run: Runner, seeded: dict[str, str], clock: Clock) -> None:
    await mark_dead(seeded["spare-read"], TokenRefreshReason.REVOKED, clock.now)

    code, out, _ = await run("tokens", "prune", "--dry-run", "--json")

    assert code == 0
    document = payload(out)
    assert document["dry_run"] is True
    (removed,) = cast("list[dict[str, object]]", document["removed"])
    assert removed["account"] == "spare"
    assert cast("dict[str, object]", removed["token"])["status"] == "revoked"


async def test_verify_all_ok(run: Runner, seeded: dict[str, str], keycloak: Keycloak) -> None:
    await mark_dead(seeded["main-read"], TokenRefreshReason.REVOKED, 0)

    code, out, err = await run("tokens", "verify")

    assert code == 0
    assert err == ""
    assert sorted(keycloak.client_ids()) == ["trade-api-read", "trade-api-read", "trade-api-write"]
    assert all(call["refresh_token"][0] in seeded.values() for call in keycloak.calls)
    table, message = out.rstrip().rsplit("\n", 1)
    assert [r[-1] for r in rows(table)] == ["ok", "ok", "ok"]
    assert message == "verified 3 tokens: 3 ok"
    assert await _dead_sessions() == {}
    for value in seeded.values():
        assert value not in out


async def test_verify_reports_dead_tokens_and_exits_3(
    run: Runner,
    seeded: dict[str, str],
    keycloak: Keycloak,
    token: TokenFactory,
    accounts_file: Path,
) -> None:
    keycloak.revoked.add("main-write")
    await AccountManager.from_file(accounts_file).add_token(
        "spare", token(days=-1, sid="stale", agreement_id=OTHER_AGREEMENT)
    )
    keycloak.invalid.add(seeded["spare-read"])

    code, out, _ = await run("tokens", "verify")

    assert code == 3
    table, message = out.rstrip().rsplit("\n", 1)
    live = {
        short: line.split()[-1]
        for line in table.splitlines()
        for short in (RefreshToken.parse(v).short for v in seeded.values())
        if short in line
    }
    assert live[RefreshToken.parse(seeded["main-write"]).short] == "revoked"
    assert live[RefreshToken.parse(seeded["main-read"]).short] == "ok"
    assert live[RefreshToken.parse(seeded["spare-read"]).short] == "invalid"
    assert [r[-1] for r in rows(table)].count("expired") == 1
    assert len(keycloak.calls) == 3  # the offline-expired token is not sent
    dead = await _dead_sessions()
    assert dead["main-write"].reason is TokenRefreshReason.REVOKED
    assert "stale" not in dead
    assert message == "verified 4 tokens: 1 ok, 1 revoked, 1 expired, 1 invalid"


async def test_verify_groups_tokens_by_account(
    run: Runner, accounts_file: Path, token: TokenFactory, keycloak: Keycloak
) -> None:
    manager = AccountManager.from_file(accounts_file)
    await manager.add_token("zeta", token(days=10, sid="z1"))
    await manager.add_token("alpha", token(days=20, sid="a1"))
    await manager.add_token("zeta", token(days=30, sid="z2"))

    code, out, _ = await run("tokens", "verify")

    assert code == 0
    table, _summary = out.rstrip().rsplit("\n", 1)
    assert headings(table) == ["alpha", "zeta"]
    assert len(rows(table)) == 3


async def test_verify_orders_tokens_the_way_the_listing_does(
    run: Runner, accounts_file: Path, token: TokenFactory, keycloak: Keycloak
) -> None:
    manager = AccountManager.from_file(accounts_file)
    await manager.add_token("main", token(TokenScope.WRITE, days=10, token_id="w"))
    await manager.add_token("main", token(days=40, token_id="r"))

    _, verified, _ = await run("tokens", "verify")
    _, listed, _ = await run("accounts", "list")

    # a row reads the same way in both tables
    assert [r[1] for r in rows(verified)] == ["r", "w"] == [r[1] for r in rows(listed)]


async def test_verify_single_account_and_json(
    run: Runner, seeded: dict[str, str], keycloak: Keycloak
) -> None:
    keycloak.revoked.add("spare-read")

    code, out, _ = await run("tokens", "verify", "spare", "--json")

    assert code == 3
    document = payload(out)
    assert document["checked_at"] == "2027-01-15T08:00:00+00:00"
    assert document["summary"] == {"revoked": 1}
    (checked,) = cast("list[dict[str, object]]", document["tokens"])
    assert checked["account"] == "spare"
    assert checked["live"] == "revoked"
    assert checked["error"] is None
    assert cast("dict[str, object]", checked["token"])["status"] == "revoked"
    assert len(keycloak.calls) == 1

    code, _, err = await run("tokens", "verify", "ghost")
    assert code == 1
    assert "no account named 'ghost'" in err


async def test_verify_network_failure_exits_1(
    seeded: dict[str, str], deps: CliDeps, capsys: pytest.CaptureFixture[str]
) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("down", request=request)

    def factory() -> httpx2.AsyncClient:
        return httpx2.AsyncClient(transport=httpx2.MockTransport(handler), base_url="https://x")

    failing = replace(deps, http_client_factory=factory)
    code = await run_command(["tokens", "verify", "spare"], deps=failing)
    out, err = capsys.readouterr()

    assert code == 1
    assert rows(out)[0][-1] == "error"
    assert err.startswith("warning: token ")
    assert "(account 'spare')" in err


async def test_verify_writes_status_not_the_access_token_cache(
    run: Runner, seeded: dict[str, str], tmp_path: Path, keycloak: Keycloak
) -> None:
    keycloak.revoked.add("main-read")

    await run("tokens", "verify")

    assert not (tmp_path / "tokens.json").exists()
    assert set(await _dead_sessions()) == {"main-read"}


async def test_verify_advises_on_the_live_verdict(
    run: Runner, seeded: dict[str, str], keycloak: Keycloak, accounts_file: Path
) -> None:
    """An `invalid` verdict is never stored, so only the live column can advise on it."""
    keycloak.invalid.add(seeded["spare-read"])

    code, _, err = await run("tokens", "verify", "spare")

    assert code == 3
    assert err == (
        "warning: account 'spare' has no usable token\n"
        "         issue an API token in the BCS web terminal and run: "
        "bacsy tokens add spare\n"
    )
    account = await AccountManager.from_file(accounts_file).get("spare")
    assert account is not None
    assert account.tokens[0].dead is None  # the advice came from the verdict, not the store


async def test_verify_without_tokens(run: Runner) -> None:
    code, out, err = await run("tokens", "verify")

    assert code == 0
    assert out == "nothing to verify\n"
    assert err.startswith("hint: create an account")
