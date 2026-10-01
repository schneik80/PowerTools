# Change Share Settings — Architecture

[← Change Share Settings guide](../Change%20Share%20Settings.md)

| | |
|---|---|
| **Command ID** | `PTSHD_sharesettings` |
| **Registry** | group `share` (`Share Document`); enabled by default |
| **UI location** | the `shareDropMenu` ("Share Menu") flyout on `QATRight`; appended (`addCommand(cmd_def, "", False)`), so the flyout follows registry start order (`shareDocument`, `shareSettings`, `OpenDesktop`, `OpenInTeam`, `projectInvite`, `projectMembers`). Issue #21 replaced a `PTSHD_projectInvite` anchor that did not exist yet when this `start()` ran; `tests/test_command_contract.py::test_pt_anchors_name_a_command_that_started_earlier` guards it. |
| **Files** | `commands/shareSettings/entry.py`; `resources/` (16/32 light and dark, 64 light PNGs) |
| **Shared helpers** | [`ptutil.add_handler`](architecture.md#event_utils); [`ptutil.require_document`, `log`, `handle_error`](architecture.md#general_utils); [`ptutil.remove_from_qat_right_flyout`](architecture.md#ui_utils); [`config`](architecture.md#config) (workspace/panel constants are imported but unused) |
| **Tests** | none beyond `tests/test_command_contract.py` |

## Purpose

Opens Fusion's own share-settings dialog (`SimpleSharingPublicLinkCommand`) for the active document from the Share Menu, after checking that the document is saved and that the hub allows sharing. Nothing is changed by this command itself; the native dialog owns the download and password settings.

## How it is wired

- `start()`: `addButtonDefinition`; `commandCreated` → `command_created`; find-or-create the `shareDropMenu` flyout on `QATRight` (`addDropDown("Share Menu", ICON_FOLDER, "shareDropMenu", "FeaturePacksCommand", True)` when absent — see [Get a Share Link](Get%20a%20Share%20Link.md)); `dropDown.controls.addCommand(cmd_def, "", False)` (appended).
- `stop()`: [`ptutil.remove_from_qat_right_flyout(CMD_ID, "shareDropMenu")`](architecture.md#ui_utils), then delete the definition.
- `command_created(args)`: wires `destroy` → `command_destroy`, then runs the whole command inline. No inputs and no `execute` handler: the Share Menu is live with no document open, where Fusion never raises `execute` (issue #16; [pattern](architecture.md#acting-from-commandcreated-when-there-are-no-inputs)).
- The body (formerly `command_execute`): [`ptutil.require_document(CMD_NAME, saved=True)`](architecture.md#document-preconditions) is `None` → return (it shows the standard message); reads `ui.commandDefinitions.itemById("SimpleSharingPublicLinkCommand").controlDefinition.isEnabled`; `isShareAllowed is False` → message "Sharing is not allowed …", return; otherwise `ui.commandDefinitions.itemById("SimpleSharingPublicLinkCommand").execute()` inside a `try` whose `except Exception` calls `ptutil.handle_error(CMD_NAME)`.
- `command_destroy(args)`: resets `local_handlers`.

## Data and state

None.

## Diagram

None: two gates and one `execute()`, listed above.

## Key API surface

| API element | Purpose |
|---|---|
| `ui.commandDefinitions.itemById("SimpleSharingPublicLinkCommand")` | The native share-settings command; `controlDefinition.isEnabled` reflects the hub's sharing policy, `execute()` opens the dialog |
| [`ptutil.require_document(CMD_NAME, saved=True)`](architecture.md#general_utils) | Saved-document guard; shows "Change Share Settings needs a saved document. Save the document, then retry." (or the no-document message) |

## Tests

- `tests/test_command_contract.py` — registry/doc/description contract; `PTSHD_sharesettings` is checked against the ID shape.

Not covered: `entry.py` is Fusion-bound and is not exercised by the suite; nothing here is verified in Fusion on this branch except by the AST guards in `tests/test_command_contract.py` and `tests/test_command_abort.py`, which import it under the `adsk` stub. The icon set is not pinned in `tests/test_command_icons.py`.

---

*Copyright © 2026 IMA LLC. All rights reserved.*
