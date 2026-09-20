"""Platform directory resolution."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from bacsy._util.paths import state_dir

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="POSIX layout")


def test_state_dir_variable_takes_precedence() -> None:
    """The variable names the state directory itself, on every platform, with no suffix."""
    env = {"BACSY_STATE_DIR": "/srv/bacsy-state", "XDG_STATE_HOME": "/tmp/state"}

    assert state_dir(env) == Path("/srv/bacsy-state")


@posix_only
def test_xdg_variables_take_precedence() -> None:
    assert state_dir({"XDG_STATE_HOME": "/tmp/state"}) == Path("/tmp/state/bacsy")


@posix_only
def test_defaults_under_home() -> None:
    assert state_dir({}) == Path.home() / ".local" / "state" / "bacsy"
