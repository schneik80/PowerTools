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
  table. `tests/test_command_contract.py` asserts all four for every
  registered command; its `KNOWN_ARCH_GAPS` / `KNOWN_ARCH_INDEX_GAPS`
  allowlists are empty and must stay empty.
- **Developer and architecture docs describe the as-is state, not the
  journey.** No "was moved", "previously", "no longer", "now", commit hashes
  or dates in a design section. A mistake and what it taught goes either into
  `docs/dev/lessons.md` (with its commit hash -- that file is the ledger) or
  into a clearly headed `## Learnings` section at the end of the per-command
  note. Per-command notes follow one template (see `docs/arch/index.md`):
  header table, Purpose, How it is wired, Data and state, design sections, a
  diagram only where it shows more than the prose, Tests (what is and is not
  covered), optional Learnings. Shared helpers are linked to
  `docs/arch/architecture.md#shared-modules`, not re-explained.
- **Mermaid on GitHub:** `flowchart` and `sequenceDiagram` only; quote every
  label containing punctuation; real handler and function names in the real
  order; no C4 or `%%{init}` blocks.
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
  fix teaches a Fusion rule, add it to `docs/dev/lessons.md` and, if it
  changes how commands are written, to the matching pattern section of
  `docs/arch/architecture.md` (as a rule, not as a story).
- Copyright footer on docs: `*Copyright © 2026 IMA LLC. All rights reserved.*`
  Python files carry the Industrial Machine Arts header; the three
  Autodesk-sample-derived ptutil modules keep Autodesk's notice (9b416cb).

## Release zip (`tools/release/build_release.py`)

- File list = `git ls-files` minus `EXCLUDED_DIRS` (`tests/`, `tools/`,
  `.github/`, `.claude/`, `.agent/`, `docs/arch/`, `docs/dev/`), `EXCLUDED_FILES`
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
- `tools/debug/update_debug_path.py` repoints `.env` + `.zed/settings.json` at
  the newest *complete* Fusion build for a channel (most webdeploy hash dirs
  are partial deltas). Both targets are git-ignored per-device state; the
  macOS layout is verified, Windows is probed and unverified.
- `tools/icons/iconkit.py` is loaded by path from each
  `commands/*/resources/generate_icons.py` (skill `generate-icons`).
