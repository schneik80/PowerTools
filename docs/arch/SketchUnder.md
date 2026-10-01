# Sketch Under-Constrained — Architecture

[← Sketch Under-Constrained guide](../SketchUnder.md)

| | |
|---|---|
| **Command ID** | `PTPM_sketchunderconstrain` (note the spelling: no trailing `ed`) |
| **Registry** | group `partmodeling` (`Part Modeling`); enabled by default |
| **UI location** | Design workspace, **Sketch** tab (`SketchTab`), **Modify** panel (`SketchModifyPanel`); appended at the end of the panel, not promoted. Both containers are built in; `start()` finds the tab through `ui.allToolbarTabs`. |
| **Files** | `commands/sketchunderconstrained/entry.py`; `resources/` holds 16/32/64 px light and dark PNGs (no `generate_icons.py`) |
| **Shared helpers** | [`ptutil.add_handler`](architecture.md#event_utils); [`ptutil.log`, `ptutil.handle_error`, `ptutil.require_document`](architecture.md#general_utils); [`config.design_workspace`](architecture.md#config) |
| **Tests** | none module-specific (see [Tests](#tests)) |

## Purpose

Asks Fusion to highlight every under-constrained entity in the sketch being edited and shows the text the query returns. It is read-only: nothing is constrained or changed. The command has no inputs, so Fusion auto-executes it; the control lives on the Sketch tab, which is only shown while a sketch is in edit, so a document is always open when `execute` fires ([why that matters](architecture.md#acting-from-commandcreated-when-there-are-no-inputs)).

## How it is wired

- `start()`: `addButtonDefinition(CMD_ID, CMD_NAME, CMD_Description, ICON_FOLDER)`; `ptutil.add_handler(cmd_def.commandCreated, command_created)`; `ui.allToolbarTabs.itemById("SketchTab")` → `toolbarPanels.itemById("SketchModifyPanel")` → `controls.addCommand(cmd_def)`, `isPromoted = False`. A missing tab or panel raises a `ui.messageBox` and returns.
- `stop()`: resolves the panel through `ui.workspaces.itemById(config.design_workspace).toolbarPanels`, deletes the control and the definition. The trailing delete-if-empty branches for the panel and the tab cannot fire on built-in containers that still carry Fusion's own controls.
- `command_created(args)`: registers `execute` → `command_execute` and `destroy` → `command_destroy`. No inputs are built, so Fusion's default `isAutoExecute` runs the command immediately.
- `command_execute(args)`: [`ptutil.require_document(CMD_NAME, "design")`](architecture.md#document-preconditions) (`None` → it has shown "Sketch Under-constrained needs a design open. Open or create a design, then retry."; return). If `design.activeEditObject` is an `adsk.fusion.Sketch`, `under = app.executeTextCommand("Sketch.ShowUnderconstrained")`; the returned string is logged and shown with `ui.messageBox(under, CMD_NAME, 0, 2)`. Otherwise "No sketch is currently active.". Every message box in this handler is titled `CMD_NAME`. Exceptions go to `ptutil.handle_error(CMD_NAME, show_message_box=True)`.
- `command_destroy(args)`: clears `local_handlers`.

## Data and state

None beyond `local_handlers`. No settings keys, no files, no custom events.

## The text command

`Sketch.ShowUnderconstrained` is an undocumented Fusion text command. It both highlights the affected entities in the canvas and returns a summary string; the add-in relays that string verbatim and does no parsing of its own. The highlight is Fusion's, not custom graphics, so the [executePreview rule](../dev/Custom%20graphics%20that%20stay%20painted.md) does not apply.

## Diagram

None: one straight line (`command_created` → auto-execute → one text command → message box).

## Tests

- No module-specific test. `tests/test_command_contract.py` imports `entry.py` under the `adsk` stub and checks the `CMD_ID` shape, `CMD_Description`, the registered doc filename, this note, the arch index row and the README row; `tests/test_command_abort.py` scans `command_created` for `doExecute` calls.
- `entry.py` is Fusion-bound and is not otherwise exercised by the suite; nothing here is verified in Fusion on this branch except by those AST guards. The icon set is not pinned in `tests/test_command_icons.py`.

---

*Copyright © 2026 IMA LLC. All rights reserved.*
