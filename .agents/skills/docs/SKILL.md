---
name: docs
description: Work on the bacsy documentation site - the English and Russian page trees, the Zensical configurations, the docstring-generated API reference, previewing and the build check. Use for any change under docs/, to zensical.toml or zensical.ru.toml, to .github/scripts/build_docs.py, or to a public docstring.
---

# Documentation

The documentation site is two Zensical builds, one per language, published to GitHub
Pages. Read the "Documentation" and "Terminology" sections of `AGENTS.md` first; this
skill adds the mechanics, and `writing.md` beside it the voice, vocabulary and which page
owns which fact. Read both before writing or editing a page.

## Layout

```
zensical.toml                 English build: docs_dir docs/en, site_dir site/en
zensical.ru.toml              Russian build: docs_dir docs/ru, site_dir site/ru
docs/en/, docs/ru/            the page trees, identical paths and file names
docs/<lang>/reference/        the API reference by topic: an intro paragraph, then `:::`
                              directives; plus the hand-written command line and
                              environment variable pages
.github/scripts/build_docs.py assembles site/pages/ for GitHub Pages
.github/workflows/docs.yml    builds on pull requests, publishes on main and after releases
site/                         build output, ignored by git
```

The two configurations are full copies and differ only in `docs_dir`, `site_dir`,
`site_url`, `edit_uri`, `theme.language` and the navigation titles. A change to any other
key is made in both files.

## Published versions

`build_docs.py` rebuilds the whole site from scratch on every deploy, so nothing is kept
between runs and there is no `gh-pages` branch:

- `<lang>/dev/` from `main`;
- `<lang>/X.Y.Z/` from the newest published final release, checked out by tag into a
  temporary worktree and built with that tag's own lock file, with `<lang>/stable/` as a
  copy;
- `<lang>/versions.json` for the version selector, and two redirect pages: the root
  sends the reader to the language their browser prefers, `/<lang>/` to the default
  version.

A tag that predates the documentation is skipped, and the site then holds `dev` alone.
The workflow passes the published release tag explicitly; a local full build discovers
the newest matching local tag when `--release-tag` is omitted. `MIKE_DOCS_VERSION` in the
environment tells Zensical which version it is building; no mike installation is involved.

## Commands

```bash
uv run --group docs zensical serve                       # preview English
uv run --group docs zensical serve -f zensical.ru.toml   # preview Russian
uv run .github/scripts/build_docs.py --no-release        # the check: both languages, strict
uv run .github/scripts/build_docs.py                     # the full site, as the workflow builds it
uv run .github/scripts/build_docs.py --release-tag vX.Y.Z # select one final release
```

Strict mode fails on a broken `.md` link, a missing anchor or an unresolved cross
reference. `zensical serve` does not enforce strict mode, so run the check before
reporting a change as done. A change to a public docstring also runs the four repository
checks.

```bash
uv run .github/scripts/check_docs_examples.py       # type-check the Python examples
```

The example checker gathers the `python` fences of each English page into one module,
wraps blocks that use top-level `await`, and runs `basedpyright` and `ruff format --check`
over the result, so a guessed method name or a wrong keyword fails. A fragment that is not
meant to type-check uses a `pycon` or `text` fence, or is preceded by an HTML comment
`<!-- no-check -->` on the line before the fence. Every `bacsy` command line in a `bash`
fence is matched against the parser without running it.

## Rules

- A page exists in both languages under the same path, and appears in both navigations
  at the same position. A page not yet translated holds the Russian placeholder: the
  title, then `!!! note` with "Эта страница ещё не написана."; the English placeholder
  says "This page is not written yet." The page tree is the maintainer's decision: do not
  add pages, sections or navigation entries unless asked.
- The API reference is the docstrings. Fix a wrong or missing description in the
  docstring, never in the reference page, and keep the page to its intro paragraphs and
  the `:::` directives. Every object is rendered once, on the page of its defining
  module; never `::: bacsy` for the package. Docstrings are English in both languages.
- Cross references use the mkdocstrings syntax, `[TradeApiClient][bacsy.client.TradeApiClient]`,
  and are checked by the strict build.
- Zensical's default Markdown extensions apply because neither configuration declares
  `markdown_extensions`; declaring the table would replace the whole default set. The
  defaults include admonitions, `pymdownx.details`, content tabs, tables, `attr_list`
  and `md_in_html`; `pymdownx.snippets` is not among them, so pages cannot include files.
- Examples never contain a real token, account identifier or captured response; the
  security rules in `AGENTS.md` apply to documentation as to code.
- `README.md` links to `/en/` and `/ru/`, which redirect to `stable` or, before the
  first release with documentation, to `dev`. Do not link to a specific version.

## Adding a page

1. Create `docs/en/<path>.md` and `docs/ru/<path>.md`.
2. Add the entry to `nav` in `zensical.toml` and `zensical.ru.toml`, same position,
   translated title.
3. Run the check and preview both languages.
