# Reference Manager — Architecture

[← Reference Manager guide](../Reference%20Manager.md)

| | |
|---|---|
| **Command ID** | `PTAT_refmanager` |
| **Registry** | group `assembly` (`Assembly`); **ships disabled** — listed in `settings_store.DEFAULT_DISABLED_COMMANDS`, so it starts only after the user enables it in Preferences ([settings_store](architecture.md#settings_store)) |
| **UI location** | Quick Access Toolbar (`ui.toolbars.itemById("QAT")`), `qat.controls.addCommand(cmd_def, "PTAT_getandupdate", True)` — before the Get and Update button (`isBefore = True`) |
| **Files** | `commands/refmanager/entry.py`; `resources/` (button icons) |
| **Shared helpers** | [`ptutil.add_handler`](architecture.md#event_utils); [`ptutil.log`, `handle_error`](architecture.md#general_utils) |
| **Tests** | `tests/test_command_contract.py` |

## Purpose

Puts Fusion's own Reference Manager one click away on the QAT. The command has no logic of its own: it executes the built-in `ReferenceManagerCmd` command definition, and Fusion's dialog does the reviewing, updating and version selection. It is a thin launcher, and it ships disabled.

## How it is wired

- `start()`: `addButtonDefinition` with the `resources/` icon folder, attaches `command_created`, adds the control to the QAT anchored on `PTAT_getandupdate`. Get and Update also ships disabled, so the anchor is frequently absent; what Fusion does with a missing `positionID` is not verified on this branch. `stop()` deletes the QAT control and the definition.
- `command_created(args)`: attaches `command_execute` and `command_destroy` to the new command and returns. It builds no inputs, so Fusion auto-executes the command.
- `command_execute(args)`: `ui.commandDefinitions.itemById("ReferenceManagerCmd").execute()`; any exception goes to [`ptutil.handle_error`](architecture.md#general_utils) with a message box. Because the work is in `execute` rather than `commandCreated`, it depends on Fusion firing `execute` for an input-less command — which it does not do with no document open ([rule 1](../dev/lessons.md)); in that state the built-in command is never invoked and nothing is reported.
- `command_destroy(args)`: clears `local_handlers`. It fires when this launcher command ends, independently of Fusion's Reference Manager dialog, which lives on as a separate command.

## Data and state

None beyond `local_handlers`. No files, settings keys, custom events or temp files.

## Diagram

None — a single call, described above.

## Tests

- `tests/test_command_contract.py` — registry/description/ID contract; `commands/refmanager/entry.py` is the pinned example of a cross-module anchor literal (`PTAT_getandupdate`) in `test_the_literal_walk_can_see_cross_module_anchors`.

`entry.py` is Fusion-bound and is not exercised by the suite; nothing here is verified in Fusion on this branch except by the AST guards in `tests/test_command_contract.py` and `tests/test_command_abort.py`, which import it under the `adsk` stub. The icon set (which includes a non-standard `32x32-normal.png`) is not pinned in `tests/test_command_icons.py`.

---

*Copyright © 2026 IMA LLC. All rights reserved.*
