"""Package-level metadata checks."""

from __future__ import annotations

import bacsy


def test_version_is_exposed() -> None:
    assert isinstance(bacsy.__version__, str)
    assert bacsy.__version__


def test_all_exports_resolve() -> None:
    for name in bacsy.__all__:
        assert hasattr(bacsy, name), f"{name} listed in __all__ but not importable"


def test_package_is_typed() -> None:
    from importlib.resources import files

    assert (files("bacsy") / "py.typed").is_file()
