# Local Recovery Save — Architecture

[← Local Recovery Save guide](../Recovery%20Save.md)

| | |
|---|---|
| **Command ID** | `PTND_autoSave` |
| **Registry** | module `autosave`, group `document` (`Document Tools`); enabled by default; not beta |
| **UI location** | QAT File dropdown (`ui.toolbars.itemById("QAT")` → `FileSubMenuCommand`), inserted after `PLM360SaveAsLatestOnQATCommand` (**Save as Latest**); text item, no icon |
| **Files** | `commands/autosave/entry.py` only (no `resources/`) |
| **Shared helpers** | [`ptutil.add_handler`](architecture.md#event_utils); [`ptutil.log`, `handle_error`](architecture.md#general_utils) |
| **Tests** | `tests/test_command_contract.py` only |

## Purpose

Writes a local recovery checkpoint for the active document without creating a cloud version, so work in progress can be checkpointed as often as wanted without raising out-of-date flags for everyone referencing the document. The command is a thin wrapper: it does nothing but run Fusion's internal `AutoSaveFilesCommand`.

## How it is wired

- `start()`: `ui.commandDefinitions.addButtonDefinition(CMD_ID, CMD_NAME, CMD_Description)` (no resource folder); `ptutil.add_handler(cmd_def.commandCreated, command_created)`; `fileDropDown.controls.addCommand(cmd_def, "PLM360SaveAsLatestOnQATCommand", False)`. The QAT and dropdown are read directly, without the `None` guard that [`ptutil.get_qat_file_dropdown`](architecture.md#ui_utils) provides; if either were missing `start()` would raise and `commands/__init__.start` would log it and move on.
- `stop()`: deletes the dropdown control and the definition.
- `command_created(args)`: registers `command_destroy`, then runs `ui.commandDefinitions.itemById("AutoSaveFilesCommand").execute()` directly; any exception → `ptutil.handle_error(CMD_NAME, show_message_box=True)`. There are no `CommandInputs` and no `execute` handler, so Fusion's auto-execute has nothing to run.
- `command_destroy(args)`: drops `local_handlers`.

The work runs in `commandCreated` because the control sits in the File dropdown, which exists with no document open, and `execute` never fires in that state (rule 1, #16). This is the first of the three File-dropdown commands converted under #25; it pilots launching a native Fusion command from `commandCreated` (the `scriptsmanager` pattern) before Export BOM and Export Mermaid follow.

## Data and state

`local_handlers` only. No disk cache, no settings keys, no custom events.

## Diagram

None — the flow is `command_created` → `AutoSaveFilesCommand.execute()`.

## Tests

- `tests/test_command_contract.py` — registry row, `CMD_Description`, docs pair, `CMD_ID` shape; imports `entry.py` under the `adsk` stub.

`tests/test_bottomupupdate_autosave.py` is unrelated: it covers `bottomupupdate`'s `_suspend_autosave` / `_restore_autosave` preference toggles, not this command. `entry.py` is Fusion-bound and is not exercised by the suite; nothing here is verified in Fusion on this branch except by the AST guards in `tests/test_command_contract.py` and `tests/test_command_abort.py`, which import it under the `adsk` stub.

---

*Copyright © 2026 IMA LLC. All rights reserved.*
