"""Credential management: named accounts and the refresh tokens they hold.

This package is built on `bacsy.auth`; nothing in `bacsy.auth` imports from here.

- `AccountManager`: account lifecycle, dead-token marks, verification against the token
  endpoint, and building an access token provider for one account.
- `AccountStore`: persistence of the accounts in one machine-managed JSON file holding a
  `TokenRecord` per token. The manager receives its store as a constructor argument.
- `validate_account_name`: the rule an account name must follow, applied by the manager
  when an account is created or renamed.
"""

from __future__ import annotations

from bacsy.accounts.manager import AccountManager
from bacsy.accounts.models import Account, TokenRecord, TokenStatus, VerifyResult
from bacsy.accounts.store import ACCOUNTS_FILENAME, AccountStore, default_accounts_path
from bacsy.accounts.validation import (
    ACCOUNT_NAME_RULE,
    MAX_ACCOUNT_NAME_LENGTH,
    validate_account_name,
)

__all__ = [
    "ACCOUNTS_FILENAME",
    "ACCOUNT_NAME_RULE",
    "MAX_ACCOUNT_NAME_LENGTH",
    "Account",
    "AccountManager",
    "AccountStore",
    "TokenRecord",
    "TokenStatus",
    "VerifyResult",
    "default_accounts_path",
    "validate_account_name",
]
