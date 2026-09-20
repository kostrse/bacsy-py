"""Entry point, packaging and error mapping of the command line."""

from __future__ import annotations

import asyncio
import io
import os
import subprocess
import sys
from dataclasses import replace
from importlib.metadata import entry_points
from typing import TYPE_CHECKING

import pytest

import bacsy
from bacsy.cli import CliDeps, ExitCode, main, run_command
from tests.cli.conftest import FakeTty, payload

if TYPE_CHECKING:
    from pathlib import Path

    from tests.cli.conftest import Runner


async def test_help_lists_the_groups(run: Runner, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as info:
        await run("--help")

    assert info.value.code == 0
    out = capsys.readouterr().out
    assert "accounts" in out
    assert "tokens" in out
    # the help names the commands in the order to run them
    assert "Getting started:" in out
    assert "  bacsy accounts add main     create an account" in out
    assert "  bacsy tokens add main       paste an API token issued in the BCS web terminal" in out


async def test_a_bare_command_lists_the_accounts(run: Runner, seeded: dict[str, str]) -> None:
    bare_code, bare_out, bare_err = await run()
    listed_code, listed_out, _ = await run("accounts", "list")

    # the bare command is the listing, not the help
    assert (bare_code, listed_code) == (ExitCode.OK, ExitCode.OK)
    assert bare_out == listed_out
    assert "usage:" not in bare_out
    assert bare_err.endswith("Run `bacsy --help` to see all commands.\n")


async def test_a_bare_group_prints_its_help_and_exits_2(run: Runner) -> None:
    code, out, _ = await run("accounts")
    assert code == ExitCode.USAGE
    assert out.startswith("usage: bacsy accounts")
    assert "rename" in out
    assert "An account starts empty: create one, then add a token to it with" in out

    code, out, _ = await run("tokens")
    assert code == ExitCode.USAGE
    assert "verify" in out
    assert "the account must exist first" in out


async def test_an_unknown_subcommand_exits_2(run: Runner) -> None:
    with pytest.raises(SystemExit) as info:
        await run("accounts", "bogus")

    assert info.value.code == 2


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as info:
        main(["--version"])

    assert info.value.code == 0
    assert bacsy.__version__ in capsys.readouterr().out


def test_console_script_is_registered() -> None:
    (script,) = entry_points(group="console_scripts", name="bacsy")

    assert script.value == "bacsy.cli:main"


def test_cli_is_not_imported_by_the_library() -> None:
    code = "import sys, bacsy; sys.exit('bacsy.cli' in sys.modules)"
    result = subprocess.run([sys.executable, "-c", code], check=False)

    assert result.returncode == 0
    assert "cli" not in bacsy.__all__


async def test_state_dir_variable_locates_the_accounts_file(
    run: Runner, accounts_file: Path
) -> None:
    code, out, _ = await run("accounts", "add", "main")

    assert code == 0
    assert await asyncio.to_thread(accounts_file.exists)
    assert str(accounts_file.parent) not in out  # never shown, only used


@pytest.fixture
def broken_accounts_file(accounts_file: Path) -> Path:
    """A directory where the accounts file belongs, so reading it raises ``OSError``."""
    accounts_file.mkdir(mode=0o700)
    return accounts_file


async def test_os_errors_become_exit_1(run: Runner, broken_accounts_file: Path) -> None:
    code, out, err = await run("accounts", "list")

    assert code == 1
    assert out == ""
    assert err.startswith("error:")
    assert str(broken_accounts_file) in err


def test_default_deps_are_usable() -> None:
    deps = CliDeps()

    assert deps.tz is None
    assert deps.stdin is None
    assert deps.out is sys.stdout
    assert deps.err is sys.stderr
    assert deps.env is os.environ


async def test_json_is_accepted_before_and_after_the_command(run: Runner) -> None:
    _, before, _ = await run("--json", "accounts", "list")
    _, after, _ = await run("accounts", "list", "--json")

    assert payload(before) == payload(after)
    assert "accounts" in payload(before)


async def test_color_follows_the_flag_and_the_terminal(
    deps: CliDeps, seeded: dict[str, str]
) -> None:
    async def output(*argv: str, stdout: io.StringIO, environ: dict[str, str]) -> str:
        code = await run_command(list(argv), deps=replace(deps, stdout=stdout, environ=environ))
        assert code == 0
        return stdout.getvalue()

    assert "\x1b[" not in await output("accounts", "list", stdout=io.StringIO(), environ={})
    assert "\x1b[" in await output(
        "accounts", "list", "--color", "always", stdout=io.StringIO(), environ={}
    )
    assert "\x1b[" in await output(
        "accounts", "list", stdout=FakeTty(), environ={"WT_SESSION": "x"}
    )
    assert "\x1b[" not in await output(
        "accounts", "list", stdout=FakeTty(), environ={"NO_COLOR": "1"}
    )
    assert "\x1b[" not in await output(
        "accounts", "list", "--color", "never", stdout=FakeTty(), environ={}
    )
    assert "\x1b[" not in await output(
        "accounts", "list", "--json", "--color", "always", stdout=FakeTty(), environ={}
    )


def test_keyboard_interrupt_exits_130(deps: CliDeps) -> None:
    def interrupted() -> float:
        raise KeyboardInterrupt

    assert main(["accounts", "list"], deps=replace(deps, clock=interrupted)) == 130
