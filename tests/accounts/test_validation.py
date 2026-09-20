"""The account name rule."""

from __future__ import annotations

import pytest

from bacsy.accounts import validate_account_name


@pytest.mark.parametrize(
    "name",
    ["main", "3412345", "3412345/25-иис", "Основной", "_x", "a.b", "ro-2025", "Main", "a" * 64],
)
def test_identifier_like_names_are_accepted_unchanged(name: str) -> None:
    assert validate_account_name(name) == name


def test_names_are_returned_in_nfc_form() -> None:
    decomposed = "и\u0306"  # й as и + combining breve

    assert validate_account_name(decomposed) == "й"
    assert validate_account_name("й") == "й"


@pytest.mark.parametrize(
    ("name", "problem"),
    [
        ("", "is empty"),
        ("my acct", "contains ' ' (SPACE) at position 3"),
        ("a\tb", "contains '\\t' (U+0009) at position 2"),
        ("a\u200bb", "contains '\\u200b' (ZERO WIDTH SPACE) at position 2"),
        ("-x", "may not start with '-' (HYPHEN-MINUS)"),
        (".x", "may not start with '.' (FULL STOP)"),
        ("/x", "may not start with '/' (SOLIDUS)"),
        ("a'b", 'contains "\'" (APOSTROPHE) at position 2'),
        ('"main"', "may not start with '\"' (QUOTATION MARK)"),
        ("a*b", "contains '*' (ASTERISK) at position 2"),
        ("a@b", "contains '@' (COMMERCIAL AT) at position 2"),
        ("a" * 65, "is longer than 64 characters"),
    ],
)
def test_names_that_are_not_identifiers_are_rejected(name: str, problem: str) -> None:
    with pytest.raises(ValueError, match="letters, digits and") as info:
        validate_account_name(name)

    assert problem in str(info.value)
