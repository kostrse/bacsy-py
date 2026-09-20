"""Persistence of accounts and their refresh tokens in ``accounts.json``.

The file lives in the state directory. It is machine-managed state and is not meant to
be edited by hand. This module is the only place that knows the file format.

Each token record stores the claims decoded from the token next to the token value, so
loading the file never decodes a JWT. A token is referred to by its ``token_id``; the
``short`` field is a display label and identifies nothing.

```json
{
  "version": 1,
  "accounts": {
    "main": {
      "label": "Main account",
      "tokens": [
        {
          "token": "eyJ...",
          "short": "eyJh**********lCGA",
          "token_id": "00002tst",
          "sid": "...",
          "agreement_id": "...",
          "scope": "trade-api-read",
          "issued_at": 1757000000,
          "expires_at": 1764776000,
          "added_at": 1757000100,
          "dead": null
        }
      ]
    }
  }
}
```

The file is written atomically with owner-only permissions and read on every load.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import TYPE_CHECKING, cast

from bacsy._util.files import FileLock, read_private_text, write_private_text
from bacsy._util.paths import state_dir
from bacsy.accounts.models import Account, TokenRecord, TokenStatus
from bacsy.auth.tokens import RefreshToken, TokenScope
from bacsy.exceptions import AccountError, AccountStoreError

if TYPE_CHECKING:
    from collections.abc import Mapping

ACCOUNTS_FILENAME = "accounts.json"
_FILE_VERSION = 1


def default_accounts_path(env: Mapping[str, str] | None = None) -> Path:
    """Return the path of ``accounts.json`` in the state directory.

    ``env`` is the environment used to locate the state directory, which
    ``BACSY_STATE_DIR`` relocates; it defaults to the process environment.
    """
    return state_dir(env) / ACCOUNTS_FILENAME


def _record_to_dict(record: TokenRecord) -> dict[str, object]:
    token = record.token
    return {
        "token": token.value,
        "short": token.short,
        "token_id": token.token_id,
        "sid": token.sid,
        "agreement_id": token.agreement_id,
        "scope": token.scope.value,
        "issued_at": token.issued_at,
        "expires_at": token.expires_at,
        "added_at": record.added_at,
        "dead": record.dead.to_dict() if record.dead is not None else None,
    }


def _dump_accounts(accounts: Mapping[str, Account]) -> str:
    payload = {
        "version": _FILE_VERSION,
        "accounts": {
            name: {
                "label": account.label,
                "tokens": [_record_to_dict(record) for record in account.tokens],
            }
            for name, account in accounts.items()
        },
    }
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


class _Reader:
    """Reads typed fields from one decoded record; error messages name the record."""

    def __init__(self, data: Mapping[str, object], where: str) -> None:
        self._data: Mapping[str, object] = data
        self._where: str = where

    def fail(self, detail: str) -> AccountStoreError:
        return AccountStoreError(f"{self._where}: {detail}")

    def text(self, key: str, *, optional: bool = False) -> str | None:
        value = self._data.get(key)
        if value is None and optional:
            return None
        if not isinstance(value, str) or not value:
            raise self.fail(f"{key!r} must be a non-empty string")
        return value

    def required_text(self, key: str) -> str:
        value = self.text(key)
        if value is None:  # pragma: no cover - text() only returns None when optional
            raise self.fail(f"{key!r} must be a non-empty string")
        return value

    def timestamp(self, key: str) -> int:
        value = self._data.get(key)
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise self.fail(f"{key!r} must be a Unix timestamp")
        return int(value)


def _record_from_dict(data: Mapping[str, object], where: str) -> TokenRecord:
    reader = _Reader(data, where)
    scope = reader.required_text("scope")
    try:
        token_scope = TokenScope(scope)
    except ValueError as exc:
        raise reader.fail(f"unknown token scope {scope!r}") from exc
    token = RefreshToken(
        value=reader.required_text("token"),
        short=reader.required_text("short"),
        scope=token_scope,
        issued_at=reader.timestamp("issued_at"),
        expires_at=reader.timestamp("expires_at"),
        sid=reader.required_text("sid"),
        agreement_id=reader.required_text("agreement_id"),
        token_id=reader.required_text("token_id"),
    )
    raw_dead = data.get("dead")
    if raw_dead is None:
        dead = None
    elif isinstance(raw_dead, dict):
        try:
            dead = TokenStatus.from_dict(cast("Mapping[str, object]", raw_dead))
        except ValueError as exc:
            raise reader.fail(f"'dead' is malformed: {exc}") from exc
    else:
        raise reader.fail("'dead' must be an object or null")
    return TokenRecord(token=token, added_at=reader.timestamp("added_at"), dead=dead)


def _account_from_dict(name: str, fields: Mapping[str, object], path: Path) -> Account:
    where = f"{path}: account {name!r}"
    label = fields.get("label")
    if label is not None and not isinstance(label, str):
        msg = f"{where}: 'label' must be a string or null"
        raise AccountStoreError(msg)
    raw_tokens = fields.get("tokens", [])
    if not isinstance(raw_tokens, list):
        msg = f"{where}: 'tokens' must be a list"
        raise AccountStoreError(msg)
    records: list[TokenRecord] = []
    for index, entry in enumerate(cast("list[object]", raw_tokens), start=1):
        if not isinstance(entry, dict):
            msg = f"{where}: token {index} must be an object"
            raise AccountStoreError(msg)
        records.append(
            _record_from_dict(cast("Mapping[str, object]", entry), f"{where} token {index}")
        )
    try:
        return Account(name=name, label=label, tokens=tuple(records))
    except AccountError as exc:
        msg = f"{path}: {exc}"
        raise AccountStoreError(msg) from exc


def _load_accounts(text: str, path: Path) -> dict[str, Account]:
    try:
        raw = cast("object", json.loads(text))
    except ValueError as exc:
        msg = f"{path} is not valid JSON: {exc}"
        raise AccountStoreError(msg) from exc
    if not isinstance(raw, dict):
        msg = f"{path}: the accounts file must hold a JSON object"
        raise AccountStoreError(msg)
    document = cast("dict[str, object]", raw)
    version = document.get("version", _FILE_VERSION)
    if version != _FILE_VERSION:
        msg = f"{path}: unsupported accounts file version {version!r}"
        raise AccountStoreError(msg)
    accounts = document.get("accounts", {})
    if not isinstance(accounts, dict):
        msg = f"{path}: 'accounts' must be an object"
        raise AccountStoreError(msg)
    result: dict[str, Account] = {}
    for name, fields in cast("dict[object, object]", accounts).items():
        if not isinstance(name, str) or not isinstance(fields, dict):
            msg = f"{path}: account entries must be objects keyed by name"
            raise AccountStoreError(msg)
        result[name] = _account_from_dict(name, cast("Mapping[str, object]", fields), path)
    return result


class AccountStore:
    """Accounts kept in a JSON file that is re-read on every `load`.

    A file that cannot be parsed raises `AccountStoreError` from `load`. Writes are
    atomic, and a writer holding `locked` around a `load` and the `save` that follows
    is serialised against every other such writer, in this process or another.

    ``path`` defaults to `default_accounts_path`.
    """

    def __init__(self, path: Path | str | None = None) -> None:
        self._path: Path = Path(path).expanduser() if path else default_accounts_path()

    @property
    def path(self) -> Path:
        """The file the store reads and writes."""
        return self._path

    async def load(self) -> dict[str, Account]:
        """Return every account in the file keyed by name; empty when the file is absent.

        Raises:
            AccountStoreError: the file exists but cannot be parsed.
        """
        text = await asyncio.to_thread(read_private_text, self._path)
        return {} if text is None else _load_accounts(text, self._path)

    def locked(self) -> FileLock:
        """Return the lock a writer holds around a `load` followed by a `save`.

        Use as ``async with store.locked():``. Readers need not hold it.
        """
        return FileLock(self._path)

    async def save(self, accounts: Mapping[str, Account]) -> None:
        """Replace the file with ``accounts``, atomically and with owner-only permissions.

        ``accounts`` is the complete set: any account absent from it is dropped.
        """
        await asyncio.to_thread(write_private_text, self._path, _dump_accounts(accounts))
