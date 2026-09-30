# Get Open in Team Link — Architecture

[← Get Open in Team Link guide](../Get%20Open%20in%20Team%20Link.md)

| | |
|---|---|
| **Command ID** | `PTSHD_shareopeninteam` |
| **Registry** | group `share` (`Share Document`); enabled by default |
| **UI location** | the `shareDropMenu` ("Share Menu") flyout on `QATRight`; appended (`addCommand(cmd_def, "", False)`) |
| **Files** | `commands/OpenInTeam/entry.py`; `resources/` (16 light/dark, `16x16@2x-dark`, 32 dark PNGs) |
| **Shared helpers** | [`ptutil.add_handler`](architecture.md#event_utils); [`ptutil.isSaved`, `clipText`, `log`, `handle_error`](architecture.md#general_utils); [`ptutil.remove_from_qat_right_flyout`](architecture.md#ui_utils); [`config`](architecture.md#config) (workspace/panel constants are imported but unused) |
| **Tests** | none beyond `tests/test_command_contract.py` |

## Purpose

Copies the active document's Fusion Team web URL to the clipboard so a hub member can review it in the browser. The URL is `DataFile.fusionWebURL` verbatim, which exists only for a saved document.

## How it is wired

- `start()`: `addButtonDefinition`; `commandCreated` → `command_created`; find-or-create the `shareDropMenu` flyout on `QATRight` (see [Get a Share Link](Get%20a%20Share%20Link.md)); `dropDown.controls.addCommand(cmd_def, "", False)`.
- `stop()`: [`ptutil.remove_from_qat_right_flyout(CMD_ID, "shareDropMenu")`](architecture.md#ui_utils), then delete the definition.
- `command_created(args)`: wires `execute` → `command_execute` and `destroy` → `command_destroy`; no inputs, so `execute` runs immediately when a document is open.
- `command_execute(args)`: [`ptutil.isSaved()`](architecture.md#general_utils) false → return. Then, inside a `try` ending in `ptutil.handle_error(CMD_NAME)`: `ui.progressBar.showBusy("Generating Fusion Team Link")`; `shareLink = app.activeDocument.dataFile.fusionWebURL`; `ptutil.log` it; `clipText(shareLink)`; build the HTML result with `html.escape(app.activeDocument.name)`; when `app.activeProduct.productType == "DesignProductType"` and `has_external_child_reference(rootComponent)` (recursive over `occurrences`, true on any `isReferencedComponent`), append a note that referenced designs may be shared depending on the recipient's permissions; `progressBar.hide()`; `ui.messageBox(resultString, "Share Document", 0, 2)`.
- `command_destroy(args)`: resets `local_handlers`.

## Data and state

None. Clipboard writes go through `ptutil.clipText`.

## Diagram

None: the flow is linear (guard, read one property, copy, report).

## Key API surface

| API element | Purpose |
|---|---|
| `app.activeDocument.dataFile.fusionWebURL` | The Fusion Team URL for the active document |
| `Occurrence.isReferencedComponent` | External-reference detection in `has_external_child_reference` |
| `ui.progressBar.showBusy` / `hide` | Busy indicator |

## Tests

- `tests/test_command_contract.py` — registry/doc/description contract; `PTSHD_shareopeninteam` is checked against the ID shape.

Not covered: `entry.py` is Fusion-bound and is not exercised by the suite; nothing here is verified in Fusion on this branch except by the AST guards in `tests/test_command_contract.py` and `tests/test_command_abort.py`, which import it under the `adsk` stub. The icon set is not pinned in `tests/test_command_icons.py`.

---

*Copyright © 2026 IMA LLC. All rights reserved.*
