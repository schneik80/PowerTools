# Sketch Repair — Architecture

[← Sketch Repair guide](../SketchFix.md)

| | |
|---|---|
| **Command ID** | `PTPM_sketchfix` |
| **Registry** | group `partmodeling` (`Part Modeling`); enabled by default |
| **UI location** | Design workspace, **Sketch** tab (`SketchTab`), **Modify** panel (`SketchModifyPanel`); appended at the end of the panel, not promoted. Both containers are built in; `start()` finds the tab through `ui.allToolbarTabs`. |
| **Files** | `commands/sketchfix/entry.py`; `resources/` holds 16/32/64 px light and dark PNGs (no `generate_icons.py`) |
| **Shared helpers** | [`ptutil.add_handler`](architecture.md#event_utils); [`ptutil.log`, `ptutil.handle_error`](architecture.md#general_utils); [`config.design_workspace`](architecture.md#config) |
| **Tests** | none module-specific (see [Tests](#tests)) |

## Purpose

Runs Fusion's two built-in sketch-repair text commands against the sketch currently in edit mode and confirms with a message box. The command has no dialog and no inputs, so Fusion auto-executes it as soon as it is created. That is safe here because the control lives on the Sketch tab, which Fusion shows only while a sketch is being edited, so a document is always open when `execute` fires (see [acting from commandCreated when there are no inputs](architecture.md#acting-from-commandcreated-when-there-are-no-inputs) for why that matters elsewhere).

## How it is wired

- `start()`: `ui.commandDefinitions.addButtonDefinition(CMD_ID, CMD_NAME, CMD_Description, ICON_FOLDER)`; `ptutil.add_handler(cmd_def.commandCreated, command_created)`; `ui.allToolbarTabs.itemById("SketchTab")` → `toolbarPanels.itemById("SketchModifyPanel")` → `controls.addCommand(cmd_def)` with `isPromoted = False`. A missing tab or panel raises a `ui.messageBox` and returns, leaving the definition registered without a control.
- `stop()`: resolves the panel through `ui.workspaces.itemById(config.design_workspace).toolbarPanels`, deletes the control and the definition. Two further branches delete the panel if `controls.count == 0` and the tab if it has no panels; both containers are built in and always hold Fusion's own controls, so neither branch fires (rule 10 forbids it if they ever did).
- `command_created(args)`: registers `execute` → `command_execute` and `destroy` → `command_destroy` on `local_handlers`. No `CommandInputs` are added, so Fusion's default `isAutoExecute` runs the command immediately.
- `command_execute(args)`: casts `app.activeProduct` to `adsk.fusion.Design` (message box and return if it is not one). If `design.activeEditObject` is an `adsk.fusion.Sketch`, calls `app.executeTextCommand("sketch.repairsketch /3")` and then `app.executeTextCommand("sketch.repair")`, shows "Sketch repaired." and logs; otherwise shows "No sketch is currently active.". The text commands' return values are ignored. Exceptions go to `ptutil.handle_error(CMD_NAME, show_message_box=True)`.
- `command_destroy(args)`: clears `local_handlers`.

## Data and state

None beyond `local_handlers`. No settings keys, no files, no custom events.

## The two text commands

`sketch.repairsketch /3` and `sketch.repair` are undocumented Fusion text commands; the [user guide](../SketchFix.md) describes their observed effect (pass 1 removes tiny segments, pass 2 closes small gaps). The add-in does not read their output and cannot tell whether anything was repaired: the confirmation box is unconditional once both calls return.

## Diagram

None: the flow is one straight line (`command_created` → auto-execute → two text commands → message box) and prose shows it as clearly.

## Tests

- No module-specific test. `tests/test_command_contract.py` imports `entry.py` under the `adsk` stub and checks the `CMD_ID` shape, `CMD_Description`, the registered doc filename, this note, the arch index row and the README row; `tests/test_command_abort.py` scans `command_created` for `doExecute` calls.
- `entry.py` is Fusion-bound and is not otherwise exercised by the suite; nothing here is verified in Fusion on this branch except by those AST guards. The icon set is not pinned in `tests/test_command_icons.py`.

---

*Copyright © 2026 IMA LLC. All rights reserved.*
