# Releasing Power Tools

How an end-user release of the **Power Tools** add-in is built and published.
Releases are automated: publishing a GitHub Release builds a clean, end-user-only
zip and attaches it to that release. No manual packaging steps are involved.

---

## Contents

- [How it works](#how-it-works)
- [Cutting a release](#cutting-a-release)
- [What ships and what is stripped](#what-ships-and-what-is-stripped)
- [Keeping README.pdf current](#keeping-readmepdf-current)
- [Manifest stamping](#manifest-stamping)
- [Dry runs and local builds](#dry-runs-and-local-builds)
- [Changing what ships](#changing-what-ships)

---

## How it works

Two pieces implement the pipeline:

| Path | Purpose |
|---|---|
| `tools/release/build_release.py` | Builds `dist/PowerTools-<version>.zip` from the git-tracked tree. Standard library + the `git` CLI only; no installs needed. |
| `.github/workflows/release.yml` | Runs the script when a GitHub Release is **published** and attaches the zip to that release. Also supports a manual dry run. |
| `tools/pandoc/build_readme_pdf.py` | Builds `README.pdf` from `README.md`. The release build calls it before zipping; CI gates it on every push. |

The script takes its file list from `git ls-files`, so anything git-ignored can
never ship — the [`.debug` marker](index.md#the-debug-marker), `.env`, editor and
agent config, virtualenvs, caches, generated palette `init.js` files, and the
per-machine `settings/preferences.json` are all stripped *by construction*, not
by pattern-matching the filesystem. Tracked developer-only paths are then removed
by an explicit exclusion list (see below).

Every entry in the zip lives under a top-level `PowerTools/` folder, so
extracting the archive into Fusion's AddIns directory yields a correctly named
add-in folder.

## Cutting a release

1. Make sure [CI](index.md#developer-tooling) is green on the commit you are
   releasing.
2. On GitHub, draft a new **Release** with a tag of the form `vX.Y.Z`
   (e.g. `v1.2.0`). Write the release notes as usual.
3. **Publish** the release. The `Release` workflow builds
   `PowerTools-X.Y.Z.zip` and attaches it to the release within a couple of
   minutes.
4. Verify the asset appears on the release page and spot-check the zip if the
   exclusion rules changed since the last release.

The version label comes from the tag with any leading `v` stripped: tag
`v1.2.0` produces `PowerTools-1.2.0.zip` whose manifest reports version
`1.2.0`.

## What ships and what is stripped

**Ships:** `PowerTools.py`, `PowerTools.manifest`, `config.py`,
`command_registry.py`, `settings_store.py`, every `commands/<name>/` package with
its `resources/` (icons, SVGs, palette HTML/JS/CSS), `lib/ptAddInUtils/`,
`LICENSE`, `README.md`, `README.pdf`, and the end-user guides — `docs/*.md` plus
`docs/assets/` (the Preferences palette links to them, and the README's command
table does too).

**Stripped** (tracked, but developer-only):

| Category | Paths |
|---|---|
| Tests and CI | `tests/`, `.github/`, `pyproject.toml`, `.gitignore`, `.git-blame-ignore-revs` |
| Dev tooling | `tools/` (including this release script itself) |
| Developer docs | `docs/arch/`, `docs/dev/` |
| Agent guidance | `AGENTS.md`, `CLAUDE.md`, `.claude/` |
| Stale org config | the root `hub.json` (the live copy the add-in reads is the git-ignored `cache/hub.json`) |
| Design sources in `resources/` | `generate_icons.py` helpers, `*.idraw`, `*.pxd` bundles, `fusion_icon_resources` (zip and extracted folder) |

There is no `settings/preferences.json` in the zip **on purpose** — a fresh
install generates pristine, registry-derived defaults on first launch
(`settings_store.py`). Shipping a file would ship a developer's accumulated
preferences instead.

**Safety guard:** the build aborts with an error if `.debug`, `.env`, or
`settings/preferences.json` ever become git-tracked (e.g. after a `.gitignore`
regression), rather than shipping them.

## Keeping README.pdf current

`README.pdf` ships in the zip but is a **checked-in artifact** — nothing in
Fusion or in the add-in generates it. Left alone it goes stale the moment
`README.md` changes, and the release quietly ships a PDF that disagrees with the
Markdown beside it. That happened once already: the Flatten Surface row was
added to the command table in `b5946ea` and the PDF was not rebuilt until
`f93ec75`.

Two things now prevent it:

| Guard | Where | Needs pandoc? |
|---|---|---|
| `build_readme_pdf.py --check` | CI, on every push; also as a pytest case | No |
| `refresh_readme_pdf()` | `build_release.py`, before the file list is taken | Only if stale |

Every build stamps a SHA-256 of `README.md` into the PDF's `Subject` metadata
(invisible — it never renders on the page). `--check` reads that stamp back and
compares it with the Markdown on disk, so it answers *"was this PDF built from
this README?"* exactly, from the two files alone: no pandoc, no xelatex, no git
history, and it works on CI's shallow checkout and on a dirty working tree.

Because CI keeps `main` current, the release build's rebuild path stays cold and
`release.yml` still needs no installs. If it ever does go stale on a machine
without pandoc and xelatex, the build **aborts** rather than shipping the stale
PDF.

To rebuild by hand after editing the README:

```
python tools/pandoc/build_readme_pdf.py
```

Commit the regenerated PDF alongside the Markdown change. A clean run reports
`overfull boxes : 0` and `undefined refs : 0`; a nonzero count is a layout
defect or a broken internal link and exits 1.

## Manifest stamping

The zipped `PowerTools.manifest` is not a verbatim copy. The script rewrites it
in-memory before archiving:

- `version` is set to the release version (from the tag), so the Add-Ins dialog
  reports the real release number regardless of what the repo manifest says.
- `editEnabled` is set to `false`, marking the shipped add-in as non-editable
  in Fusion's Add-Ins dialog.

All other fields, key order, and formatting are preserved, and the manifest in
the repository is never modified.

## Dry runs and local builds

**CI dry run:** trigger the `Release` workflow manually (**Actions › Release ›
Run workflow**). It builds the zip from the selected branch and uploads it as a
workflow **artifact** — nothing is attached to any release.

**Local build:**

```bash
python tools/release/build_release.py                    # version from the manifest
python tools/release/build_release.py --version v1.2.0   # version from a tag label
```

The zip lands in `dist/` (git-ignored). Note the file list comes from
`git ls-files`, so uncommitted new files are not included — commit (or at least
`git add`) first if you are testing a change to the shipped set.

## Changing what ships

The exclusion rules live at the top of `tools/release/build_release.py`:

- `EXCLUDED_DIRS` — tracked directories that never ship (prefix match).
- `EXCLUDED_FILES` — individual tracked files that never ship (exact match).
- `EXCLUDED_GLOBS` — `fnmatch` patterns for design sources inside `resources/`.
- `FORBIDDEN_FILES` — machine-local files that abort the build if tracked.

When you change them, update the ship/strip cases in
`tests/test_release_build.py` in the same commit — the test suite is what keeps
the shipped set intentional.

---

*Copyright © 2026 IMA LLC. All rights reserved.*
