"""Colour policy and the routing of results and diagnostics between the two streams."""

from __future__ import annotations

import io
import sys

import pytest

from bacsy.cli._console import ColorMode, Console, color_enabled, table_dash
from bacsy.cli._format import ASCII_RULE, BOX_RULE, Cell, Section, Style
from tests.cli.conftest import FakeTty


@pytest.mark.parametrize(
    ("mode", "tty", "environ", "expected"),
    [
        ("auto", True, {}, True),
        ("auto", False, {}, False),
        ("auto", True, {"NO_COLOR": "1"}, False),
        ("auto", False, {"FORCE_COLOR": "1"}, True),
        ("auto", True, {"NO_COLOR": "1", "FORCE_COLOR": "1"}, False),
        ("auto", True, {"TERM": "dumb"}, False),
        ("always", False, {"NO_COLOR": "1"}, True),
        ("never", True, {"FORCE_COLOR": "1"}, False),
    ],
)
def test_color_enabled(mode: ColorMode, tty: bool, environ: dict[str, str], expected: bool) -> None:
    if sys.platform == "win32":
        environ = {"WT_SESSION": "x", **environ}
    stream = FakeTty() if tty else io.StringIO()

    assert color_enabled(mode, stream, environ) is expected


def test_results_go_to_stdout_and_diagnostics_to_stderr() -> None:
    out, err = io.StringIO(), io.StringIO()
    console = Console(out, err, color_out=False, color_err=False)

    console.result("done")
    console.table(("a",), [["x"]])
    console.json({"k": [1, None]})
    console.warning("careful")
    console.error("broken", hint="fix it")
    console.note("by the way")

    assert out.getvalue() == 'done\n\nA\n-\nx\n\n{\n  "k": [\n    1,\n    null\n  ]\n}\n'
    assert err.getvalue() == "warning: careful\nerror: broken\nhint: fix it\nnote: by the way\n"


def test_tables_are_set_apart_by_blank_lines() -> None:
    out, err = io.StringIO(), io.StringIO()
    console = Console(out, err, color_out=False, color_err=False)

    console.table(("a",), [["x"]])
    console.hint("next")
    console.result("line")
    console.table(("b",), [["y"]])
    console.finish()

    assert out.getvalue() == "A\n-\nx\n\nline\n\nB\n-\ny\n"
    assert err.getvalue() == "hint: next\n"


def test_a_terminal_also_gets_blank_lines_between_streams() -> None:
    out, err = FakeTty(), io.StringIO()
    console = Console(out, err, color_out=False, color_err=False)

    console.warning("w")
    console.table(("a",), [["x"]])
    console.hint("next")
    console.result("line")
    console.finish()

    assert out.getvalue() == "\nA\n-\nx\n\nline\n\n"
    assert err.getvalue() == "warning: w\nhint: next\n"


def test_box_drawing_needs_a_utf8_stream() -> None:
    assert table_dash(io.StringIO()) == ASCII_RULE
    utf8 = io.TextIOWrapper(io.BytesIO(), encoding="utf-8", newline="\n")
    assert table_dash(utf8) == BOX_RULE
    latin = io.TextIOWrapper(io.BytesIO(), encoding="cp1251", newline="\n")
    assert table_dash(latin) == ASCII_RULE

    console = Console(utf8, io.StringIO(), color_out=False, color_err=False)
    console.table(("a", "b"), [["x", "y"]])
    utf8.flush()
    assert utf8.buffer.getvalue().decode() == "A  B\n" + "\u2500" * 4 + "\nx  y\n"


def test_finish_adds_a_blank_line_only_on_a_terminal() -> None:
    tty = FakeTty()
    console = Console(tty, io.StringIO(), color_out=False, color_err=False)
    console.finish()
    assert tty.getvalue() == ""

    console.result("done")
    console.finish()
    assert tty.getvalue() == "done\n\n"

    piped = io.StringIO()
    console = Console(piped, io.StringIO(), color_out=False, color_err=False)
    console.result("done")
    console.finish()
    assert piped.getvalue() == "done\n"


def test_sections_are_written_as_one_block() -> None:
    out, err = io.StringIO(), io.StringIO()
    console = Console(out, err, color_out=False, color_err=False)

    console.sections(("a",), [Section(heading=[Cell("main")], rows=[["x"]])])
    console.result("done")

    assert out.getvalue() == "  A\n---\nmain\n  x\n\ndone\n"
    assert err.getvalue() == ""


def test_multi_line_diagnostics_are_indented_under_the_prefix() -> None:
    err = io.StringIO()
    console = Console(io.StringIO(), err, color_out=False, color_err=False)

    console.hint("first\n  second\nthird")

    assert err.getvalue() == "hint: first\n        second\n      third\n"


def test_colour_paints_prefixes_but_never_json() -> None:
    out, err = io.StringIO(), io.StringIO()
    console = Console(out, err, color_out=True, color_err=True)

    console.error("broken")
    console.table(("status",), [["ok"]])
    console.json({"status": "ok"})

    assert err.getvalue() == "\x1b[31merror:\x1b[0m broken\n"
    table, rule, document = out.getvalue().split("\n", 2)
    assert table == "\x1b[1mSTATUS\x1b[0m"
    assert rule == "\x1b[2m------\x1b[0m"
    assert "\x1b[" not in document


def test_message_is_painted_only_when_a_style_is_given() -> None:
    err = io.StringIO()
    console = Console(io.StringIO(), err, color_out=False, color_err=True)

    console.message("aborted")
    console.message("quietly", style=Style.DIM, block=True)

    assert err.getvalue() == "aborted\n\n\x1b[2mquietly\x1b[0m\n"
