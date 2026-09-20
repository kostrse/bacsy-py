"""Pure formatting helpers: times, plurals, styles and table layout.

Nothing here writes to a stream.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from datetime import tzinfo

DAY = 86400.0


def format_local(timestamp: float, tz: tzinfo | None) -> str:
    """Return `timestamp` as `YYYY-MM-DD HH:MM:SS` in `tz`, or in local time when `None`."""
    return datetime.fromtimestamp(timestamp, tz=UTC).astimezone(tz).strftime("%Y-%m-%d %H:%M:%S")


def format_iso(timestamp: float, tz: tzinfo | None) -> str:
    """Return `timestamp`, truncated to the second, as ISO 8601 with an offset in `tz`."""
    return datetime.fromtimestamp(int(timestamp), tz=UTC).astimezone(tz).isoformat()


def days_left(expires_at: float, now: float) -> int:
    """Return the whole days from `now` to `expires_at`, never negative."""
    return max(0, math.floor((expires_at - now) / DAY))


def plural(count: int, noun: str, plural_form: str | None = None) -> str:
    """Return `count` followed by the noun: `1 token`, `2 tokens`."""
    word = noun if count == 1 else (plural_form or f"{noun}s")
    return f"{count} {word}"


class Style(StrEnum):
    """ANSI SGR escape sequences for text styles."""

    BOLD = "\x1b[1m"
    DIM = "\x1b[2m"
    RED = "\x1b[31m"
    GREEN = "\x1b[32m"
    YELLOW = "\x1b[33m"
    CYAN = "\x1b[36m"


RESET = "\x1b[0m"

type Painter = Callable[[str, Style], str]
"""Callable applying a `Style` to text and returning what is written."""


def styled(text: str, style: Style) -> str:
    """Return `text` wrapped in the escape sequence of `style`."""
    return f"{style}{text}{RESET}"


def plain(text: str, style: Style) -> str:
    """Return `text` unchanged."""
    return text


@dataclass(frozen=True, slots=True)
class Cell:
    """One table cell: its text and an optional style."""

    text: str
    style: Style | None = None


type Align = Literal["<", ">"]


type Row = Sequence[str | Cell]


# Characters drawing the rule under the table header.
ASCII_RULE = "-"
BOX_RULE = "\u2500"

COLUMN_GAP = "  "


@dataclass(frozen=True, slots=True)
class Section:
    """Rows grouped under a heading that spans the table."""

    heading: Sequence[Cell] | None = None
    rows: Sequence[Row] = ()
    note: str | None = None
    """Shown in place of the rows when the section has none."""


def render_sections(
    headers: Sequence[str],
    sections: Sequence[Section],
    *,
    align: Sequence[Align] | None = None,
    painter: Painter = plain,
    dash: str = ASCII_RULE,
    indent: str = "  ",
) -> str:
    """Render an aligned table whose rows are grouped under section headings.

    Header cells and the rule below them are passed to `painter` with `Style.BOLD` and
    `Style.DIM`, respectively. Columns are separated by two spaces. Rows are indented
    under their heading, which is written unpadded, and a blank line separates sections.
    Cells are padded before they are painted, so escape sequences do not affect
    alignment; a left-aligned last column is not padded, so lines carry no trailing
    spaces.
    """
    alignments = tuple(align) if align is not None else ("<",) * len(headers)
    bodies = [
        [[c if isinstance(c, Cell) else Cell(c) for c in row] for row in section.rows]
        for section in sections
    ]
    widths = [len(h) for h in headers]
    for body in bodies:
        for row in body:
            for index, cell in enumerate(row):
                widths[index] = max(widths[index], len(cell.text))

    def line(cells: Sequence[Cell]) -> str:
        pieces: list[str] = []
        last = len(cells) - 1
        for index, cell in enumerate(cells):
            spec = alignments[index]
            padded = (
                cell.text if index == last and spec == "<" else f"{cell.text:{spec}{widths[index]}}"
            )
            pieces.append(padded if cell.style is None else painter(padded, cell.style))
        return indent + COLUMN_GAP.join(pieces)

    def run(cells: Sequence[Cell]) -> str:
        return "".join(c.text if c.style is None else painter(c.text, c.style) for c in cells)

    header = [Cell(h.upper(), Style.BOLD) for h in headers]
    width = len(indent) + sum(widths) + len(COLUMN_GAP) * (len(widths) - 1)
    lines = [line(header), painter(dash * width, Style.DIM)]
    for index, (section, body) in enumerate(zip(sections, bodies, strict=True)):
        if index:
            lines.append("")
        if section.heading is not None:
            lines.append(run(section.heading))
        if body:
            lines.extend(line(row) for row in body)
        elif section.note is not None:
            lines.append(indent + painter(section.note, Style.DIM))
    return "\n".join(lines)


def render_table(
    headers: Sequence[str],
    rows: Sequence[Row],
    *,
    align: Sequence[Align] | None = None,
    painter: Painter = plain,
    dash: str = ASCII_RULE,
) -> str:
    """Render one ungrouped table: `render_sections` with a single unheaded section."""
    return render_sections(
        headers, [Section(rows=rows)], align=align, painter=painter, dash=dash, indent=""
    )
