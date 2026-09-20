"""The installed distribution's version, read once at import."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _version

try:
    __version__ = _version("bacsy")
except PackageNotFoundError:  # pragma: no cover - only hit when running from a source tree
    __version__ = "0.0.0.dev0"
