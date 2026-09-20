"""Print the release notes for one version from ``CHANGELOG.md``.

Usage: ``release_notes.py VERSION [CHANGELOG]``

Writes the body of the ``## [VERSION] - DATE`` section, up to the next ``## `` heading, to
standard output. Exits with status 1 when the section is missing or empty. The body is
used verbatim as the GitHub Release notes, so entries must use inline links: the link
references at the end of the changelog are not part of any section.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_LINK_REFERENCE = re.compile(r"^\[[^\]]+\]:\s")
"""A reference-style link definition; the block of them ends the last section."""


def release_notes(changelog: str, version: str) -> str | None:
    """Return the body of the section for ``version``, or ``None`` when there is none."""
    heading = re.compile(rf"^## \[{re.escape(version)}\](?:\s|$)")
    body: list[str] = []
    inside = False
    for line in changelog.splitlines():
        if line.startswith("## "):
            if inside:
                break
            inside = heading.match(line) is not None
        elif inside:
            if _LINK_REFERENCE.match(line):
                break
            body.append(line)
    if not inside:
        return None
    return "\n".join(body).strip("\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Print the release notes for one version.")
    parser.add_argument("version", help="the version whose section to print, e.g. 0.1.0")
    parser.add_argument(
        "changelog",
        nargs="?",
        type=Path,
        default=Path("CHANGELOG.md"),
        help="the changelog to read (default: CHANGELOG.md)",
    )
    args = parser.parse_args(argv)
    version: str = args.version
    path: Path = args.changelog
    notes = release_notes(path.read_text(encoding="utf-8"), version)
    if not notes:
        sys.stderr.write(f"{path}: no release notes for version {version}\n")
        return 1
    sys.stdout.write(notes + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
