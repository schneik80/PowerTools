# Hide Objects — Architecture

[← Hide Objects guide](../HideObjects.md)

| | |
|---|---|
| **Command ID** | `PTPM_hideobjects` |
| **Registry** | group `partmodeling` (`Part Modeling`); enabled by default |
| **UI location** | Design workspace (`FusionSolidEnvironment`), **Tools** tab (`ToolsTab`), panel `UtilityPanel` ("Utility"). `start()` creates the tab and the panel when absent and appends the control; not promoted. This is the same built-in tab that carries the shared Power Tools panel, but the command uses its own panel rather than [`get_power_tools_panel`](architecture.md#_ui_bootstrap); no other command references `UtilityPanel`. |
| **Files** | `commands/hideobjects/entry.py`; `resources/` holds 16/32/64 px light and dark PNGs (no `generate_icons.py`) |
| **Shared helpers** | [`ptutil.add_handler`](architecture.md#event_utils); [`ptutil.log`, `ptutil.handle_error`](architecture.md#general_utils); [`config.design_workspace`](architecture.md#config) |
| **Tests** | none module-specific (see [Tests](#tests)) |

## Purpose

Switches off the visibility light bulb of up to nine categories of reference and construction geometry across every component of the active design in one operation, so a model can be decluttered before sharing, rendering or review. Nothing is deleted or suppressed; everything can be turned back on from the browser. The dialog is nine plain checkboxes whose values are read directly in `execute` (they are `BoolValueCommandInput`s, not selections, so no capture step is needed).

## How it is wired

- `start()`: `addButtonDefinition(CMD_ID, CMD_NAME, CMD_Description, ICON_FOLDER)`; `ptutil.add_handler(cmd_def.commandCreated, command_created)`; `ui.workspaces.itemById(config.design_workspace)` (log and return if missing); `toolbarTabs.itemById("ToolsTab")` or `toolbarTabs.add("ToolsTab", "Tools")`; `toolbarPanels.itemById("UtilityPanel")` or `toolbarPanels.add("UtilityPanel", "Utility", "", False)`; `panel.controls.addCommand(cmd_def, "", True)`; `isPromoted = False`. The whole body is wrapped so a failure is logged rather than raised.
- `stop()`: deletes the control and the definition; deletes the panel when it is left empty (it is, since no other command adds to it); deletes the tab only if it has no panels left, which does not happen on the built-in Tools tab.
- `command_created(args)`: adds nine `addBoolValueInput(id, label, True, "", True)` checkboxes, all initially checked, then registers `execute` → `command_execute` and `destroy` → `command_destroy`. No `inputChanged`, `validateInputs` or `executePreview` handler.
- `command_execute(args)`: casts `app.activeProduct` to `adsk.fusion.Design` (message box and return otherwise); reads the nine values with `inputs.itemById(...).value`; iterates `design.allComponents` and applies the table below. Exceptions go to `ptutil.handle_error(CMD_NAME, show_message_box=True)`.
- `command_destroy(args)`: clears `local_handlers`.

| Input id | Label | What `command_execute` sets, per component |
|---|---|---|
| `hide_origin` | Origin | `isOriginFolderLightBulbOn = False` |
| `hide_construction_points` | Construction Points | every `constructionPoints[i].isLightBulbOn = False` |
| `hide_construction_axes` | Construction Axes | every `constructionAxes[i].isLightBulbOn = False` |
| `hide_construction_planes` | Construction Planes | every `constructionPlanes[i].isLightBulbOn = False` |
| `hide_joint_origins` | Joint Origins | every `jointOrigins[i].isLightBulbOn = False` |
| `hide_joints` | Joints | `isJointsFolderLightBulbOn = False` |
| `hide_sketches` | Sketches | `isSketchFolderLightBulbOn = True`, then every `sketches[i].isLightBulbOn = False` |
| `hide_canvas` | Canvas | `isCanvasFolderLightBulbOn = False` |
| `hide_ucs` | User Coordinate Systems | every `userCoordinateSystems[i].isLightBulbOn = False`, guarded by `hasattr` |

## Data and state

None beyond `local_handlers`. No settings keys, no files, no custom events.

## Folder bulbs versus item bulbs

Origin, joints and canvas are hidden at the folder bulb, which is the only bulb those categories expose. Sketches are the exception: the sketch folder bulb is forced **on** and each sketch's own bulb is switched off, so the folder stays visible in the browser and a single sketch can be re-enabled without re-showing all of them (the user guide states this as "sketch folder remains visible"). User coordinate systems have no folder bulb, and `Component.userCoordinateSystems` is a preview-state API absent from some Fusion builds, so both the collection and each item's `isLightBulbOn` are probed with `hasattr` and silently skipped when missing.

## Diagram

None: a single dialog followed by one loop; the table above is the complete behaviour.

## Tests

- No module-specific test. `tests/test_command_contract.py` imports `entry.py` under the `adsk` stub and checks the `CMD_ID` shape, `CMD_Description`, the registered doc filename, this note, the arch index row and the README row; `tests/test_command_abort.py` scans `command_created` for `doExecute` calls.
- `entry.py` is Fusion-bound and is not otherwise exercised by the suite; nothing here is verified in Fusion on this branch except by those AST guards. The icon set is not pinned in `tests/test_command_icons.py`.

---

*Copyright © 2026 IMA LLC. All rights reserved.*
