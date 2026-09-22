"""Check the code examples in the English documentation pages.

Usage: ``check_docs_examples.py [--keep DIR] [PAGE ...]``

Every ``python`` fence becomes one module under a temporary directory, prefixed with a
preamble that provides the open ``client`` the guides assume. A block that uses top-level
``await``, ``async for`` or ``async with`` and defines no function is wrapped in an
``async def``. The modules are checked with ``basedpyright`` and ``ruff format --check``,
so a guessed method name, a wrong keyword argument or an unformatted snippet fails.

A fence is skipped when the line before it is the HTML comment ``<!-- no-check -->``;
``pycon`` and ``text`` fences are never checked.

Every ``bash`` fence is scanned for lines that run ``bacsy``: each is parsed by the
command line's own parser and fails the check when the parser rejects it. Nothing is
executed and no state directory is touched.

Exit status is 1 when any check fails.
"""

from __future__ import annotations

import argparse
import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCS_DIR = REPO_ROOT / "docs" / "en"

FENCE = re.compile(
    r"^(?P<indent> *)```(?P<lang>[\w+-]*)[^\n]*\n(?P<body>.*?)^(?P=indent)```[ \t]*$", re.S | re.M
)
NO_CHECK = "<!-- no-check -->"
USES_AWAIT = re.compile(r"\bawait\b|\basync (for|with)\b")
DEFINES_FUNCTION = re.compile(r"^\s*(async )?def ", re.M)
BACSY_COMMAND = re.compile(r"^\s*(?:\$ )?(?:uvx |uv run )?bacsy\b(?P<args>.*)$")
SHELL_OPERATORS = {"&&", "||", "|", ";"}

PREAMBLE = """# Generated from a documentation page; not a real program.
# pyright: reportUnusedVariable=false, reportUnusedImport=false
# pyright: reportUnusedExpression=false, reportUnusedFunction=false
from __future__ import annotations

from bacsy import TradeApiClient as _TradeApiClient


def _open_client() -> _TradeApiClient:
    raise NotImplementedError


client = _open_client()


"""


def fences(text: str) -> list[tuple[str, str, bool]]:
    """Return (language, body, skipped) for every fence in a page, in order."""
    found: list[tuple[str, str, bool]] = []
    for match in FENCE.finditer(text):
        indent = match.group("indent")
        body = match.group("body")
        if indent:
            body = "".join(
                line[len(indent) :] if line.startswith(indent) else line
                for line in body.splitlines(keepends=True)
            )
        before = text[: match.start()].rstrip("\n").rsplit("\n", 1)[-1].strip()
        found.append((match.group("lang"), body, before == NO_CHECK))
    return found


def python_module(block: str) -> str:
    """Build one module from a Python block."""
    block = block.rstrip("\n")
    if USES_AWAIT.search(block) and not DEFINES_FUNCTION.search(block):
        indented = "".join(
            ("    " + line) if line.strip() else line for line in block.splitlines(keepends=True)
        )
        block = f"async def _cell() -> None:\n{indented}"
    return f"{PREAMBLE}{block}\n"


def check_bash(page: Path, body: str) -> list[str]:
    """Return a message for every `bacsy` command line the parser rejects."""
    from bacsy.cli._parser import build_parser

    problems: list[str] = []
    parser = build_parser()
    for line in body.splitlines():
        match = BACSY_COMMAND.match(line.split("#", 1)[0])
        if match is None:
            continue
        tokens = shlex.split(match.group("args"))
        cut = next((i for i, t in enumerate(tokens) if t in SHELL_OPERATORS), None)
        if cut is not None:
            tokens = tokens[:cut]
        if not tokens or "--help" in tokens or "-h" in tokens:
            continue
        try:
            parser.parse_args(tokens)
        except SystemExit:
            problems.append(f"{page.relative_to(REPO_ROOT)}: rejected command line: {line.strip()}")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("pages", nargs="*", type=Path, help="pages to check; default: all")
    parser.add_argument("--keep", type=Path, help="write the generated modules here")
    options = parser.parse_args()

    pages = options.pages or sorted(DOCS_DIR.rglob("*.md"))
    problems: list[str] = []
    modules: dict[str, str] = {}
    for page in pages:
        page = page.resolve()
        stem = page.relative_to(DOCS_DIR).with_suffix("").as_posix()
        stem = stem.replace("/", "__").replace("-", "_")
        index = 0
        for lang, body, skipped in fences(page.read_text(encoding="utf-8")):
            if skipped:
                continue
            if lang == "python":
                index += 1
                modules[f"{stem}__{index}.py"] = python_module(body)
            elif lang in {"bash", "sh", "shell", "console"}:
                problems.extend(check_bash(page, body))

    with tempfile.TemporaryDirectory(prefix="bacsy-docs-examples-") as tmp:
        out = options.keep or Path(tmp)
        out.mkdir(parents=True, exist_ok=True)
        paths = [str(out / name) for name in modules]
        for path, source in zip(paths, modules.values(), strict=True):
            Path(path).write_text(source, encoding="utf-8")
        if modules:
            for command in (
                ["uv", "run", "basedpyright", *paths],
                ["uv", "run", "ruff", "format", "--check", *paths],
            ):
                result = subprocess.run(command, cwd=REPO_ROOT, capture_output=True, text=True)
                if result.returncode != 0:
                    problems.append(f"{command[2]} failed:\n{result.stdout}{result.stderr}")

    for problem in problems:
        sys.stderr.write(problem + "\n")
    sys.stdout.write(f"checked {len(modules)} python blocks on {len(pages)} pages\n")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
