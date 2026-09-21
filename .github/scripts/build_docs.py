"""Assemble the documentation site that GitHub Pages serves.

Usage: ``build_docs.py [--no-release | --release-tag TAG] [--out DIR]``

Each language has its own Zensical configuration at the repository root and is built
twice: ``dev`` from the working tree and a release from its ``vX.Y.Z`` tag, checked out
into a temporary worktree and built with that tag's own lock file. By default the release
is the newest matching local tag; the publishing workflow supplies the newest published
GitHub Release explicitly. The release is published under its number with a ``stable``
copy; a tag that predates the documentation is skipped, and the site then holds ``dev``
alone. The output is::

    <out>/index.html            redirect to the browser's language, <lang>/stable/
                                (<lang>/dev/ without a release)
    <out>/<lang>/index.html     redirect to stable/ (dev/ without a release)
    <out>/<lang>/versions.json  what the version selector reads
    <out>/<lang>/<version>/     one built site per version: dev, X.Y.Z, stable

``MIKE_DOCS_VERSION`` tells Zensical which version a build is, so canonical URLs and the
version selector point at ``<lang>/<version>/``. Every build runs in strict mode and a
failing one fails the script.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIGS = {"en": "zensical.toml", "ru": "zensical.ru.toml"}
"""Language code to the Zensical configuration that builds it, in selector order."""

LANGUAGE_LABELS = {"en": "Documentation in English", "ru": "Документация на русском"}
"""Language code to the link the root page offers, written in that language."""

DEV = "dev"
STABLE = "stable"
_RELEASE_TAG = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
"""A final release tag; pre-releases never become ``stable``."""


def newest_release_tag(tags: list[str]) -> str | None:
    """Return the highest ``vX.Y.Z`` tag among ``tags``, or ``None`` when there is none."""
    releases = {
        tag: tuple(int(part) for part in match.groups())
        for tag in tags
        if (match := _RELEASE_TAG.match(tag))
    }
    if not releases:
        return None
    return max(releases, key=releases.__getitem__)


def versions_json(release: str | None) -> str:
    """Return the ``versions.json`` document listing ``release`` (if any) and ``dev``."""
    versions: list[dict[str, object]] = []
    if release is not None:
        versions.append({"version": release, "title": release, "aliases": [STABLE]})
    versions.append({"version": DEV, "title": DEV, "aliases": []})
    return json.dumps(versions, indent=2) + "\n"


def lang_redirect_html(default: str) -> str:
    """Return the root page, which sends the browser to the language it prefers.

    The languages come from ``CONFIGS`` in order; a browser that matches none of them,
    or has no JavaScript, gets the first one.
    """
    available = json.dumps(list(CONFIGS))
    fallback = next(iter(CONFIGS))
    links = "\n".join(
        f'  <li><a href="{lang}/{default}/">{LANGUAGE_LABELS[lang]}</a></li>' for lang in CONFIGS
    )
    return (
        "<!DOCTYPE html>\n"
        f'<html lang="{fallback}">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        "<title>Redirecting</title>\n"
        "<script>\n"
        f"var available = {available};\n"
        f'var fallback = "{fallback}";\n'
        f'var version = "{default}";\n'
        "var preferred = navigator.languages || [navigator.language || fallback];\n"
        "var lang = fallback;\n"
        "for (var i = 0; i < preferred.length; i++) {\n"
        '  var base = (preferred[i] || "").toLowerCase().split(/[-_]/)[0];\n'
        "  if (available.indexOf(base) !== -1) { lang = base; break; }\n"
        "}\n"
        'location.replace(lang + "/" + version + "/");\n'
        "</script>\n"
        f'<noscript><meta http-equiv="refresh" content="0; url={fallback}/{default}/">'
        "</noscript>\n"
        f'<link rel="canonical" href="{fallback}/{default}/">\n'
        "</head>\n"
        "<body>\n"
        "<ul>\n"
        f"{links}\n"
        "</ul>\n"
        "</body>\n"
        "</html>\n"
    )


def version_redirect_html(default: str) -> str:
    """Return a language's index page, which sends the browser to the default version."""
    target = f"{default}/"
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        f'<meta http-equiv="refresh" content="0; url={target}">\n'
        f'<link rel="canonical" href="{target}">\n'
        "<title>Redirecting</title>\n"
        "</head>\n"
        "<body>\n"
        f'<p>Redirecting to <a href="{target}">{target}</a>.</p>\n'
        "</body>\n"
        "</html>\n"
    )


def git(*args: str) -> str:
    """Run a git command in the repository and return its output."""
    result = subprocess.run(
        ["git", *args], cwd=REPO_ROOT, check=True, capture_output=True, text=True
    )
    return result.stdout


def build(tree: Path, lang: str, version: str, destination: Path) -> None:
    """Build one language of the documentation in ``tree`` and move it to ``destination``."""
    env = {name: value for name, value in os.environ.items() if name != "VIRTUAL_ENV"}
    env["MIKE_DOCS_VERSION"] = version
    sys.stdout.write(f"Building {lang}/{version} from {tree}\n")
    subprocess.run(
        ["uv", "run", "--group", "docs", "zensical", "build", "--strict", "-f", CONFIGS[lang]],
        cwd=tree,
        env=env,
        check=True,
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(tree / "site" / lang, destination)


def build_release(tag: str, out: Path) -> bool:
    """Build the release tagged ``tag``; return whether the tag had documentation to build."""
    version = tag.removeprefix("v")
    with tempfile.TemporaryDirectory(prefix="bacsy-docs-") as scratch:
        worktree = Path(scratch) / version
        git("worktree", "add", "--detach", str(worktree), tag)
        try:
            if not (worktree / CONFIGS["en"]).exists():
                sys.stdout.write(f"Skipping {tag}: it predates the documentation\n")
                return False
            for lang in CONFIGS:
                build(worktree, lang, version, out / lang / version)
                shutil.copytree(out / lang / version, out / lang / STABLE)
        finally:
            git("worktree", "remove", "--force", str(worktree))
    return True


def assemble(out: Path, *, with_release: bool, release_tag: str | None = None) -> None:
    """Build every version of every language into ``out`` and add the site-wide files.

    An explicit ``release_tag`` overrides discovery of the newest matching local tag.
    """
    if out.exists():
        shutil.rmtree(out)
    for lang in CONFIGS:
        build(REPO_ROOT, lang, DEV, out / lang / DEV)
    release: str | None = None
    if with_release:
        tag = release_tag or newest_release_tag(git("tag", "--list").split())
        if tag is not None and build_release(tag, out):
            release = tag.removeprefix("v")
    default = STABLE if release is not None else DEV
    for lang in CONFIGS:
        (out / lang / "versions.json").write_text(versions_json(release), encoding="utf-8")
        (out / lang / "index.html").write_text(version_redirect_html(default), encoding="utf-8")
    (out / "index.html").write_text(lang_redirect_html(default), encoding="utf-8")
    (out / ".nojekyll").touch()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Assemble the documentation site.")
    release = parser.add_mutually_exclusive_group()
    release.add_argument(
        "--no-release",
        action="store_true",
        help="build only dev from the working tree, skipping the newest release tag",
    )
    release.add_argument(
        "--release-tag",
        metavar="TAG",
        help="build this final release tag (vX.Y.Z) instead of discovering the newest one",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=REPO_ROOT / "site" / "pages",
        help="the directory to assemble the site in (default: site/pages)",
    )
    args = parser.parse_args(argv)
    out: Path = args.out.resolve()
    no_release: bool = args.no_release
    release_tag: str | None = args.release_tag
    if release_tag is not None and not _RELEASE_TAG.match(release_tag):
        parser.error(f"--release-tag must be a final release tag vX.Y.Z, not {release_tag!r}")
    try:
        assemble(out, with_release=not no_release, release_tag=release_tag)
    except subprocess.CalledProcessError as error:
        command = " ".join(str(part) for part in error.cmd)
        sys.stderr.write(f"{command}: exit status {error.returncode}\n")
        if error.stderr:
            sys.stderr.write(error.stderr)
        return 1
    sys.stdout.write(f"Site assembled in {out}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
