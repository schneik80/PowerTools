# Power Tools — Developer Guide

Developer-oriented documentation for working *on* the **Power Tools** add-in
for Autodesk Fusion: setting up a local development environment, the
repository layout, the tooling and its four CI gates, how the test suite runs
without Fusion, the `.debug` marker, and how to debug the add-in from VS Code
or Zed.

- New to the internals? Read [Architecture](../arch/architecture.md) first —
  lifecycle, the command-module pattern, the shared patterns, and the
  reference for every shared module.
- Looking for a file? [`codebase-map.md`](codebase-map.md).
- Looking for **end-user command guides**? See the [`docs/`](..) folder.
- Installing the add-in as a user? See the project [README](../../README.md).

---

## Contents

- [Prerequisites](#prerequisites)
- [Getting the source into Fusion](#getting-the-source-into-fusion)
- [Repository layout](#repository-layout)
- [The command-module pattern](#the-command-module-pattern)
- [Developer tooling and the CI gates](#developer-tooling-and-the-ci-gates)
- [Testing](#testing)
- [The `.debug` marker](#the-debug-marker)
- [Debugging](#debugging)
- [Documentation map](#documentation-map)

---

## Prerequisites

- **Autodesk Fusion** on **macOS** or **Windows 10/11**. Fusion ships its own
  bundled Python (currently **3.14**); the add-in runs inside that
  interpreter, not a system Python. There is no Linux client, so a Linux
  checkout can lint, test, build the release zip and the PDF, but never run
  the add-in.
- A local **Python 3.10+** for the developer tooling (lint, tests). The venv
  is not committed; the pin must match `.github/workflows/ci.yml`:

  ```bash
  python3 -m venv .venv && .venv/bin/pip install "ruff==0.15.20" "pytest>=8.0"
  ```

- **Git**; `pandoc` + `xelatex` only if you rebuild `README.pdf` locally.

The add-in has **no runtime dependencies** beyond Fusion's API and the
standard library, and so does everything under `tools/` (Fusion's Python has
no pip and no Pillow; CI installs nothing but ruff and pytest).
`pyproject.toml` configures developer tools *only* — Fusion loads
`PowerTools.py` and the `commands/` tree directly and ignores it.

## Getting the source into Fusion

Fusion loads an add-in from **any path on disk**; nothing needs to be copied
or symlinked under `.../API/AddIns/`.

1. Clone the repository (e.g. to `~/Source/PowerTools`).
2. In Fusion, open **Utilities › Add-Ins** (or press **Shift+S**).
3. On the **Add-Ins** tab, click the green **+** next to *My Add-Ins* and
   select the repository folder.
4. Select **PowerTools** in the list and click **Run** (enable **Run on
   Startup** to load it automatically each session).

Fusion remembers the absolute path and reloads from it every session. The
user-facing steps are in the [README Installation section](../../README.md#installation).

## Repository layout

| Path | Purpose |
|---|---|
| `PowerTools.py` | Add-in entry point. Fusion calls `run()` on start and `stop()` on stop; `run()` also starts the debugpy listener when `.debug` is present. |
| `PowerTools.manifest` | Fusion add-in manifest (id, author, `runOnStartup`, supported OS). Version and `editEnabled` are stamped at release time. |
| `config.py` | Flags, UI ids, workspace probes, hub config, palette ids, settings paths ([reference](../arch/architecture.md#config)). |
| `command_registry.py` | The single list of commands (55 `_cmd(` entries): group, exact doc filename, beta tier, settings section. No `adsk` import. |
| `settings_store.py` | `settings/preferences.json`: defaults derived from the registry, command sets, renames, import/validate. |
| `commands/` | One folder per command; `__init__.py` is the start/stop runner. `_ui_bootstrap.py`, `_command_abort.py`, `_inspect_panels.py` are shared infrastructure; `preferences/` is the always-on Preferences command; `partnumber_shared/` is a library. |
| `lib/ptAddInUtils/` | Shared helpers, imported as `ptutil` ([reference](../arch/architecture.md#libptaddinutils-ptutil)). |
| `cache/`, `settings/` | Runtime caches and the preferences file (both git-ignored). |
| `docs/` | End-user command guides (ship in the release zip). |
| `docs/arch/` | Architecture: `architecture.md` plus one note per command. Does not ship. |
| `docs/dev/` | This guide, the codebase map, the lessons ledger, debugging, release, and the API recipes. Does not ship. |
| `tests/` | Pytest suite; runs outside Fusion (see [Testing](#testing)). |
| `tools/` | `release/build_release.py`, `pandoc/build_readme_pdf.py`, `icons/iconkit.py`, `debug/update_debug_path.py`, `fusion_probes/` (see [Fusion probes](#fusion-probes)). |
| `pyproject.toml` | Ruff / mypy / pytest configuration (developer tooling only). |

## The command-module pattern

Every command lives in its own folder under `commands/<module>/`:

- `__init__.py` — copyright header only; the runner imports `entry` directly.
- `entry.py` — `CMD_ID`, `CMD_NAME`, `CMD_Description`, `start()` / `stop()`,
  and the Fusion event handlers (`command_created`, `command_execute`,
  `command_input_changed`, `command_execute_preview`, `command_destroy`, …).
- `resources/` — icons (with the `generate_icons.py` that drew them) and any
  palette HTML.
- optional adsk-free modules (`logic.py`, `pathgraph.py`, `flatten.py`, …)
  that hold everything worth a unit test.

`commands/__init__.py` creates the shared Power Tools panel once, starts
`preferences`, then walks `command_registry.iter_commands()` and starts each
enabled command; `stop()` reverses it. The full account, including the four
ways a command resolves its container and the handler table, is
[The command module](../arch/architecture.md#the-command-module) in the
architecture document. The patterns a new command is likely to need are
collected under
[Patterns commands share](../arch/architecture.md#patterns-commands-share):

- a command with no inputs works from `commandCreated`, because `execute`
  never fires with no document open;
- work that needs a later main-loop turn goes `threading.Timer` →
  `fireCustomEvent`;
- a precondition failure before the dialog uses `_command_abort`, never
  `doExecute`;
- waits go through `ptutil.pump_events_for`, and handles are re-acquired
  afterwards;
- anything that draws in the viewport reads
  [Custom graphics that stay painted](Custom%20graphics%20that%20stay%20painted.md)
  first;
- real geometry processing follows the
  [Flatten Surface solver](Flatten%20Surface%20solver.md): the mathematics in
  a module that imports no `adsk`, developed and tested without Fusion.

The contract a command must keep (registry entry, `CMD_Description`, docs
pair, arch index row, README row, pinned icons) is enforced by
`tests/test_command_contract.py` and listed in
[`.claude/rules/commands-registry.md`](../../.claude/rules/commands-registry.md).

## Developer tooling and the CI gates

`.github/workflows/ci.yml` runs on every push and enforces **four** hard
gates. Run all four before every commit:

```bash
ruff format --check .                              # formatting (fix with: ruff format .)
ruff check .                                       # lint: pyflakes, pycodestyle, isort, bugbear
.venv/bin/python -m pytest -q                      # -> "1711 passed, 8 skipped" (count grows)
python3 tools/pandoc/build_readme_pdf.py --check   # README.pdf carries the SHA of the README it was built from
```

Notes:

- **Formatting is standardized on `ruff format`** (double quotes, line length
  88). The ruff version that formats must be the version that gates: the pin
  in `ci.yml` is `0.15.20`; check `ruff --version` before trusting a
  `--check` result. Pure reformat commits go in `.git-blame-ignore-revs`;
  enable it once with `git config blame.ignoreRevsFile .git-blame-ignore-revs`.
- `ruff` and `pytest` exclude `cache/`, `settings/`, `**/resources/`,
  `docs/`, `.venv`, `.venv-dev`. `mypy` is configured but advisory, not a gate.
- The exact invocations differ per device (on the macOS dev box pytest lives
  only in `.venv`, `ruff` only on `PATH`; on the Windows box the CI-matching
  venv is `.venv-dev`). See [`.agent/environment.md`](../../.agent/environment.md).
- The skips in the pytest result are tests that need a real Fusion install
  or a specific platform; report the real "N passed, N skipped" line.

Other commands:

```bash
python3 tools/release/build_release.py --version v0.0.0-test   # dry run -> dist/ (git add first)
python3 tools/pandoc/build_readme_pdf.py                       # after any README.md edit
python3 commands/<cmd>/resources/generate_icons.py             # regenerate an icon set
python3 tools/debug/update_debug_path.py --list                # repoint .env/.zed at a Fusion build
```

This project does **not** use pull requests; branches merge straight to
`main`. See [`.agent/workflow.md`](../../.agent/workflow.md).

### Fusion probes

`tools/fusion_probes/` holds throwaway scripts that answer one runtime
question before a fix is decided -- for example whether an invisible
`documents.open` + `close` inside `command_execute` still faults
(`close_in_execute_probe.py`, issue #10). They import `adsk`, so they run only
inside Fusion: open one from **Utilities > Add-Ins > Scripts** (as a script,
not an add-in) on **both channels of both Fusion devices**, and record the
verdict per device + channel + build in the issue or `docs/dev/lessons.md`.
Each probe's docstring says what to run and what to record. They are dev-only
and are excluded from the release zip by the `tools/` rule in
`tools/release/build_release.py`.

## Testing

`import adsk` resolves only inside Fusion, so the suite runs against a stub
and proves **pure logic only**. Nothing in `tests/` is evidence that the
add-in behaves inside Fusion; say "not yet exercised in Fusion" when that is
true of a change.

### The harness (`tests/conftest.py`)

1. **A synthetic `PowerTools` package.** The repo root is pre-registered in
   `sys.modules` as a package named after the folder (`PowerTools`), the same
   name Fusion loads the add-in under. Modules that use relative imports are
   imported as `PowerTools.settings_store`,
   `PowerTools.commands.<module>.entry`, `PowerTools.lib.ptAddInUtils.<mod>`.
   Pre-registering avoids the root `PowerTools.py` shadowing the directory.
2. **An `adsk` stub.** A meta-path finder fabricates any `adsk` / `adsk.*`
   module on demand as a `MagicMock` package, so `import adsk.core`,
   `adsk.fusion`, `adsk.cam` and `adsk.core.Application.get()` all succeed
   and do nothing. Enum members are mocks, not integers — which is why
   `matchunits/logic.py` keys its tables by member *name*.
3. Modules with no `adsk` and no relative imports are loaded straight from
   their file path with `importlib.util.spec_from_file_location`
   (`test_measurepath_pathgraph.py`, `test_release_build.py`,
   `test_readme_pdf_build.py`).

### What the suite covers

| Kind | Tests | What is pinned |
|---|---|---|
| Per-command pure logic | `test_<module>_*.py` — see the Tests column of the [command table](codebase-map.md#command-table) | The adsk-free core of each command; the invariant, brute-forced where a plausible wrong number is the failure mode (`test_measurepath_pathgraph.py`) |
| Fusion-facing halves imported under the stub | `test_exportsysml_entry.py`, `test_flattensurface_entry.py`, `test_assemblypalette_*.py`, `test_bottomupupdate_*.py`, `test_dochistory_doc_switch.py`, `test_externalize_upload.py`, `test_changecyclecolor_abort.py`, `test_relateddata_cache.py` | Identity constants, structural guarantees (`test_no_execute_handler_is_registered`), arithmetic and state machines that live in `entry.py`, bounded loops shown to terminate |
| Registry-driven contract (AST) | `test_command_contract.py` | For every `command_registry` entry: `entry.py` exists and imports under the stub; `CMD_Description` present, ASCII, exact casing; `docs/<Doc>.md` and `docs/arch/<Doc>.md` exist; a row in `docs/arch/index.md`; a README link; literal `CMD_ID` in the `PT*_` underscore-only shape and unique; every `PT*_` literal in `commands/` resolves to a live `CMD_ID` or is in the allowlist (so a dead `positionID` fails); the `time.sleep` sites equal the recorded set. Every known gap is a `KNOWN_*` allowlist asserted **equal** to the tree — fixing a gap means shrinking the list |
| `doExecute` guard (AST) | `test_command_abort.py` | No `doExecute` inside any handler registered with `add_handler(<x>.commandCreated, …)` — resolved by registration, so oddly named handlers and `_make_*` factories are covered; plus the abort-flag lifecycle and self-checks that the walk still sees the three deliberate `doExecute` sites and at least 55 handlers |
| Shared modules | `test_pump_events.py`, `test_general_utils_debug_log.py`, `test_json_utils.py`, `test_recents_utils.py`, `test_fusion_recents.py`, `test_date_utils.py`, `test_config_hub.py`, `test_config_workspaces.py`, `test_settings_validate.py`, `test_settings_command_sets.py` | The pump cadence (fake clock), the debug-log writer, atomic JSON, recents merge and thumbnails, the native recents resolver, `loadHub` degradation, the Animation/Manufacture workspace fallbacks, preferences validation and the read-only-install path, command-set gating |
| Icon pin | `test_command_icons.py` | Every listed command ships 16/32/64 px, light/dark/disabled, 8-bit RGBA PNGs whose size matches the filename, and no two commands share byte-identical art |
| Release zip | `test_release_build.py` | Ship/strip decisions for representative paths, the forbidden-file guard, version parsing, manifest stamping, zip layout — `git` is mocked |
| README.pdf stamp | `test_readme_pdf_build.py` | The `readme-sha256:` stamp round-trips through a synthetic PDF, and `test_repo_readme_pdf_is_current` fails the moment `README.md` is edited without rebuilding the PDF |
| Security guards | `test_csv_injection.py`, `test_settings_validate.py`, `test_teamaddins_installer.py` | CSV formula neutralisation, unknown-key rejection on import, zip-slip and self-overwrite refusal |

### What is not covered

- Any behaviour that depends on Fusion: placement, events firing, dialogs,
  selections, custom graphics, saves, the cloud. `entry.py` modules are
  imported under the stub to prove they import and to read constants, not
  to exercise them.
- `_ui_bootstrap`, `_inspect_panels`, `event_utils`, `selection_utils`,
  `ui_utils`, `cache_utils`, `upload_utils` (the helper itself),
  `intent_icons`, `log_utils`, `attributes_utils`, and all of
  `partnumber_shared` except the literal/`time.sleep` walk.
- Platform-specific branches run on the current platform only unless the
  helper takes the platform as an argument (`changecyclecolor/fusion_install.py`
  does; see the ledger for the Windows-only bugs that motivated it).

### Writing a test

- Put the logic in an adsk-free module and import it as
  `PowerTools.commands.<module>.<mod>`; import `entry` only to check identity
  or structure.
- Pin the bug you fixed, especially one that produced a plausible wrong
  answer rather than a crash. For an unbounded loop, show the test hangs
  before the fix (`timeout 15 …; exit 124`) and terminates after.
- Asset-contract tests move with their assets: icons, the release exclusion
  list, the settings schema, the PDF stamp.
- Cross-platform: CI runs on `ubuntu-latest`; `.casefold()` explicitly, OR
  permission bits, take the platform as a parameter when a resolver has
  per-OS branches.

## The `.debug` marker

Create an empty file named **`.debug`** in the repository root to enable
developer **debug mode**. The marker is git-ignored and forbidden in the
release build, so it can never ship. Its presence is read when the add-in
loads (`config.DEBUG = os.path.isfile(...)`) and turns on two things:

1. **Logging** (`config.DEBUG`) — `ptutil.log(...)` writes to stdout,
   `cache/powertools-debug.log` (5 MB cap), the Fusion **Text Commands**
   window, and the Fusion log file for errors. Without the marker
   `ptutil.log()` is a no-op, and so is the trace from `handle_error()`;
   absence of a traceback is not evidence a handler ran.
2. **The attach-debug server** (`config.WAIT_FOR_DEBUGGER = DEBUG`) —
   `PowerTools.run()` starts an in-process `debugpy` listener on port 5678
   so an editor can attach. See [Debugging](#debugging).

Toggle debug mode by creating or deleting the file — no code change is
required. `lib/ptAddInUtils/log_utils.py` provides `open_live_log_viewer()`
for a platform-native tail (Console.app, PowerShell `Get-Content -Wait`).

## Debugging

Power Tools supports two debuggers:

- **VS Code** — via Fusion's built-in **Debug** button (Fusion injects
  `debugpy` on port 9000 and VS Code attaches).
- **Zed** — via the in-process `debugpy` server this add-in starts when the
  `.debug` marker is present (port 5678); Zed *attaches* to it.

Step-by-step instructions, the port map, the setup traps, how to repoint the
editor config after a Fusion update (`tools/debug/update_debug_path.py`), how
to read a CER crash report, and how to disable debugging for a shipping build
are in **[debugging.md](debugging.md)**. It is written against the macOS dev
box; the Windows paths differ.

## Documentation map

| Folder / file | Audience | Contents |
|---|---|---|
| [`docs/`](..) | End users | Per-command usage guides. |
| [`docs/arch/architecture.md`](../arch/architecture.md) | Developers | Lifecycle, the command module, shared patterns with diagrams, the shared-module reference, UI access points, state on disk. |
| [`docs/arch/<Command>.md`](../arch/index.md) | Developers | One architecture note per command, to one template (Purpose, wiring, data, diagram, tests, learnings). |
| [`codebase-map.md`](codebase-map.md) | Developers, AI agents | "Search less" index: command table (module → docs → adsk-free modules → tests), helper routing, UI access points, on-disk state, where-is-the-example-of, stale items. |
| [`lessons.md`](lessons.md) | Developers, AI agents | The mistakes ledger — Fusion API traps, tooling regressions and process rules, each citing its commit. |
| [`debugging.md`](debugging.md), [`release.md`](release.md) | Developers | Attaching a debugger; how a release is cut and what ships. |
| [Custom graphics that stay painted](Custom%20graphics%20that%20stay%20painted.md), [Insert and position a component from a palette](Insert%20and%20position%20a%20component%20from%20a%20palette.md) | Developers | Fusion API recipes. |
| [Flatten Surface solver](Flatten%20Surface%20solver.md), [Flatten Surface research](Flatten%20Surface%20research.md) | Developers | The worked example of a pure-Python geometry solver behind a command, and its method background. |
| [`/AGENTS.md`](../../AGENTS.md) + `.claude/` | AI agents | Entry point (loaded via `CLAUDE.md`), the non-negotiable rules, path-scoped `.claude/rules/`, and the `build-readme-pdf` / `generate-icons` skills. Tracked, but stripped from the release. |
| [`/.agent/`](../../.agent/README.md) | AI agents, developers | Tool-neutral guidance: the [symptom index](../../.agent/symptom-index.md), the [environment reference](../../.agent/environment.md) (per-device commands, Fusion paths, crash dumps, MCP), and the [workflow conventions](../../.agent/workflow.md). Tracked, stripped from the release. |

---

*Copyright © 2026 IMA LLC. All rights reserved.*
