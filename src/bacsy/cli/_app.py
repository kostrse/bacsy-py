"""Entry points: parse the arguments, run the command and map failures to exit codes."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from bacsy.accounts import AccountManager
from bacsy.cli._command import Command, Context
from bacsy.cli._console import Console, color_enabled
from bacsy.cli._deps import CliDeps
from bacsy.cli._errors import CliError, ExitCode
from bacsy.cli._parser import build_parser
from bacsy.exceptions import BacsyError

if TYPE_CHECKING:
    import argparse
    from collections.abc import Sequence

    from bacsy.cli._console import ColorMode


async def run_command(argv: Sequence[str] | None = None, *, deps: CliDeps | None = None) -> int:
    """Parse `argv` and run the selected command in the current event loop."""
    deps = deps or CliDeps()
    args = build_parser().parse_args(argv)
    mode: ColorMode = args.color
    console = Console(
        deps.out,
        deps.err,
        color_out=color_enabled(mode, deps.out, deps.env),
        color_err=color_enabled(mode, deps.err, deps.env),
    )
    command_type: type[Command] | None = args.command
    if command_type is None:
        help_parser: argparse.ArgumentParser = args.help_parser
        help_parser.print_help(file=console.out)
        return ExitCode.USAGE
    ctx = Context(
        manager=AccountManager.from_file(clock=deps.clock),
        deps=deps,
        console=console,
        now=deps.clock(),
        json=bool(args.json),
    )
    try:
        return await command_type.from_namespace(args).run(ctx)
    except CliError as exc:
        console.error(str(exc), hint=exc.hint)
        return exc.exit_code
    except (BacsyError, OSError) as exc:
        console.error(str(exc))
        return ExitCode.FAILURE
    finally:
        if not ctx.json:
            console.finish()


def main(argv: Sequence[str] | None = None, *, deps: CliDeps | None = None) -> int:
    """Console-script entry point: run the command line and return its exit code."""
    try:
        return asyncio.run(run_command(argv, deps=deps))
    except KeyboardInterrupt:
        return ExitCode.INTERRUPTED
