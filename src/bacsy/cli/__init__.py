"""The `bacsy` command line: account and token management.

Installed as the `bacsy` console script. It depends on `bacsy` and the standard
library only, and nothing in the library imports it. Results go to stdout and
diagnostics (`error:`, `warning:`, `hint:` and `note:` lines) to stderr; prompts are
never written to stdout. `--json` replaces the text on stdout with one JSON document.
Exit codes: 0 on success, 1 on a configuration or runtime failure, 2 on a usage error,
3 when `tokens verify` found tokens the token endpoint rejects, and 130 when the run
was interrupted from the keyboard.
"""

from __future__ import annotations

from bacsy.cli._app import main, run_command
from bacsy.cli._deps import CliDeps
from bacsy.cli._errors import CliError, ExitCode

__all__ = ["CliDeps", "CliError", "ExitCode", "main", "run_command"]
