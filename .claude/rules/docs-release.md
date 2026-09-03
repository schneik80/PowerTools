---
paths:
  - "docs/**"
  - "README.md"
  - "README.pdf"
  - "tools/**"
---

# Docs and release

## Documentation contract

- Every registered command has **two** docs with the **same filename**:
  `docs/<Doc>.md` (end user; ships in the zip; linked from the Preferences
  palette via `DOCS_BASE_URL`) and `docs/arch/<Doc>.md` (developer; stripped
  from the zip). Add a row in `docs/arch/index.md` and in the README command
  table. Known gaps: `docs/arch/Animation Named View.md` and
  `docs/arch/Set Up Shared Add-ins Folder.md` do not exist yet.
- **`README.pdf` is regenerated in the same commit as any `README.md`
  change** (48722db). Use skill `build-readme-pdf`; never `--skip-audit` to
  get green. Each build stamps `readme-sha256:<hash>` into the PDF Subject;
  `build_readme_pdf.py --check` verifies it (CI gate + pytest case) and
  `build_release.py` runs `--if-stale` before zipping and aborts if it cannot
  rebuild (28188f7).
- In README, `---` is a print page break (`hr-to-pagebreak.lua`); the three
  command-table headers must stay identical across tables so
  `table-widths.lua` pools their widths.
- Developer recipes live in `docs/dev/` (`index.md`, `debugging.md`,
  `release.md`, `lessons.md`, `codebase-map.md`, the two API recipes). When a
  fix teaches a Fusion rule, add it to `docs/dev/lessons.md` and, if it fits,
  to `docs/arch/architecture.md` (f18b911 did both).
- Copyright footer on docs: `*Copyright © 2026 IMA LLC. All rights reserved.*`
  Python files carry the Industrial Machine Arts header; the three
  Autodesk-sample-derived ptutil modules keep Autodesk's notice (9b416cb).

## Release zip (`tools/release/build_release.py`)

- File list = `git ls-files` minus `EXCLUDED_DIRS` (`tests/`, `tools/`,
  `.github/`, `.claude/`, `docs/arch/`, `docs/dev/`), `EXCLUDED_FILES`
  (`.gitignore`, `.git-blame-ignore-revs`, `pyproject.toml`, root `hub.json`,
  `AGENTS.md`, `CLAUDE.md`), `EXCLUDED_GLOBS` (icon design sources).
  **Anything newly tracked at the root or in a new top-level folder ships
  unless excluded here.**
- `FORBIDDEN_FILES` (`.debug`, `.env`, `settings/preferences.json`) abort the
  build if they ever become tracked.
- Exclusion changes and `tests/test_release_build.py` land in the same commit.
- Manifest is stamped in memory (version from the tag, `editEnabled=false`);
  the repo manifest is never edited for a release.
- Dry run: `python tools/release/build_release.py --version v0.0.0-test`
  (reads `git ls-files`, so `git add` new files first), then
  `unzip -l dist/*.zip`. `dist/` is git-ignored.
- Root `hub.json` is a stale org copy; the live one is `cache/hub.json`.

## Tools

- All of `tools/` is stdlib-only and shells out (`git`, `pandoc`, `xelatex`);
  keep it that way -- nothing third-party is installed in CI or in Fusion.
- `tools/icons/iconkit.py` is loaded by path from each
  `commands/*/resources/generate_icons.py` (skill `generate-icons`).
