"""The rule an account name must follow.

`validate_account_name` checks a name against the rule and returns its normalised form;
`ACCOUNT_NAME_RULE` states the rule in one line for error messages and help text.
"""

from __future__ import annotations

import unicodedata

ACCOUNT_NAME_RULE = "letters, digits and _ - . /, starting with a letter, digit or _"
"""One-line statement of the account name rule, used in error messages and help text."""

MAX_ACCOUNT_NAME_LENGTH = 64
"""The longest account name accepted, in code points."""

_NAME_SYMBOLS = frozenset("_-./")
_NAME_START_CATEGORIES = frozenset({"Lu", "Ll", "Lt", "Lm", "Lo", "Nl", "Nd"})
_NAME_CATEGORIES = _NAME_START_CATEGORIES | {"Mn", "Mc"}


def _describe(char: str) -> str:
    return f"{char!r} ({unicodedata.name(char, f'U+{ord(char):04X}')})"


def validate_account_name(name: str) -> str:
    """Return ``name`` in NFC form, or raise when it is not a valid account name.

    A name is a Unicode identifier in the sense of UAX #31, extended to allow a leading
    digit and the symbols ``_ - . /``: it starts with a Unicode letter, a decimal digit
    or ``_``, continues with letters, digits, combining marks or those symbols, and is
    at most `MAX_ACCOUNT_NAME_LENGTH` code points long. Whitespace, control and format
    characters, zero-width joiners included, are rejected. Case is significant;
    visually confusable names are not detected.

    Raises:
        ValueError: ``name`` breaks the rule; the message names the offending
            character.
    """
    name = unicodedata.normalize("NFC", name)
    if not name:
        msg = f"account name is empty; names are {ACCOUNT_NAME_RULE}"
        raise ValueError(msg)
    if len(name) > MAX_ACCOUNT_NAME_LENGTH:
        msg = (
            f"account name is longer than {MAX_ACCOUNT_NAME_LENGTH} characters; "
            f"names are {ACCOUNT_NAME_RULE}"
        )
        raise ValueError(msg)
    for position, char in enumerate(name, start=1):
        category = unicodedata.category(char)
        if position == 1:
            allowed = category in _NAME_START_CATEGORIES or char == "_"
            problem = f"may not start with {_describe(char)}"
        else:
            allowed = category in _NAME_CATEGORIES or char in _NAME_SYMBOLS
            problem = f"contains {_describe(char)} at position {position}"
        if not allowed:
            msg = f"account name {name!r} {problem}; names are {ACCOUNT_NAME_RULE}"
            raise ValueError(msg)
    return name
