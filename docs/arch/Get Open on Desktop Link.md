# Get Open on Desktop Link — Architecture

[← Get Open on Desktop Link guide](../Get%20Open%20on%20Desktop%20Link.md)

| | |
|---|---|
| **Command ID** | `PTSHD_shareopenondesktop` |
| **Registry** | group `share` (`Share Document`); enabled by default |
| **UI location** | the `shareDropMenu` ("Share Menu") flyout on `QATRight`; appended (`addCommand(cmd_def, "", False)`) |
| **Files** | `commands/OpenDesktop/entry.py`; `resources/` (16 light/dark, `16x16@2x-dark`, 32 dark PNGs) |
| **Shared helpers** | [`ptutil.add_handler`](architecture.md#event_utils); [`ptutil.isSaved`, `clipText`, `log`, `handle_error`](architecture.md#general_utils); [`ptutil.remove_from_qat_right_flyout`](architecture.md#ui_utils); [`config`](architecture.md#config) (workspace/panel constants are imported but unused) |
| **Tests** | none beyond `tests/test_command_contract.py` |

## Purpose

Builds a `fusion360://` deep link for the active document and copies it to the clipboard, so a teammate who has access can open the document directly in their Fusion desktop client. The link carries the document's lineage URN, the hub URL and the document name; the document must be saved for the first two to exist.

## How it is wired

- `start()`: `addButtonDefinition`; `commandCreated` → `command_created`; find-or-create the `shareDropMenu` flyout on `QATRight` (see [Get a Share Link](Get%20a%20Share%20Link.md)); `dropDown.controls.addCommand(cmd_def, "", False)`.
- `stop()`: [`ptutil.remove_from_qat_right_flyout(CMD_ID, "shareDropMenu")`](architecture.md#ui_utils), then delete the definition.
- `command_created(args)`: wires `destroy` → `command_destroy`, then runs the whole command inline. No inputs and no `execute` handler: the Share Menu is live with no document open, where Fusion never raises `execute` (issue #16; [pattern](architecture.md#acting-from-commandcreated-when-there-are-no-inputs)).
- The body (formerly `command_execute`): [`ptutil.isSaved()`](architecture.md#general_utils) false → return. Then, inside a `try` ending in `ptutil.handle_error(CMD_NAME)`: `ui.progressBar.showBusy("Generating Share Link")`; assemble the link (below); `ptutil.log` it; `clipText(shareLink)`; build the HTML result with `html.escape(app.activeDocument.name)`; when `app.activeProduct.productType == "DesignProductType"` and `has_external_child_reference(rootComponent)` (recursive over `occurrences`, true on any `isReferencedComponent`), append a note that referenced designs may be shared depending on the recipient's permissions; `progressBar.hide()`; `ui.messageBox(resultString, "Share Document", 0, 2)`.
- `command_destroy(args)`: resets `local_handlers`.

## Link construction

```
fusion360://lineageUrn=<quote(dataFile.id)>&hubUrl=<quote(hub)>&documentName=<quote(document.name)>
```

- `lineageUrn`: `app.activeDocument.dataFile.id`, URL-encoded with `urllib.parse.quote`.
- `hubUrl`: `app.activeDocument.dataFile.parentProject.parentHub.fusionWebURL` with spaces removed, then `.rstrip(url[-3:])` — `str.rstrip` strips every trailing character that is in the set formed by the URL's last three characters, not a fixed three-character cut — then upper-cased and URL-encoded.
- `documentName`: `app.activeDocument.name`, URL-encoded; display only on the receiving side.

## Data and state

None. Clipboard writes go through `ptutil.clipText`.

## Diagram

None: the flow is linear (guard, build, copy, report).

## Key API surface

| API element | Purpose |
|---|---|
| `app.activeDocument.dataFile.id` | Lineage URN, the primary identifier in the link |
| `app.activeDocument.dataFile.parentProject.parentHub.fusionWebURL` | Hub URL so the recipient's client connects to the right hub |
| `app.activeDocument.name` | Document name parameter |
| `urllib.parse.quote` | URL-encodes each parameter |
| `Occurrence.isReferencedComponent` | External-reference detection in `has_external_child_reference` |

## Tests

- `tests/test_command_contract.py` — registry/doc/description contract; `PTSHD_shareopenondesktop` is checked against the ID shape.

Not covered: `entry.py` is Fusion-bound and is not exercised by the suite; nothing here is verified in Fusion on this branch except by the AST guards in `tests/test_command_contract.py` and `tests/test_command_abort.py`, which import it under the `adsk` stub. The icon set is not pinned in `tests/test_command_icons.py`.

---

*Copyright © 2026 IMA LLC. All rights reserved.*
