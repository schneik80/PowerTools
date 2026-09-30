# Change Share Settings — Architecture

[← Change Share Settings guide](../Change%20Share%20Settings.md)

| | |
|---|---|
| **Command ID** | `PTSHD_sharesettings` |
| **Registry** | group `share` (`Share Document`); enabled by default |
| **UI location** | the `shareDropMenu` ("Share Menu") flyout on `QATRight`; placed with `addCommand(cmd_def, "PTSHD_projectInvite", False)`, i.e. after Invite to Project. In registry start order (`shareDocument`, `shareSettings`, `OpenDesktop`, `OpenInTeam`, `projectInvite`, `projectMembers`) that anchor does not exist yet when this `start()` runs, so the resulting position depends on how Fusion treats an unresolved `positionID`; not verified in Fusion on this branch. Invite to Project and Document Project Members in turn anchor themselves before this control. |
| **Files** | `commands/shareSettings/entry.py`; `resources/` (16/32 light and dark, 64 light PNGs) |
| **Shared helpers** | [`ptutil.add_handler`](architecture.md#event_utils); [`ptutil.isSaved`, `log`, `handle_error`](architecture.md#general_utils); [`ptutil.remove_from_qat_right_flyout`](architecture.md#ui_utils); [`config`](architecture.md#config) (workspace/panel constants are imported but unused) |
| **Tests** | none beyond `tests/test_command_contract.py` |

## Purpose

Opens Fusion's own share-settings dialog (`SimpleSharingPublicLinkCommand`) for the active document from the Share Menu, after checking that the document is saved and that the hub allows sharing. Nothing is changed by this command itself; the native dialog owns the download and password settings.

## How it is wired

- `start()`: `addButtonDefinition`; `commandCreated` → `command_created`; find-or-create the `shareDropMenu` flyout on `QATRight` (`addDropDown("Share Menu", ICON_FOLDER, "shareDropMenu", "FeaturePacksCommand", True)` when absent — see [Get a Share Link](Get%20a%20Share%20Link.md)); `dropDown.controls.addCommand(cmd_def, "PTSHD_projectInvite", False)`.
- `stop()`: [`ptutil.remove_from_qat_right_flyout(CMD_ID, "shareDropMenu")`](architecture.md#ui_utils), then delete the definition.
- `command_created(args)`: wires `execute` → `command_execute` and `destroy` → `command_destroy`; no inputs, so `execute` runs immediately when a document is open.
- `command_execute(args)`: reads `ui.commandDefinitions.itemById("SimpleSharingPublicLinkCommand").controlDefinition.isEnabled`; [`ptutil.isSaved()`](architecture.md#general_utils) false → return; `isShareAllowed is False` → message "Sharing is not allowed …", return; otherwise `ui.commandDefinitions.itemById("SimpleSharingPublicLinkCommand").execute()` inside a `try` whose `except Exception` calls `ptutil.handle_error(CMD_NAME)`.
- `command_destroy(args)`: resets `local_handlers`.

## Data and state

None.

## Diagram

None: two gates and one `execute()`, listed above.

## Key API surface

| API element | Purpose |
|---|---|
| `ui.commandDefinitions.itemById("SimpleSharingPublicLinkCommand")` | The native share-settings command; `controlDefinition.isEnabled` reflects the hub's sharing policy, `execute()` opens the dialog |
| [`ptutil.isSaved()`](architecture.md#general_utils) | Saved-document guard with its own "Please Save" prompt |

## Tests

- `tests/test_command_contract.py` — registry/doc/description contract; `PTSHD_sharesettings` is checked against the ID shape and is the anchor literal that Invite to Project and Document Project Members reference.

Not covered: `entry.py` is Fusion-bound and is not exercised by the suite; nothing here is verified in Fusion on this branch except by the AST guards in `tests/test_command_contract.py` and `tests/test_command_abort.py`, which import it under the `adsk` stub. The icon set is not pinned in `tests/test_command_icons.py`.

---

*Copyright © 2026 IMA LLC. All rights reserved.*
