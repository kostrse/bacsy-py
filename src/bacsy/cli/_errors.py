"""Exit codes and the error type the command line reports as a message and a code."""

from __future__ import annotations

from enum import IntEnum


class ExitCode(IntEnum):
    """Process exit codes of the `bacsy` command."""

    OK = 0
    FAILURE = 1
    """A configuration or runtime failure, a declined confirmation, a network failure."""
    USAGE = 2
    """A usage error, including a command group given without a subcommand."""
    DEAD_TOKENS = 3
    """`tokens verify` found a token the token endpoint rejects."""
    INTERRUPTED = 130
    """The run was interrupted from the keyboard."""


class CliError(Exception):
    """A failure reported as an `error:` line, an optional hint and an exit code."""

    def __init__(
        self,
        message: str,
        *,
        exit_code: ExitCode = ExitCode.FAILURE,
        hint: str | None = None,
    ) -> None:
        super().__init__(message)
        self.exit_code: ExitCode = exit_code
        self.hint: str | None = hint
