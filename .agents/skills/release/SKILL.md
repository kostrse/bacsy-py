---
name: release
description: Prepare a bacsy release - bump the version, cut the changelog, run the checks, commit, and hand over for approval before anything is pushed or tagged.
argument-hint: "[X.Y.Z]"
disable-model-invocation: true
metadata:
  opencode/autoinvoke: false
---

# Release

Prepare a bacsy release on `main` and stop for the maintainer's approval before anything
leaves the machine. The release itself is the tag push: `.github/workflows/release.yml`
verifies the tag, runs the checks, builds, publishes to PyPI and creates the GitHub
Release. Read the "Releases" section of `AGENTS.md` first.

## 1. Preconditions

Stop and report if any of these fails; do not work around it.

- `git branch --show-current` prints `main` and `git status --porcelain` prints nothing.
- After `git fetch origin`, `git rev-parse main origin/main` prints the same commit twice.
- `uv sync` succeeds and `uv lock --check` passes.
- `CHANGELOG.md` has a non-empty `## [Unreleased]` section.

## 2. Choose the version

- Use the version given as the argument (`/release 0.2.0`). Without one, propose a version
  from the `[Unreleased]` entries and wait for confirmation: while the major version is 0,
  anything under Changed, Removed or Deprecated needs a minor bump; Added usually deserves
  a minor bump too; only Fixed or Security allows a patch bump.
- The version is PEP 440 without a `v` prefix: `0.2.0`, `0.2.1`, or a pre-release such as
  `0.2.0b1` for a preview. Never a `.dev` version.
- The tag must be unused: `git tag --list vX.Y.Z` and `git ls-remote --tags origin vX.Y.Z`
  both print nothing.

## 3. Apply

1. `uv version X.Y.Z`. This rewrites `pyproject.toml` and `uv.lock`.
2. In `CHANGELOG.md`, rename `## [Unreleased]` to `## [X.Y.Z] - YYYY-MM-DD` with today's
   date, insert a new empty `## [Unreleased]` heading above it, and update the link
   references at the bottom:
   - `[Unreleased]: https://github.com/kostrse/bacsy-py/compare/vX.Y.Z...HEAD`
   - `[X.Y.Z]: https://github.com/kostrse/bacsy-py/compare/vPREVIOUS...vX.Y.Z`, or
     `https://github.com/kostrse/bacsy-py/releases/tag/vX.Y.Z` for the first release.
   Keep the entries as they are; only fix wording that is wrong. Entries use inline links,
   because the release notes are the section body alone.
3. Check `README.md` and `AGENTS.md` for anything the release makes stale. Normally
   nothing changes.

## 4. Verify

Run these and report their real output. Any failure stops the release: fix it in a
separate commit first, then start over from step 1.

```bash
uv run ruff format --check .
uv run ruff check .
uv run basedpyright
uv run pytest
uv build
uvx twine check --strict dist/*
uvx --from dist/bacsy-X.Y.Z-py3-none-any.whl bacsy --version
python3 .github/scripts/release_notes.py X.Y.Z
```

The last command prints the notes the GitHub Release will carry.

## 5. Commit

One commit, message `Release X.Y.Z`, containing exactly `pyproject.toml`, `uv.lock` and
`CHANGELOG.md`. Add the attribution trailer your agent uses, if any.

## 6. Hand over and stop

Show the maintainer the version, the release notes, `git show --stat HEAD`, and the steps
below. Then stop. Do not push, tag or dispatch a workflow until the maintainer explicitly
approves in this conversation.

## 7. After approval

Three stages, each gated on the previous one. Watching a workflow run is delegated to a
subagent (see "Watching a run" below) so the run logs never enter the main context; the
main agent acts only on the verdict it returns.

1. Push `main`:

   ```bash
   git push origin main
   ```

2. Watch the CI workflow on the release commit: delegate "watch the `ci.yml` run for
   commit `<sha>`" to a subagent, where `<sha>` is `git rev-parse HEAD`. If the verdict is
   a failure, report it to the maintainer and stop. Do not push the tag. The fix is a new
   commit on `main`; the release resumes at stage 1 once the maintainer approves again.

3. Only after CI passes, push the tag and delegate "watch the `release.yml` run for tag
   `vX.Y.Z`" to a subagent:

   ```bash
   git tag -a vX.Y.Z -m "bacsy X.Y.Z"
   git push origin vX.Y.Z
   ```

   On success, report `https://pypi.org/project/bacsy/X.Y.Z/` and the GitHub Release URL.

If the Release workflow fails before the "Publish to PyPI" job, nothing was published:
report the failure and stop. The fix is a new commit on `main`; after approval, move the
tag to it (`git tag -d vX.Y.Z`, `git push origin :refs/tags/vX.Y.Z`, then tag and push
again) so the workflow reruns. If it fails after publishing, PyPI already holds the
version: keep the tag and rerun only the failed jobs with `gh run rerun <run-id> --failed`.

## Watching a run

Give the subagent the workflow file name and the commit SHA or tag, and this brief. If
your agent cannot spawn subagents, run the same steps inline but show the maintainer only
the verdict, not the logs.

1. Find the run; it may take a few seconds to appear, so retry until it does:

   ```bash
   gh run list --workflow=<file> --commit <sha> --limit 1 --json databaseId,url --jq '.[0]'
   ```

   For a tag, use `--branch vX.Y.Z` instead of `--commit`.
2. Wait for it: `gh run watch <run-id> --exit-status`.
3. Return a verdict of a few lines and nothing else: the run URL, `passed` or `failed`,
   and for a failure the name of the failed job and step and the last relevant lines of
   `gh run view <run-id> --log-failed`, at most about twenty. Never return the full log.
