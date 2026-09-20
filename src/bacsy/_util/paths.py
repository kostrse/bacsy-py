"""The user-scoped state directory for the current OS.

XDG Base Directory specification on Linux and macOS; `LOCALAPPDATA` on Windows. Paths
are resolved, never created.

`BACSY_STATE_DIR` relocates the directory as a whole. The files inside it are
internal and may change between versions; no environment variable names an individual
file.

This module imports nothing from bacsy.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

APP_NAME = "bacsy"
"""Default name of this library's state directory."""

STATE_DIR_ENV = "BACSY_STATE_DIR"
"""Environment variable naming the state directory; used verbatim on every platform."""


def state_dir(env: Mapping[str, str] | None = None) -> Path:
    r"""Return the user-scoped state directory.

    `BACSY_STATE_DIR` when set, used as given without the application name appended;
    otherwise `$XDG_STATE_HOME/bacsy`, else `~/.local/state/bacsy`; on Windows
    `%LOCALAPPDATA%\bacsy`, else `~\AppData\Local\bacsy`. `env` defaults to
    `os.environ`.
    """
    env = os.environ if env is None else env
    override = env.get(STATE_DIR_ENV)
    if override:
        return Path(override).expanduser()
    if sys.platform == "win32":
        base = env.get("LOCALAPPDATA")
        return Path(base) / APP_NAME if base else Path.home() / "AppData" / "Local" / APP_NAME
    base = env.get("XDG_STATE_HOME")
    return Path(base) / APP_NAME if base else Path.home() / ".local" / "state" / APP_NAME
