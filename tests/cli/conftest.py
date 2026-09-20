"""Fixtures driving the command line in-process with every side effect injected."""

from __future__ import annotations

import io
import json
from dataclasses import dataclass, field
from datetime import UTC
from typing import TYPE_CHECKING, Protocol, cast, override

import httpx
import pytest

from bacsy.accounts import AccountManager
from bacsy.auth import RefreshToken, TokenScope
from bacsy.cli import CliDeps, run_command
from bacsy.cli._command import Context
from bacsy.cli._console import Console
from bacsy.cli._format import ASCII_RULE, BOX_RULE
from bacsy.cli._views import NO_TOKENS
from tests.auth.fakes import AGREEMENT, DAY, Keycloak, make_refresh_token

if TYPE_CHECKING:
    from pathlib import Path

    from bacsy.exceptions import TokenRefreshReason

NOW = 1_800_000_000
OTHER_AGREEMENT = "00000000-0000-4000-8000-000000000002"


RULE_CHARS = frozenset((ASCII_RULE, BOX_RULE))


def is_rule(line: str) -> bool:
    """Whether ``line`` is the rule under a table's header."""
    return bool(line) and set(line) <= RULE_CHARS


def cells(line: str) -> list[str]:
    """The whitespace-separated words of a table line."""
    return line.split()


def rows(out: str) -> list[list[str]]:
    """The cells of every token row, the column header and the headings skipped."""
    header, body = _table(out)
    grouped = header.startswith(" ")
    return [
        cells(line)
        for line in body
        if line.strip() and line.strip() != NO_TOKENS and (line.startswith("  ") or not grouped)
    ]


def headings(out: str) -> list[str]:
    """The account heading lines of a grouped table, without their labels."""
    header, body = _table(out)
    if not header.startswith(" "):
        return []  # an ungrouped table has no headings
    return [line.split(" \u00b7 ")[0] for line in body if line and not line.startswith(" ")]


def _table(out: str) -> tuple[str, list[str]]:
    """The column header of the first table and the lines below its rule."""
    lines = out.splitlines()
    index = next(i for i, line in enumerate(lines) if is_rule(line))
    return lines[index - 1], lines[index + 1 :]


def payload(out: str) -> dict[str, object]:
    """The one JSON document a ``--json`` run wrote."""
    return cast("dict[str, object]", json.loads(out))


async def mark_dead(value: str, reason: TokenRefreshReason, at: float) -> None:
    """Record a rejection against a stored token, as a failed refresh would."""
    await AccountManager.from_file().mark_dead(RefreshToken.parse(value), reason, now=at)


class FakeTty(io.StringIO):
    """A text stream that claims to be a terminal, for colour tests."""

    @override
    def isatty(self) -> bool:
        return True


@dataclass
class Prompts:
    """Scripted answers for getpass and confirmation prompts."""

    secrets: list[str] = field(default_factory=list)
    answers: list[bool] = field(default_factory=list)
    asked: list[str] = field(default_factory=list)

    def getpass(self, prompt: str) -> str:
        self.asked.append(prompt)
        return self.secrets.pop(0)

    def confirm(self, prompt: str) -> bool:
        self.asked.append(prompt)
        return self.answers.pop(0)


@dataclass
class Clock:
    now: float = NOW

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def prompts() -> Prompts:
    return Prompts()


@pytest.fixture
def keycloak(clock: Clock) -> Keycloak:
    return Keycloak(clock=clock)


@pytest.fixture
def deps(clock: Clock, prompts: Prompts, keycloak: Keycloak) -> CliDeps:
    return CliDeps(
        clock=clock,
        tz=UTC,
        getpass=prompts.getpass,
        confirm=prompts.confirm,
        stdin=io.StringIO(),
        environ={},
        http_client_factory=lambda: httpx.AsyncClient(
            transport=httpx.MockTransport(keycloak.async_handler), base_url="https://be.broker.ru"
        ),
    )


class Runner(Protocol):
    async def __call__(self, *argv: str, stdin: str = "") -> tuple[int, str, str]: ...


@pytest.fixture
def run(deps: CliDeps, capsys: pytest.CaptureFixture[str]) -> Runner:
    """Run ``bacsy`` with ``argv`` and return ``(exit code, stdout, stderr)``."""

    async def runner(*argv: str, stdin: str = "") -> tuple[int, str, str]:
        assert deps.stdin is not None
        deps.stdin.seek(0)
        deps.stdin.truncate()
        deps.stdin.write(stdin)
        deps.stdin.seek(0)
        capsys.readouterr()
        code = await run_command(list(argv), deps=deps)
        out, err = capsys.readouterr()
        return code, out, err

    return runner


@pytest.fixture
def accounts_file(tmp_path: Path) -> Path:
    """The accounts file inside the state directory the autouse fixture isolates."""
    return tmp_path / "accounts.json"


@pytest.fixture
def console() -> Console:
    """A colourless console over two in-memory streams, for running commands directly."""
    return Console(io.StringIO(), io.StringIO(), color_out=False, color_err=False)


@pytest.fixture
def ctx(deps: CliDeps, console: Console, clock: Clock) -> Context:
    return Context(
        manager=AccountManager.from_file(clock=clock),
        deps=deps,
        console=console,
        now=clock.now,
        json=False,
    )


class TokenFactory(Protocol):
    def __call__(
        self,
        scope: TokenScope = ...,
        *,
        days: int = ...,
        sid: str | None = ...,
        token_id: str | None = ...,
        agreement_id: str | None = ...,
    ) -> str: ...


@pytest.fixture
def token(clock: Clock) -> TokenFactory:
    def make(
        scope: TokenScope = TokenScope.READ,
        *,
        days: int = 60,
        sid: str | None = None,
        token_id: str | None = None,
        agreement_id: str | None = None,
    ) -> str:
        return make_refresh_token(
            scope=scope,
            exp=NOW + days * DAY,
            sid=sid,
            token_id=token_id,
            agreement_id=AGREEMENT if agreement_id is None else agreement_id,
        )

    return make


@pytest.fixture
async def seeded(accounts_file: Path, token: TokenFactory) -> dict[str, str]:
    """Two accounts: ``main`` with a read and a write token, ``spare`` with one read token."""
    manager = AccountManager.from_file(accounts_file)
    values = {
        "main-read": token(sid="main-read", token_id="00001tst"),
        "main-write": token(TokenScope.WRITE, days=80, sid="main-write", token_id="00002tst"),
        "spare-read": token(sid="spare-read", agreement_id=OTHER_AGREEMENT),
    }
    await manager.create("main", label="Main account")
    await manager.add_token("main", values["main-read"])
    await manager.add_token("main", values["main-write"])
    await manager.create("spare")
    await manager.add_token("spare", values["spare-read"])
    return values
