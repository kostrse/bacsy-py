"""The accounts file: parsing, serialization, permissions and path resolution."""

from __future__ import annotations

import json
import stat
import sys
from typing import TYPE_CHECKING

import pytest

from bacsy.accounts import (
    Account,
    AccountManager,
    AccountStore,
    TokenStatus,
    default_accounts_path,
)
from bacsy.auth import RefreshToken, TokenScope, default_token_cache_path
from bacsy.exceptions import AccountStoreError, TokenRefreshReason
from tests.accounts.fakes import NOW, make_record, make_token
from tests.auth.fakes import DAY, OTHER_AGREEMENT

if TYPE_CHECKING:
    from pathlib import Path


def _write(path: Path, document: object) -> None:
    path.write_text(json.dumps(document))


def test_default_paths_are_isolated(tmp_path: Path) -> None:
    """The autouse fixture must keep every test away from real credential files."""
    assert default_accounts_path().parent == tmp_path
    assert default_token_cache_path().parent == tmp_path


def test_default_path_follows_the_state_directory(tmp_path: Path) -> None:
    env = {"BACSY_STATE_DIR": str(tmp_path)}

    assert default_accounts_path(env) == tmp_path / "accounts.json"


def test_default_path_lives_in_the_state_directory() -> None:
    env = {"XDG_STATE_HOME": "/tmp/state", "LOCALAPPDATA": "C:\\state"}

    assert default_accounts_path(env).parent.name == "bacsy"
    assert default_accounts_path(env).name == "accounts.json"


async def test_missing_file_loads_as_no_accounts(tmp_path: Path) -> None:
    assert await AccountStore(tmp_path / "absent.json").load() == {}


async def test_a_record_round_trips_with_all_its_fields(tmp_path: Path) -> None:
    path = tmp_path / "accounts.json"
    store = AccountStore(path)
    token = make_token(scope=TokenScope.WRITE, exp=NOW + DAY, token_id="00002tst")
    dead = TokenStatus(reason=TokenRefreshReason.REVOKED, at=NOW)
    record = make_record(token, added_at=NOW - 5, dead=dead)

    await store.save({"my acct": Account(name="my acct", label="Main", tokens=(record,))})
    reloaded = (await store.load())["my acct"]

    assert reloaded.name == "my acct"
    assert reloaded.label == "Main"
    assert reloaded.tokens == (record,)


async def test_the_stored_claims_are_used_rather_than_the_token(tmp_path: Path) -> None:
    """A record whose stored value is opaque still loads in full from the stored claims."""
    path = tmp_path / "accounts.json"
    record = make_record()
    await AccountStore(path).save({"main": Account(name="main", tokens=(record,))})
    document = json.loads(path.read_text())
    document["accounts"]["main"]["tokens"][0]["token"] = "opaque-ciphertext"
    _write(path, document)

    reloaded = (await AccountStore(path).load())["main"].tokens[0]

    assert reloaded.token.value == "opaque-ciphertext"
    assert reloaded.token.short == record.token.short
    assert reloaded.token.token_id == record.token.token_id
    assert reloaded.token.expires_at == record.token.expires_at
    assert reloaded.token.sid == record.token.sid


async def test_optional_fields_are_written_as_null(tmp_path: Path) -> None:
    path = tmp_path / "accounts.json"
    record = make_record(make_token(token_id=None))
    await AccountStore(path).save({"main": Account(name="main", tokens=(record,))})

    stored = json.loads(path.read_text())["accounts"]["main"]

    assert stored["label"] is None
    assert stored["tokens"][0]["token_id"] == record.token.token_id
    assert stored["tokens"][0]["dead"] is None


async def test_the_file_uses_the_agreed_keys(tmp_path: Path) -> None:
    path = tmp_path / "accounts.json"
    record = make_record(make_token(token_id="00002tst"))
    await AccountStore(path).save({"main": Account(name="main", tokens=(record,))})

    stored = json.loads(path.read_text())

    assert stored["version"] == 1
    assert set(stored["accounts"]["main"]) == {"label", "tokens"}
    assert set(stored["accounts"]["main"]["tokens"][0]) == {
        "token",
        "short",
        "token_id",
        "sid",
        "agreement_id",
        "scope",
        "issued_at",
        "expires_at",
        "added_at",
        "dead",
    }
    assert stored["accounts"]["main"]["tokens"][0]["token"] == record.token.value
    assert stored["accounts"]["main"]["tokens"][0]["sid"] == record.token.sid


async def test_the_short_form_is_written_for_readers_without_the_value(tmp_path: Path) -> None:
    path = tmp_path / "accounts.json"
    record = make_record()
    await AccountStore(path).save({"main": Account(name="main", tokens=(record,))})

    stored = json.loads(path.read_text())["accounts"]["main"]["tokens"][0]

    assert stored["short"] == record.token.short
    assert stored["issued_at"] == record.token.issued_at
    assert isinstance(stored["expires_at"], int)


async def test_an_account_without_tokens_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "accounts.json"
    await AccountStore(path).save({"empty": Account(name="empty", label="x")})

    assert (await AccountStore(path).load())["empty"].tokens == ()


async def test_names_and_labels_survive_quoting(tmp_path: Path) -> None:
    path = tmp_path / "accounts.json"
    manager = AccountManager.from_file(path)
    await manager.add_token("3412345/25-иис", make_token().value, label='Main "acct"')

    reloaded = (await AccountStore(path).load())["3412345/25-иис"]

    assert reloaded.label == 'Main "acct"'
    assert reloaded.name == "3412345/25-иис"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions")
async def test_writes_are_owner_only(tmp_path: Path) -> None:
    path = tmp_path / "state" / "accounts.json"
    await AccountManager.from_file(path).add_token("main", make_token().value)

    lock_file = path.with_name("accounts.json.lock")
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(lock_file.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert sorted(path.parent.iterdir()) == [path, lock_file]


async def test_locked_is_the_lock_beside_the_file(tmp_path: Path) -> None:
    store = AccountStore(tmp_path / "accounts.json")

    async with store.locked():
        assert (tmp_path / "accounts.json.lock").exists()


def _entry(parsed: RefreshToken | None = None, **overrides: object) -> dict[str, object]:
    """One serialized record, with fields replaced to make a malformed one."""
    token = parsed if parsed is not None else make_token()
    entry: dict[str, object] = {
        "token": token.value,
        "short": token.short,
        "token_id": token.token_id,
        "sid": token.sid,
        "agreement_id": token.agreement_id,
        "scope": token.scope.value,
        "issued_at": token.issued_at,
        "expires_at": token.expires_at,
        "added_at": NOW,
        "dead": None,
    }
    entry.update(overrides)
    return entry


def _document(*entries: dict[str, object]) -> dict[str, object]:
    return {"version": 1, "accounts": {"a": {"label": None, "tokens": list(entries)}}}


def _record_document(**overrides: object) -> dict[str, object]:
    return _document(_entry(None, **overrides))


@pytest.mark.parametrize(
    ("document", "message"),
    [
        ({"version": 2}, "unsupported accounts file version"),
        ({"version": 1, "accounts": 1}, "'accounts' must be an object"),
        ({"version": 1, "accounts": {"a": 1}}, "must be objects keyed by name"),
        ({"version": 1, "accounts": {"a": {"label": 1}}}, "'label' must be a string or null"),
        ({"version": 1, "accounts": {"a": {"tokens": "x"}}}, "'tokens' must be a list"),
        ({"version": 1, "accounts": {"a": {"tokens": [5]}}}, "token 1 must be an object"),
        (_record_document(token=None), "'token' must be a non-empty string"),
        (_record_document(sid=""), "'sid' must be a non-empty string"),
        (_record_document(token_id=None), "'token_id' must be a non-empty string"),
        (_record_document(short=""), "'short' must be a non-empty string"),
        (
            _document(_entry(token_id="00002tst"), _entry(token_id="00002tst")),
            "tokens 1 and 2 share the token id '00002tst'",
        ),
        (_record_document(scope="trade-api-admin"), "unknown token scope"),
        (_record_document(expires_at="soon"), "'expires_at' must be a Unix timestamp"),
        (_record_document(added_at=None), "'added_at' must be a Unix timestamp"),
        (_record_document(dead=5), "'dead' must be an object or null"),
        (_record_document(dead={"reason": "gone"}), "'dead' is malformed"),
    ],
)
async def test_malformed_files_are_rejected(tmp_path: Path, document: object, message: str) -> None:
    path = tmp_path / "accounts.json"
    _write(path, document)

    with pytest.raises(AccountStoreError, match=message):
        await AccountStore(path).load()


async def test_a_file_that_is_not_json_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "accounts.json"
    path.write_text("not json {")

    with pytest.raises(AccountStoreError, match="is not valid JSON"):
        await AccountStore(path).load()


async def test_a_json_file_that_is_not_an_object_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "accounts.json"
    _write(path, [])

    with pytest.raises(AccountStoreError, match="must hold a JSON object"):
        await AccountStore(path).load()


async def test_a_problem_is_reported_with_the_path_and_the_token_position(tmp_path: Path) -> None:
    path = tmp_path / "accounts.json"
    _write(path, _record_document(scope="trade-api-admin"))

    with pytest.raises(AccountStoreError) as info:
        await AccountStore(path).load()

    message = str(info.value)
    assert str(path) in message
    assert "account 'a' token 1" in message


async def test_tokens_of_different_brokerage_accounts_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "accounts.json"
    other = make_token(agreement_id=OTHER_AGREEMENT, sid="other-session")
    _write(path, _document(_entry(), _entry(other)))

    with pytest.raises(AccountStoreError, match="tokens 1 and 2"):
        await AccountStore(path).load()
