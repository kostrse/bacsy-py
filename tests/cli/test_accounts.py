"""The ``bacsy accounts`` commands."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast

from bacsy.accounts import AccountManager
from bacsy.auth import RefreshToken
from bacsy.cli.accounts import HELP_REMINDER, ListAccounts
from bacsy.exceptions import TokenRefreshReason
from tests.auth.fakes import DAY
from tests.cli.conftest import cells, headings, is_rule, mark_dead, payload, rows

if TYPE_CHECKING:
    import io
    from pathlib import Path

    from bacsy.cli._command import Context
    from bacsy.cli._console import Console
    from tests.cli.conftest import Clock, Prompts, Runner, TokenFactory


async def test_list_empty_store(run: Runner) -> None:
    code, out, err = await run("accounts", "list")

    assert code == 0
    assert out == "no accounts saved\n"
    assert err.startswith("hint: create an account")
    assert "bacsy accounts add main" in err
    assert "bacsy tokens add main" in err


async def test_list_table_never_shows_full_tokens(
    run: Runner, seeded: dict[str, str], clock: Clock
) -> None:
    await mark_dead(seeded["spare-read"], TokenRefreshReason.REVOKED, clock.now)

    code, out, err = await run("accounts", "list")

    assert code == 0
    header, rule, *lines = out.splitlines()
    assert is_rule(rule)
    assert cells(header) == ["TOKEN", "ID", "SCOPE", "VALID", "UNTIL", "DAYS", "STATUS"]
    assert lines[0] == "main \u00b7 Main account"  # the label is named once, in the heading
    assert headings(out) == ["main", "spare"]

    main_read, main_write, spare_read = rows(out)
    assert [main_read[1], main_write[1]] == ["00001tst", "00002tst"]  # read before write
    assert main_write[-2:] == ["80", "ok"]
    assert spare_read[-1] == "revoked"
    assert err == (
        "warning: account 'spare' has no usable token\n"
        "         issue an API token in the BCS web terminal and run: "
        "bacsy tokens add spare\n"
    )
    for value in seeded.values():
        assert value not in out
        assert RefreshToken.parse(value).agreement_id not in out


async def test_list_asks_for_a_fresh_token_before_asking_to_prune(
    run: Runner, accounts_file: Path, token: TokenFactory
) -> None:
    manager = AccountManager.from_file(accounts_file)
    await manager.add_token("a", token(days=5))
    await manager.add_token("a", token(days=-1))

    code, out, err = await run("accounts", "list")

    assert code == 0
    assert [row[-1] for row in rows(out)] == ["expired", "expiring"]
    assert err == (
        "warning: every token of account 'a' expires within 7 days\n"
        "         issue a new one in the web terminal and run: bacsy tokens add a\n"
    )  # the dead token is real but not the next thing to do about this account


async def test_list_right_aligns_days(
    run: Runner, accounts_file: Path, token: TokenFactory
) -> None:
    manager = AccountManager.from_file(accounts_file)
    await manager.add_token("a", token(days=5))
    await manager.add_token("a", token(days=100))

    _, out, _ = await run("accounts", "list")

    header, _rule, _heading, first, second = out.splitlines()
    column = header.index("DAYS")
    assert first[column : column + 4] == "   5"  # nearest expiry first
    assert second[column : column + 4] == " 100"


async def test_list_shows_empty_accounts_in_place(
    run: Runner, accounts_file: Path, token: TokenFactory
) -> None:
    manager = AccountManager.from_file(accounts_file)
    await manager.create("empty", label="Nothing yet")
    await manager.add_token("full", token())

    code, out, err = await run("accounts", "list")

    assert code == 0
    assert headings(out) == ["empty", "full"]
    assert "empty \u00b7 Nothing yet\n  (no tokens)" in out
    assert len(rows(out)) == 1  # only the account that has one
    assert err == "hint: account 'empty' holds no tokens yet; run: bacsy tokens add empty\n"


async def test_list_sorts_accounts_and_keeps_their_tokens_together(
    run: Runner, accounts_file: Path, token: TokenFactory
) -> None:
    manager = AccountManager.from_file(accounts_file)
    await manager.add_token("zeta", token(days=10))
    await manager.add_token("Alpha", token(days=20))
    await manager.add_token("zeta", token(days=30))
    await manager.add_token("beta", token(days=40))

    _, out, _ = await run("accounts", "list")

    assert headings(out) == ["Alpha", "beta", "zeta"]
    assert len(rows(out)) == 4  # zeta's two tokens sit together under its one heading


async def test_list_json(run: Runner, seeded: dict[str, str], accounts_file: Path) -> None:
    code, out, _ = await run("accounts", "list", "--json")

    assert code == 0
    document = payload(out)
    assert set(document) == {"accounts"}  # where the accounts are stored is not a contract
    assert str(accounts_file) not in out
    accounts = cast("list[dict[str, object]]", document["accounts"])
    main = next(a for a in accounts if a["name"] == "main")
    tokens = cast("list[dict[str, object]]", main["tokens"])
    assert main["agreement_id"] == RefreshToken.parse(seeded["main-read"]).agreement_id
    assert [t["scope"] for t in tokens] == ["read", "write"]  # read before write
    assert all(str(t["expires_at"]).endswith("+00:00") for t in tokens)
    assert all(str(t["added_at"]).endswith("+00:00") for t in tokens)
    assert all(t["status"] == "ok" for t in tokens)
    assert "dead" not in tokens[0]  # `status` says it; the mark itself is internal
    for value in seeded.values():
        assert value not in out


async def test_list_json_reports_a_dead_mark_as_a_status(
    run: Runner, seeded: dict[str, str], clock: Clock
) -> None:
    await mark_dead(seeded["spare-read"], TokenRefreshReason.REVOKED, clock.now)

    _, out, _ = await run("--json", "accounts", "list")

    accounts = cast("list[dict[str, object]]", payload(out)["accounts"])
    spare = next(a for a in accounts if a["name"] == "spare")
    (record,) = cast("list[dict[str, object]]", spare["tokens"])
    assert record["status"] == "revoked"
    assert "dead" not in record  # how the rejection is stored is not part of the document


async def test_list_runs_directly_against_a_context(
    ctx: Context, console: Console, seeded: dict[str, str]
) -> None:
    code = await ListAccounts().run(ctx)

    assert code == 0
    assert cast("io.StringIO", console.out).getvalue().startswith("  TOKEN")


async def test_only_the_default_screen_reminds_how_to_reach_the_help(
    run: Runner, seeded: dict[str, str]
) -> None:
    _, _, bare = await run()
    _, _, listed = await run("accounts", "list")

    assert bare == f"{HELP_REMINDER}\n"  # a healthy store draws no advice
    assert HELP_REMINDER not in listed  # whoever typed it already knows the commands


async def test_the_default_screen_reminds_an_empty_store_too(run: Runner) -> None:
    code, out, err = await run()

    assert code == 0
    assert out == "no accounts saved\n"
    assert err.startswith("hint: create an account")
    assert err.splitlines()[-1] == HELP_REMINDER


async def test_the_help_reminder_is_text_only(run: Runner, seeded: dict[str, str]) -> None:
    code, out, err = await run("--json")

    assert code == 0
    assert set(payload(out)) == {"accounts"}
    assert HELP_REMINDER not in err


async def test_add_creates_an_empty_account(run: Runner, accounts_file: Path) -> None:
    code, out, err = await run("accounts", "add", "main", "--label", "Main account")

    assert code == 0
    assert out == "created account 'main'\n"
    assert err == "hint: add a token with: bacsy tokens add main\n"
    account = await AccountManager.from_file(accounts_file).get("main")
    assert account is not None
    assert account.label == "Main account"
    assert account.tokens == ()


async def test_add_accepts_an_identifier_like_name(run: Runner, accounts_file: Path) -> None:
    code, out, err = await run("accounts", "add", "3412345/25-иис")

    assert code == 0
    assert out == "created account '3412345/25-иис'\n"
    assert err == "hint: add a token with: bacsy tokens add 3412345/25-иис\n"
    assert await AccountManager.from_file(accounts_file).get("3412345/25-иис") is not None


async def test_add_refuses_a_name_that_is_not_an_identifier(
    run: Runner, accounts_file: Path
) -> None:
    code, out, err = await run("accounts", "add", "my acct")

    assert code == 1
    assert out == ""
    assert err == (
        "error: account name 'my acct' contains ' ' (SPACE) at position 3; "
        "names are letters, digits and _ - . /, starting with a letter, digit or _\n"
    )
    assert await AccountManager.from_file(accounts_file).list_accounts() == []


async def test_add_refuses_an_existing_account(run: Runner, seeded: dict[str, str]) -> None:
    code, out, err = await run("accounts", "add", "main")

    assert code == 1
    assert out == ""
    assert err.startswith("error: an account named 'main' already exists\n")
    assert "hint:" in err


async def test_add_json(run: Runner) -> None:
    code, out, _ = await run("accounts", "add", "main", "--json")

    assert code == 0
    assert payload(out) == {
        "account": {"name": "main", "label": None, "agreement_id": None, "tokens": []}
    }


async def test_remove_whole_account_with_confirmation(
    run: Runner, seeded: dict[str, str], prompts: Prompts, accounts_file: Path
) -> None:
    prompts.answers.append(False)
    code, out, err = await run("accounts", "remove", "main")
    assert code == 1
    assert out == ""
    assert err == "aborted\n"
    assert await AccountManager.from_file(accounts_file).get("main") is not None

    prompts.answers.append(True)
    code, out, err = await run("accounts", "remove", "main")
    assert code == 0
    assert out == "removed account 'main' and its 2 tokens\n"
    assert prompts.asked[-1] == "remove account 'main' and its 2 tokens?"
    assert err.startswith("note: removing tokens here does not revoke them")
    assert await AccountManager.from_file(accounts_file).get("main") is None


async def test_remove_with_yes_skips_confirmation(
    run: Runner, seeded: dict[str, str], prompts: Prompts
) -> None:
    code, _, _ = await run("accounts", "remove", "spare", "-y")

    assert code == 0
    assert prompts.asked == []


async def test_remove_an_empty_account_needs_no_revoke_note(
    run: Runner, accounts_file: Path, prompts: Prompts
) -> None:
    await AccountManager.from_file(accounts_file).create("empty")
    prompts.answers.append(True)

    code, out, err = await run("accounts", "remove", "empty")

    assert code == 0
    assert out == "removed account 'empty'\n"
    assert prompts.asked == ["remove account 'empty'?"]
    assert err == ""


async def test_remove_unknown_account_lists_the_saved_ones(
    run: Runner, seeded: dict[str, str]
) -> None:
    code, _, err = await run("accounts", "remove", "ghost", "--yes")

    assert code == 1
    assert err == "error: no account named 'ghost'\nhint: saved accounts: main, spare\n"


async def test_remove_json(run: Runner, seeded: dict[str, str]) -> None:
    code, out, _ = await run("accounts", "remove", "spare", "--yes", "--json")

    assert code == 0
    account = cast("dict[str, object]", payload(out)["account"])
    assert account["name"] == "spare"
    assert len(cast("list[object]", account["tokens"])) == 1


async def test_rename(run: Runner, seeded: dict[str, str], accounts_file: Path) -> None:
    code, out, _ = await run("accounts", "rename", "main", "primary")

    assert code == 0
    assert out == "renamed account 'main' to 'primary'\n"
    assert await AccountManager.from_file(accounts_file).get("primary") is not None

    code, _, err = await run("accounts", "rename", "main", "x")
    assert code == 1
    assert "no account named 'main'" in err
    code, _, err = await run("accounts", "rename", "spare", "primary")
    assert code == 1
    assert "already exists" in err


async def test_rename_refuses_a_name_that_is_not_an_identifier(
    run: Runner, seeded: dict[str, str], accounts_file: Path
) -> None:
    # "--" keeps argparse from reading "-x" as an option, so the validator sees it.
    code, out, err = await run("accounts", "rename", "main", "--", "-x")

    assert code == 1
    assert out == ""
    assert err == (
        "error: account name '-x' may not start with '-' (HYPHEN-MINUS); "
        "names are letters, digits and _ - . /, starting with a letter, digit or _\n"
    )
    assert await AccountManager.from_file(accounts_file).get("main") is not None


async def test_rename_json(run: Runner, seeded: dict[str, str]) -> None:
    code, out, _ = await run("accounts", "rename", "spare", "iis", "--json")

    assert code == 0
    document = payload(out)
    assert document["previous_name"] == "spare"
    assert cast("dict[str, object]", document["account"])["name"] == "iis"


async def test_time_is_rendered_in_the_configured_zone(
    run: Runner, accounts_file: Path, token: TokenFactory, clock: Clock
) -> None:
    await AccountManager.from_file(accounts_file).add_token("a", token(days=1))

    _, out, _ = await run("accounts", "list")

    expected = datetime.fromtimestamp(clock.now + DAY, tz=UTC).strftime("%Y-%m-%d %H:%M:%S")
    assert expected in out
