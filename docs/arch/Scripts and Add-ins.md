# Scripts and Add-ins — Architecture

[← Scripts and Add-ins guide](../Scripts%20and%20Add-ins.md)

| | |
|---|---|
| **Command ID** | `PT_scriptsmanager` |
| **Registry** | group `tools` (`Tools`); enabled by default |
| **UI location** | QAT File dropdown (`FileSubMenuCommand`), inserted directly before `PT_preferences` (`controls.addCommand(cmd_def, "PT_preferences", True)`); appended to the dropdown when that anchor is absent |
| **Files** | `commands/scriptsmanager/entry.py` only; `ICON_FOLDER = ""`, so the item renders Fusion's default menu glyph |
| **Shared helpers** | [`ptutil.add_handler`](architecture.md#event_utils); [`ptutil.handle_error`](architecture.md#general_utils). The File dropdown is resolved by a local `_qat_file_dropdown()` (`ui.toolbars.itemById("QAT")` → `DropDownControl.cast(controls.itemById("FileSubMenuCommand"))`), the same lookup as [`ptutil.get_qat_file_dropdown`](architecture.md#ui_utils). |
| **Tests** | `tests/test_command_contract.py` |

## Purpose

Puts Fusion's built-in Scripts and Add-Ins manager (`ScriptsManagerCommand`, otherwise Shift+S or Utilities → Add-Ins) one click away in the File menu, directly above PowerTools Preferences. It is a pure launcher with no dialog of its own; the constraint is that it must work on the start screen with no document open, so it fires the target from `commandCreated`.

## How it is wired

- `start()`: deletes any existing `PT_scriptsmanager` definition, then `addButtonDefinition(CMD_ID, CMD_NAME, CMD_Description, "")`; wires `commandCreated` → `command_created`. If the File dropdown resolves and does not already hold `CMD_ID`: `controls.addCommand(cmd_def, "PT_preferences", True)` when the Preferences control exists, else `controls.addCommand(cmd_def)`. Preferences is infrastructure that `commands/__init__.py` starts before any registered command, so the anchor exists on a normal start.
- `stop()`: deletes the control from the File dropdown, then the definition.
- `command_created(args)`: adds no inputs and does the whole job ([acting from `commandCreated`](architecture.md#acting-from-commandcreated-when-there-are-no-inputs)) — `ui.commandDefinitions.itemById("ScriptsManagerCommand")`; found → `target.execute()`; not found → message box "The Scripts and Add-Ins manager is not available in this version of Fusion."; any exception → `ptutil.handle_error(CMD_NAME)`. The launcher command then terminates on its own; no `execute` handler is wired.

When the `tools` group or the command is disabled in Preferences, `commands/__init__.py` skips `start()` and the menu item is not added.

## Data and state

None. `local_handlers` exists but is never appended to.

## Diagram

None: the flow is one lookup and one `execute()`.

## Tests

- `tests/test_command_contract.py` — registry/doc/description contract; `PT_scriptsmanager` is checked against the ID shape; the literal walk self-check asserts that `commands/scriptsmanager/entry.py` is where the foreign anchor `PT_preferences` is seen, which guards the anchor against a rename.

Not covered: `entry.py` is Fusion-bound and is not exercised by the suite; nothing here is verified in Fusion on this branch except by the AST guards in `tests/test_command_contract.py` and `tests/test_command_abort.py`, which import it under the `adsk` stub. There is no icon set to pin.

---

*Copyright © 2026 IMA LLC. All rights reserved.*
