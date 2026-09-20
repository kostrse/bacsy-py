"""Pure formatting helpers of the command line."""

from __future__ import annotations

from datetime import UTC, timedelta, timezone

from bacsy.cli._format import (
    BOX_RULE,
    Cell,
    Section,
    Style,
    days_left,
    format_local,
    plural,
    render_sections,
    render_table,
    styled,
)
from tests.auth.fakes import DAY

NOW = 1_800_000_000


def test_format_local_uses_the_given_zone() -> None:
    assert format_local(0.0, UTC) == "1970-01-01 00:00:00"
    assert format_local(0.0, timezone(timedelta(hours=3))) == "1970-01-01 03:00:00"


def test_days_left_floors_and_never_goes_negative() -> None:
    assert days_left(NOW + 7 * DAY - 1, NOW) == 6
    assert days_left(NOW + 7 * DAY, NOW) == 7
    assert days_left(NOW - DAY, NOW) == 0


def test_plural() -> None:
    assert plural(1, "token") == "1 token"
    assert plural(2, "token") == "2 tokens"
    assert plural(0, "token") == "0 tokens"
    assert plural(1, "token is", "tokens are") == "1 token is"
    assert plural(3, "token is", "tokens are") == "3 tokens are"


def test_render_table_aligns_columns_and_upper_cases_headers() -> None:
    text = render_table(("a", "long header"), [["x", "1"], ["yyyy", "22"]])

    assert text.splitlines() == [
        "A     LONG HEADER",
        "-" * 17,
        "x     1",
        "yyyy  22",
    ]


def test_render_table_can_draw_a_box_rule() -> None:
    text = render_table(("a", "b"), [["x", "yy"]], dash=BOX_RULE)

    assert text.splitlines() == ["A  B", "\u2500" * 5, "x  yy"]


def test_render_table_right_aligns_and_leaves_no_trailing_spaces() -> None:
    text = render_table(("n", "name"), [["7", "a"], ["100", "bb"]], align=(">", "<"))

    assert text.splitlines() == ["  N  NAME", "-" * 9, "  7  a", "100  bb"]
    assert all(line == line.rstrip() for line in text.splitlines())


def test_render_sections_heads_and_indents_each_group() -> None:
    sections = [
        Section(
            heading=[Cell("main"), Cell(" \u00b7 a very long label indeed")], rows=[["x", "1"]]
        ),
        Section(heading=[Cell("iis")], rows=[["yyyy", "22"]]),
        Section(heading=[Cell("spare")], rows=[], note="(no tokens)"),
    ]

    text = render_sections(("a", "b"), sections)

    assert text.splitlines() == [
        "  A     B",
        "-" * 10,
        "main \u00b7 a very long label indeed",
        "  x     1",
        "",
        "iis",
        "  yyyy  22",
        "",
        "spare",
        "  (no tokens)",
    ]


def test_render_sections_paints_the_heading_and_the_note() -> None:
    sections = [
        Section(heading=[Cell("main", Style.BOLD), Cell(" \u00b7 lab", Style.DIM)], rows=[["x"]]),
        Section(heading=[Cell("spare", Style.BOLD)], rows=[], note="(no tokens)"),
    ]

    text = render_sections(("a",), sections, painter=styled)

    assert text.splitlines()[2] == styled("main", Style.BOLD) + styled(" \u00b7 lab", Style.DIM)
    assert text.splitlines()[-1] == "  " + styled("(no tokens)", Style.DIM)


def test_render_table_paints_after_padding() -> None:
    rows = [[Cell("x", Style.GREEN), "1"], ["yy", Cell("2", Style.RED)]]

    plain = render_table(("a", "b"), rows)
    coloured = render_table(("a", "b"), rows, painter=styled)

    assert "\x1b[" not in plain
    assert plain.splitlines()[2:] == ["x   1", "yy  2"]
    assert coloured.splitlines()[0] == f"{styled('A ', Style.BOLD)}  {styled('B', Style.BOLD)}"
    assert coloured.splitlines()[1] == styled("-" * 5, Style.DIM)
    assert coloured.splitlines()[2] == f"{styled('x ', Style.GREEN)}  1"
    assert coloured.splitlines()[3] == f"yy  {styled('2', Style.RED)}"
