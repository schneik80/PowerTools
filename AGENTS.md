# AGENTS.md — start here

Entry point for AI coding agents (Claude Code loads it through `CLAUDE.md`).
It is deliberately short: the rules below are the ones this repo has already
paid for once, and every line links to the long form. Read the matching
`.claude/rules/*.md` before editing the paths it covers, even if your tool
does not load them automatically.

## What this is

- **PowerTools** is a single Autodesk Fusion add-in (Python) consolidating
  ~52 commands behind one entry point (`PowerTools.py`), one registry
  (`command_registry.py`), one settings store (`settings_store.py`) and one
  shared helper package (`lib/ptAddInUtils`, imported as `ptutil`).
- It runs inside **Fusion's bundled Python 3.14**, has **no runtime
  dependencies**, and `import adsk` resolves **only inside Fusion**. Tests
  stub `adsk` and cover pure logic only.
- Fusion exists on **macOS and Windows only**. A Linux checkout can lint,
  test, build the release zip and the PDF, but can never run the add-in.
  Say "not yet exercised in Fusion" when that is true of your change.

## Environment and commands

```bash
# one-time (no venv is committed; the pin must match .github/workflows/ci.yml)
python3 -m venv .venv && .venv/bin/pip install "ruff==0.15.20" "pytest>=8.0"

# the four CI gates -- run them all before every commit
ruff format .            # (CI runs `ruff format --check .`)
ruff check .
python -m pytest -q      # expect "N passed, a few skipped" (Fusion-only checks skip off-Fusion)
python tools/pandoc/build_readme_pdf.py --check   # README.pdf built from this README.md?

python tools/release/build_release.py --version v0.0.0-test   # release dry run -> dist/
python tools/pandoc/build_readme_pdf.py                       # after any README.md edit
python commands/<cmd>/resources/generate_icons.py             # icon sets
```

- `.debug` (git-ignored marker in the repo root) turns on `ptutil.log` and the
  debugpy server. Without it **logging is a no-op**.
- `.claude/settings.json` is the shared permission allowlist; put personal
  overrides in `.claude/settings.local.json` (git-ignored).
- Skills: `build-readme-pdf`, `generate-icons` (`.claude/skills/`).

## Non-negotiables

Each one has cost a fix already; hashes are `git show`-able and the long form is
[`docs/dev/lessons.md`](docs/dev/lessons.md).

1. **`execute` never fires with no document open.** A command with no
   `CommandInputs` does its work in `commandCreated` (`f18b911`, `11cfc51`).
2. **Never loop `adsk.doEvents()` inside a handler; never `time.sleep()` on the
   UI thread.** Use `ptutil.pump_events_for()` (`ce4e768`, `f0ff1af`).
3. **Re-acquire document/design handles after any pumped wait and check
   `isValid` before closing** -- stale handles fault natively, not with an
   exception (`a1d22e1`, `11cfc51`).
4. **Custom graphics only in `executePreview`**; read
   [Custom graphics that stay painted](docs/dev/Custom%20graphics%20that%20stay%20painted.md)
   first (`b3bed5f`).
5. **Read selections with `ptutil.capture_selections()` in `inputChanged`**,
   never from `execute` (`a91da41`).
6. **Never close a document inside a command event** (`11cfc51`).
7. **Off the main thread, call only `app.fireCustomEvent`**; ignore its return
   value; starting a command from a palette event needs `threading.Timer` ->
   custom event (`c440ad3`, `266e2c2`).
8. **`app.data.activeProject` raises when no project is in context** -- use
   `cache_utils.get_active_project()`; exceptions in `incomingFromHTML` are
   swallowed silently (`7535954`).
9. **Fusion IDs use `_`, never `-`.** Renaming a `CMD_ID` orphans user QAT
   pins; renaming a registry key needs `settings_store.RENAMED_COMMANDS`
   (`6789216`, `7dee722`).
10. **Never delete a built-in tab/panel; make `start()`/`stop()` idempotent;
    one tab per control** (`3b92f3f`).
11. **Never hardcode Autodesk paths or unpublished workspace IDs** -- probe
    candidates and log what resolved (`af05499`, `fusion_recents.py`).
12. **`lib/ptAddInUtils/__init__.py` import order is load-bearing, and
    `config.py` imports ptutil before defining `DEBUG`** -- no import-time
    reads of config flags (`0b179cd`, `018f0c7`).
13. **Pure logic lives in an `adsk`-free module with tests** (`logic.py`,
    `pathgraph.py`, `catalog.py`). A plausible wrong number is worse than an
    error (`c8c0382`, `b3bed5f`).
14. **Cross-platform Python:** `.casefold()` explicitly (`normcase` is
    Windows-only); OR permission bits; `os.access` lies on Windows shares;
    `except Exception:` never bare (`4cb4901`, `19ac0f7`, `14f42ca`).
15. **Every command change keeps the contract**: registry entry with the exact
    doc filename, `CMD_Description` (exact casing, ASCII, text from the docs),
    `docs/<Doc>.md` + `docs/arch/<Doc>.md` + `docs/arch/index.md` + README row,
    generated icons pinned in `tests/test_command_icons.py` (`aa6802e`, `e263d4e`).
16. **`ruff format .` before every commit** -- formatting is a hard CI gate;
    pure reformat commits go in `.git-blame-ignore-revs` (`ef424c6`, `ef14b11`).
17. **`README.pdf` is rebuilt in the same commit as `README.md`** -- CI and a
    pytest case check a SHA stamp in the PDF against the Markdown (`48722db`,
    `28188f7`).
18. **The release zip is `git ls-files` minus explicit exclusions** in
    `tools/release/build_release.py`; anything newly tracked ships unless
    excluded there, and `tests/test_release_build.py` moves with it (`1cb6d3e`).
19. **Stdlib only** -- in the add-in and in `tools/` (Fusion's Python has no
    pip, no Pillow; CI installs nothing but ruff and pytest).
20. **Never call `args.command.doExecute()` inside `commandCreated`** -- it
    re-enters the command manager on a half-built command and segfaults
    Fusion. Bail out with `commands/_command_abort.abort_before_dialog()`,
    `consume_abort()` in `execute`, `clear_abort()` in `destroy`; an AST test
    enforces it (`14871d7`, `a90be46`, `5bae0e3`).

## Where to look

Full index: [`docs/dev/codebase-map.md`](docs/dev/codebase-map.md).

| Task | Open |
|---|---|
| Add / rename a command | `command_registry.py`, `settings_store.py`, `.claude/rules/commands-registry.md` |
| How a command is wired | `commands/closealldocuments/` (simple), `commands/measurepath/` (dialog + graphics + `pathgraph.py`), `commands/assemblypalette/` (palette) |
| Shared helpers before writing new ones | `lib/ptAddInUtils/` index in the codebase map |
| QAT File-menu placement, retries | `commands/preferences/entry.py`, `commands/openrecent/entry.py` |
| Timer -> custom event deferral, future polling | `commands/assemblypalette/entry.py`, `commands/teamaddins/entry.py` |
| Palette page <-> Python RPC | `commands/preferences/entry.py` + `resources/html/app.js` |
| Long save/close runs, crash mitigations | `commands/bottomupupdate/entry.py` |
| Bailing out of a command before its dialog | `commands/_command_abort.py`, `commands/changecyclecolor/entry.py` |
| Heavy geometry in an `adsk`-free solver | `commands/flattensurface/flatten.py`, `docs/dev/Flatten Surface solver.md` |
| Test harness | `tests/conftest.py`, `.claude/rules/tests-ci.md` |
| Release, PDF, icons | `tools/`, `.claude/rules/docs-release.md`, the two skills |
| Fusion quirks, by symptom | `docs/dev/lessons.md`, `.claude/rules/fusion-api.md` |

## Working conventions

- **Commits**: `Area: imperative summary` (e.g. `Preferences: open the palette
  from commandCreated, not execute`) or a plain imperative line; a prose body
  that explains *why*, cites the commits it corrects or builds on, and ends
  with `Closes #N` when applicable. A `Co-Authored-By:` trailer is customary
  for agent-written commits. Do not commit or push unless asked; **"commit and
  sync" means commit and `git push` to `main`.**
- **Verify API names against the official Fusion reference**, not memory; the
  commit says which properties were verified.
- **Read the DEBUG log / crash report before theorising.** Two identical-looking
  "Preferences needs a document" bugs had different root causes.
- **Docs are part of the change**, not a follow-up. Descriptions and user text
  come from `docs/`, not invention.
- **When the user corrects you on something durable, add it to
  `docs/dev/lessons.md`** (and to a rule file if it is path-specific) in the
  same change.

## Documentation map

| Doc | Read it for |
|---|---|
| [`docs/dev/index.md`](docs/dev/index.md) | Setup, layout, tooling, `.debug`, doc map |
| [`docs/dev/codebase-map.md`](docs/dev/codebase-map.md) | Where everything is; command table; ptutil index; stale items |
| [`docs/dev/lessons.md`](docs/dev/lessons.md) | The mistakes ledger (long form of the rules above) |
| [`docs/arch/architecture.md`](docs/arch/architecture.md) | Lifecycle, shared access points, execution model, `config.py` |
| [`docs/arch/<Command>.md`](docs/arch/index.md) | Per-command architecture notes |
| [`docs/dev/debugging.md`](docs/dev/debugging.md) | Attaching VS Code / Zed to Fusion (macOS-centric) |
| [`docs/dev/release.md`](docs/dev/release.md) | What ships, what is stripped, how a release is cut |
| [`docs/dev/Custom graphics that stay painted.md`](docs/dev/Custom%20graphics%20that%20stay%20painted.md) | Drawing in the viewport |
| [`docs/dev/Insert and position a component from a palette.md`](docs/dev/Insert%20and%20position%20a%20component%20from%20a%20palette.md) | Starting Fusion commands from a palette |
| [`docs/dev/Flatten Surface solver.md`](docs/dev/Flatten%20Surface%20solver.md) | The worked example of a pure-Python geometry solver behind a command |
| `.claude/rules/*.md` | Path-scoped checklists: `fusion-api`, `commands-registry`, `tests-ci`, `palettes-html`, `docs-release` |
