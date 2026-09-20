"""Injectable side effects of the command line: clock, prompts, streams, environment, HTTP."""

from __future__ import annotations

import getpass as _getpass
import os
import sys
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from bacsy.cli._errors import CliError
from bacsy.config import ClientConfig
from bacsy.http import new_http_pool

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from datetime import tzinfo
    from typing import TextIO

    import httpx


def _default_confirm(prompt: str) -> bool:
    """Ask `prompt` on stderr and return whether the answer was yes.

    Raises `CliError` when stdin is not a terminal.
    """
    if not sys.stdin.isatty():
        msg = "refusing to ask for confirmation without a terminal"
        raise CliError(msg, hint="pass --yes to skip the prompt")
    sys.stderr.write(f"{prompt} [y/N] ")
    sys.stderr.flush()
    return sys.stdin.readline().strip().lower() in {"y", "yes"}


def _default_http_client() -> httpx.AsyncClient:
    return new_http_pool(ClientConfig())


@dataclass(frozen=True, slots=True, kw_only=True)
class CliDeps:
    """Side effects the commands use, replaceable in tests.

    `None` for a stream or the environment means the process's own, looked up when
    used, not when this object is built.
    """

    clock: Callable[[], float] = time.time
    tz: tzinfo | None = None
    """Time zone for displayed times; `None` means the local zone."""
    getpass: Callable[[str], str] = _getpass.getpass
    confirm: Callable[[str], bool] = _default_confirm
    stdin: TextIO | None = None
    """Stream read by `--stdin`."""
    stdout: TextIO | None = None
    stderr: TextIO | None = None
    environ: Mapping[str, str] | None = None
    """Environment `NO_COLOR`, `FORCE_COLOR` and the terminal variables are read from."""
    http_client_factory: Callable[[], httpx.AsyncClient] = _default_http_client

    def read_stdin(self) -> str:
        stream = sys.stdin if self.stdin is None else self.stdin
        return stream.read()

    @property
    def out(self) -> TextIO:
        return sys.stdout if self.stdout is None else self.stdout

    @property
    def err(self) -> TextIO:
        return sys.stderr if self.stderr is None else self.stderr

    @property
    def env(self) -> Mapping[str, str]:
        return os.environ if self.environ is None else self.environ
