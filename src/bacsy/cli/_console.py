"""Output streams of the command line: results and JSON to stdout, diagnostics to stderr.

This is the only module of the command line that writes to a stream.
"""

from __future__ import annotations

import json
import sys
from typing import TYPE_CHECKING, Literal

from bacsy.cli._format import (
    ASCII_RULE,
    BOX_RULE,
    Style,
    plain,
    render_sections,
    render_table,
    styled,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from typing import TextIO

    from bacsy.cli._format import Align, Painter, Row, Section

type ColorMode = Literal["auto", "always", "never"]

type Json = dict[str, Json] | list[Json] | str | int | float | bool | None
"""Value types of a command's JSON document."""


def color_enabled(mode: ColorMode, stream: TextIO, environ: Mapping[str, str]) -> bool:
    """Return whether escape sequences should be written to `stream`.

    `always` and `never` are taken as given. Otherwise `NO_COLOR` disables and
    `FORCE_COLOR` enables colour, `TERM=dumb` and a stream that is not a terminal get
    none, and on Windows colour also requires one of `WT_SESSION`, `TERM`, `ANSICON` or
    `ConEmuANSI` to be set.
    """
    if mode == "always":
        return True
    if mode == "never" or environ.get("NO_COLOR"):
        return False
    if environ.get("FORCE_COLOR"):
        return True
    if environ.get("TERM") == "dumb":
        return False
    if sys.platform == "win32" and not any(
        environ.get(name) for name in ("WT_SESSION", "TERM", "ANSICON", "ConEmuANSI")
    ):
        return False
    return stream.isatty()


def table_dash(stream: TextIO) -> str:
    """Return the box-drawing rule when `stream` encodes UTF-8, a plain hyphen otherwise."""
    encoding = getattr(stream, "encoding", None)
    if isinstance(encoding, str) and encoding.lower().replace("-", "") == "utf8":
        return BOX_RULE
    return ASCII_RULE


class Console:
    """The two output streams of a run and the colour policy of each.

    Content written as a block is set apart from the text around it by a blank line;
    tables are always blocks, and a diagnostic is one only when its caller asks. That
    holds within each stream whether or not it is a terminal. When stdout is a terminal
    both streams share one screen, so a block on either stream is also set apart from
    text on the other, and `finish` ends the run with a blank line.
    """

    def __init__(self, out: TextIO, err: TextIO, *, color_out: bool, color_err: bool) -> None:
        self._out: TextIO = out
        self._err: TextIO = err
        self._paint_out: Painter = styled if color_out else plain
        self._paint_err: Painter = styled if color_err else plain
        self._dash: str = table_dash(out)
        self._written: bool = False
        """Whether anything at all has been written, to either stream."""
        self._out_written: bool = False
        self._err_written: bool = False
        self._out_block: bool = False
        """Whether the last thing written to stdout was a block."""

    def _write(self, stream: TextIO, text: str, *, block: bool = False) -> None:
        """Write `text` to `stream`, inserting a blank line where it borders a block.

        A blank line separating content on one stream from content on the other is
        written only when stdout is a terminal. It goes to the stream holding the text
        being separated from, so that each stream stays readable on its own.
        """
        shared = self._out.isatty()
        if stream is self._out:
            if self._out_block or (block and (self._out_written or (shared and self._written))):
                self._out.write("\n")
            self._out_written = True
            self._out_block = block
        else:
            self._out.flush()  # keep the order of stdout and stderr when both are redirected
            if shared and self._out_block:
                self._out.write("\n")
                self._out_block = False
            elif block and (self._err_written or (shared and self._written)):
                (self._err if self._err_written else self._out).write("\n")
            self._err_written = True
        stream.write(text)
        self._written = True

    def finish(self) -> None:
        """End the run with a blank line when writing to a terminal."""
        if self._written and self._out.isatty():
            self._out.write("\n")

    @property
    def out(self) -> TextIO:
        return self._out

    @property
    def err(self) -> TextIO:
        return self._err

    def result(self, text: str) -> None:
        """Write a line, or several, of results to stdout."""
        self._write(self._out, f"{text}\n")

    def table(
        self,
        headers: Sequence[str],
        rows: Sequence[Row],
        *,
        align: Sequence[Align] | None = None,
    ) -> None:
        """Write one ungrouped table to stdout."""
        table = render_table(headers, rows, align=align, painter=self._paint_out, dash=self._dash)
        self._write(self._out, f"{table}\n", block=True)

    def sections(
        self,
        headers: Sequence[str],
        sections: Sequence[Section],
        *,
        align: Sequence[Align] | None = None,
    ) -> None:
        """Write a table whose rows are grouped under headings to stdout."""
        table = render_sections(
            headers, sections, align=align, painter=self._paint_out, dash=self._dash
        )
        self._write(self._out, f"{table}\n", block=True)

    def json(self, payload: Json) -> None:
        """Write `payload` as an indented JSON document to stdout."""
        self._write(self._out, json.dumps(payload, indent=2) + "\n")

    def message(self, text: str, *, style: Style | None = None, block: bool = False) -> None:
        """Write a line to stderr; `style` paints it, `block` sets it apart with a blank line."""
        line = text if style is None else self._paint_err(text, style)
        self._write(self._err, f"{line}\n", block=block)

    def warning(self, message: str, *, block: bool = False) -> None:
        """Write a warning to stderr; `block` sets it apart with a blank line."""
        self._diagnostic("warning", Style.YELLOW, message, block=block)

    def error(self, message: str, *, hint: str | None = None) -> None:
        """Write an error to stderr, followed immediately by `hint` when one is given."""
        self._diagnostic("error", Style.RED, message)
        if hint is not None:
            self.hint(hint)

    def hint(self, message: str, *, block: bool = False) -> None:
        """Write a hint to stderr; `block` sets it apart with a blank line."""
        self._diagnostic("hint", Style.CYAN, message, block=block)

    def note(self, message: str) -> None:
        self._diagnostic("note", Style.DIM, message)

    def _diagnostic(self, prefix: str, style: Style, message: str, *, block: bool = False) -> None:
        """Write `prefix: message` to stderr, indenting further lines under the first."""
        first, *rest = message.splitlines() or [""]
        label = self._paint_err(f"{prefix}:", style)
        indent = " " * (len(prefix) + 2)
        lines = [f"{label} {first}", *(f"{indent}{line}" for line in rest)]
        self._write(self._err, "\n".join(lines) + "\n", block=block)
