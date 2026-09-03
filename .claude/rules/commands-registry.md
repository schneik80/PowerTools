---
paths:
  - "command_registry.py"
  - "settings_store.py"
  - "commands/__init__.py"
  - "commands/_ui_bootstrap.py"
  - "commands/*/entry.py"
  - "commands/*/__init__.py"
---

# Commands and the registry

`command_registry.py` is the single source of truth: grouping, exact doc
filename, beta tier, and whether a command owns a Preferences settings
section. `commands/__init__.py` derives imports, start order, and start-up
gating from it; `settings_store.py` derives `settings/preferences.json`
defaults from it. **The `module` key is both the folder name and the user's
settings key.**

## Adding a command -- checklist (all in one change)

1. `commands/<module>/__init__.py` + `entry.py` with `start()`/`stop()`,
   `CMD_ID` (`PT*_<module>`, underscores only), `CMD_NAME`, and
   **`CMD_Description`** -- exact casing; an all-caps `CMD_DESCRIPTION` is
   silently ignored by the palette and the button (aa6802e). Keep the text
   ASCII (it doubles as a Fusion tooltip) and take it from the user doc.
2. Registry entry `_cmd("<module>", "<Doc Name>.md", beta=?, settings=?)` in
   the right group. Doc filename is **not** derived from `CMD_NAME`
   (`sketchfix` -> `SketchFix.md`).
3. Docs pair: `docs/<Doc Name>.md` (user guide) and `docs/arch/<Doc Name>.md`
   (architecture note), a row in `docs/arch/index.md`, and a row in the README
   command table (then rebuild `README.pdf` -- skill `build-readme-pdf`).
4. Icons: `resources/16x16.png`, `32x32.png`, `64x64.png` (+ `-dark`,
   `-disabled`) drawn with skill `generate-icons`; pin in
   `tests/test_command_icons.py`. Never copy another command's PNGs.
5. If it has settings: `settings_store.COMMAND_SETTING_DEFAULTS[<module>]`,
   `has_settings=True`, and a `CMD_SECTIONS` entry in
   `commands/preferences/resources/html/app.js`. Ship-disabled commands go in
   `DEFAULT_DISABLED_COMMANDS` (112d08d).
6. Pure logic in an `adsk`-free module (`logic.py`, `pathgraph.py`,
   `catalog.py`) with `tests/test_<module>_*.py`. `entry.py` holds only Fusion
   contact.
7. Preferences changes apply on the next Fusion restart -- the gating runs in
   `commands.start()` only. Say so in the docs if relevant.
8. Precondition failures before the dialog: `_command_abort.abort_before_dialog()`
   + return with no inputs; never `args.command.doExecute()` (segfault,
   14871d7). `consume_abort()` in `execute`, `clear_abort()` in `destroy`.
9. Commands only usable together go in `settings_store.COMMAND_SETS` (one
   Preferences checkbox; members resolve through the lead's flag; members must
   share the lead's group -- `tests/test_settings_command_sets.py`) (6c554d5).

## Renaming a command or folder

- Add `old: new` to `settings_store.RENAMED_COMMANDS`, or every user's
  enable/disable state for it silently resets (7dee722).
- Update every cross-reference: registry, docs pair, `docs/arch/index.md`,
  README, tests, other commands that anchor on its control ID
  (`positionID`), `recents_utils`/`fusion_recents` if it touches recents.
- Changing `CMD_ID` orphans saved QAT/ribbon pins until Fusion restarts; note
  it in the commit (6789216, 7dee722).
- Keep the folder top-level under `commands/`; a nested folder broke the
  relative imports and the whole add-in failed to load (14abc78).

## Start order and placement constraints (encoded in the registry order)

- `insertSTEP` before `assemblypalette` (palette button anchors on it).
- Share commands keep their relative order (QATRight flyout positions).
- `scriptsmanager` anchors directly before `PT_preferences`; `preferences` is
  infrastructure and always starts first (not in the registry).
- `openrecent` probes several candidate IDs for the native Open control; the
  DEBUG log dumps the File dropdown's actual control IDs.
- Only two access points are shared and bootstrapped once
  (`_ui_bootstrap`): the Power Tools panel and the QAT File flyout lookup.
  Everything else is owned, created, and torn down by its command.

## Settings store discipline

- `load()` deep-merges stored values over registry defaults (stored wins), is
  memoised, and is cleared by `save()`. Writes go through
  `ptutil.write_json_atomic`.
- `validate()` rejects unknown top-level keys on import -- keep it strict.
- `settings/preferences.json` is git-ignored and machine-local; a fresh
  install regenerates it. Never commit it (270047d, `FORBIDDEN_FILES`).
