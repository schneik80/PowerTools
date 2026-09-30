# Toggle Data Pane — Architecture

[← Toggle Data Pane guide](../Toggle%20Data%20Pane.md)

| | |
|---|---|
| **Command ID** | `CMD_ID = "PTND_toggledata"` is the module's contract constant, but the button definition Fusion sees is registered as `_navBarBtnID = "NavBarBtn"`; `CMD_ID` is not used by any control |
| **Registry** | module `datatoggle`, group `document` (`Document Tools`); enabled by default; not beta |
| **UI location** | Navigation Toolbar (`ui.toolbars.itemById("NavToolbar")`), appended at the end (`addCommand(cmd_def, "", False)`); icon from `resources/` |
| **Files** | `commands/datatoggle/entry.py`; `resources/` (16/32/64 px light + dark icons) |
| **Shared helpers** | [`ptutil.add_handler`](architecture.md#event_utils); [`ptutil.log`, `handle_error`](architecture.md#general_utils) |
| **Tests** | `tests/test_command_contract.py` only |

## Purpose

Opens or closes the Data Panel with one click from the Navigation Toolbar, where Fusion otherwise offers only the QAT grid button or a keyboard shortcut. It reads `app.data.isDataPanelVisible` and runs whichever of Fusion's two internal commands flips the state.

## How it is wired

- `start()`: `ui.commandDefinitions.itemById("NavBarBtn")` first; only when that is `None` does it `addButtonDefinition("NavBarBtn", CMD_NAME, CMD_Description, ICON_FOLDER)`. Then `ptutil.add_handler(cmd_def.commandCreated, command_created)` and `navToolbar.controls.addCommand(cmd_def, "", False)`.
- `stop()`: deletes the toolbar control. The definition is looked up but the deletion is behind `if not navBarBtnCmdDef:`, so an existing definition is never deleted (and a missing one would raise `AttributeError` on `None.deleteMe()`). The `itemById` check in `start()` is what keeps a stop/start cycle from failing on a duplicate id. `stop()` also declares `global _handlers`, a name that does not exist in the module.
- `command_created(args)`: does the work directly — `app.data.isDataPanelVisible` true → `ui.commandDefinitions.itemById("DashboardModeCloseCommand").execute()`, otherwise `DashboardModeOpenCommand.execute()`. Exceptions → `ptutil.handle_error(CMD_NAME, show_message_box=True)`. No `CommandInputs`, no `execute` or `destroy` handler; this is the [acting-from-commandCreated](architecture.md#acting-from-commandcreated-when-there-are-no-inputs) shape, which is why the button works with no document open.

## Data and state

`local_handlers` only. No disk cache, no settings keys, no custom events.

## Diagram

None — one branch on `isDataPanelVisible`.

## Tests

- `tests/test_command_contract.py` — registry row, `CMD_Description`, docs pair; the literal `PTND_toggledata` is checked for the Fusion ID shape. `NavBarBtn` carries no `PT` prefix and is not covered by the ID checks.

`entry.py` is Fusion-bound and is not exercised by the suite; nothing here is verified in Fusion on this branch except by the AST guards in `tests/test_command_contract.py` and `tests/test_command_abort.py`, which import it under the `adsk` stub. The icon set is not pinned in `tests/test_command_icons.py`.

---

*Copyright © 2026 IMA LLC. All rights reserved.*
