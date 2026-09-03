---
paths:
  - "tests/**"
  - "pyproject.toml"
  - ".github/**"
---

# Tests and CI

CI (`.github/workflows/ci.yml`) has four hard gates on every push:
`ruff format --check .`, `ruff check .`, `python -m pytest -q`, and
`python tools/pandoc/build_readme_pdf.py --check` (README.pdf carries a SHA
stamp of the README it was built from). Run them all locally before committing
-- two commits once landed unformatted and every CI run failed until a
follow-up reformat (ef424c6); the PDF went stale twice (48722db, 28188f7).

## Toolchain

- No venv is committed. Bootstrap:
  `python3 -m venv .venv && .venv/bin/pip install "ruff==0.15.20" "pytest>=8.0"`.
- **The ruff pin in `ci.yml` must equal the version that formatted the tree**
  (ef14b11). Bump both together and verify `ruff format --check .` first.
- Mechanical reformat commits are isolated and listed in
  `.git-blame-ignore-revs` (0de55c8, 89f298d, ef424c6).
- `ruff` excludes `cache/`, `settings/`, `**/resources/**`, `docs/`. It only
  sees `.py` files, so Markdown/JSON under `.claude/` or `docs/` is inert.
- `I001` is disabled for `lib/ptAddInUtils/__init__.py` on purpose (import
  order is load-bearing). `B018` is kept because it catches `adsk.doEvents`
  without parentheses.

## How the suite runs without Fusion

`tests/conftest.py`:

- Registers a synthetic package `PowerTools` (the repo folder name) whose
  `__path__` is the repo root. This is needed because the root `PowerTools.py`
  entry module would otherwise shadow the directory. Import add-in modules as
  `importlib.import_module(f"{PT_PKG}.settings_store")`,
  `f"{PT_PKG}.commands.refresh.logic"`, etc.
- Installs a meta-path finder that fabricates any `adsk`/`adsk.*` module as a
  `MagicMock`. Tests therefore cover **pure logic only**; nothing here proves
  behaviour inside Fusion. Say "not yet exercised in Fusion" in the commit
  when that is true.
- A module with zero `adsk` and zero package-relative imports can be loaded
  straight off disk with `importlib.util.spec_from_file_location`
  (`test_measurepath_pathgraph.py`, `test_release_build.py`).

## What a change must bring

- New feature -> `adsk`-free logic module + `tests/test_<module>_<topic>.py`.
  Prefer tests that pin the bug you just fixed, especially ones that produced a
  plausible wrong answer rather than a crash (b3bed5f, c8c0382).
- Asset-contract tests must move with their assets: `test_command_icons.py`
  (icon sets), `test_release_build.py` (ship/strip list -- update in the same
  commit as `tools/release/build_release.py`), `test_settings_validate.py` and
  `test_settings_command_sets.py` (settings schema / sets),
  `test_readme_pdf_build.py` (PDF stamp -- rebuild the PDF after a README edit).
- `test_command_abort.py::test_no_command_created_calls_do_execute` is an AST
  guard over `commands/`; if it fails you added a `doExecute` call to a
  `commandCreated` handler -- use `_command_abort` instead (a90be46).
- Cross-platform: CI runs on Linux; `os.path.normcase` only folds case on
  Windows, so casefold explicitly (4cb4901); OR permission bits instead of
  assigning them (19ac0f7).
- Report the real result: the suite ends "N passed, N skipped" -- the skips
  are tests that need a real Fusion install and skip on CI and on Linux.
