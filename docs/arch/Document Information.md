# Document Information — Architecture

[← Document Information guide](../Document%20Information.md)

| | |
|---|---|
| **Command ID** | `PTND_docinfo` |
| **Registry** | module `docinfo`, group `document` (`Document Tools`); enabled by default; not beta |
| **UI location** | Design workspace → Tools tab → shared "Power Tools" panel (`config.my_panel_id`) via `_ui_bootstrap.get_power_tools_panel()`; promoted button |
| **Files** | `commands/docinfo/entry.py`; `resources/` (16/32/64 px light + dark icons; `docinfo.idraw` is the design source and is stripped from the release zip) |
| **Shared helpers** | [`_ui_bootstrap.get_power_tools_panel`](architecture.md#_ui_bootstrap); [`ptutil.add_handler`](architecture.md#event_utils); [`ptutil.require_document`, `log`, `handle_error`](architecture.md#general_utils) |
| **Tests** | `tests/test_release_build.py`; `tests/test_command_contract.py` |

## Purpose

Shows the cloud data identifiers behind the active design — hub, project, parent folder, full folder path, document id, version position — plus the Fusion build that last saved it, in one HTML message box. When the saving build differs from the running one, the title and body warn that the document will migrate to the current schema on save.

## How it is wired

- `start()`: `addButtonDefinition` with the resources folder; `ptutil.add_handler(cmd_def.commandCreated, command_created)`; on the shared panel (which `_ui_bootstrap.create_shared_access_points()` creates at add-in start — this command creates nothing) `panel.controls.addCommand(cmd_def)`, `isPromoted = True`.
- `stop()`: deletes the control and the definition.
- `command_created(args)`: registers `command_execute` and `command_destroy`. No `CommandInputs`, so Fusion auto-executes; with no document open the button does nothing (rule 1).
- `command_execute(args)`:
  1. `design = ptutil.require_document(CMD_NAME, "design", saved=True)` is `None` → return (it shows "Document Information needs a design open. Open or create a design, then retry." or "Document Information needs a saved design. Save the design, then retry."; see [Document preconditions](architecture.md#document-preconditions)).
  2. Reads `design.rootComponent.name`, `app.data.activeHub.id/.name`, `dataFile.parentProject.id/.name`, `dataFile.parentFolder.id` and its name (`"Project Root"` when `isRoot`), then walks `parentFolder` up to the root to build `A / B / C / <file name>`.
  3. `dataFile.id`, `.name`, `.versionNumber`, `.latestVersionNumber`, `.description` (version comment), `app.activeDocument.version` (saving build) and `app.version` (running build).
  4. Builds the HTML string and shows `ui.messageBox(text, title, 0, icon)`: icon code `2` when the builds match; when they differ, icon code `3`, the title gains " - Document will migrate on save" and the body a warning that team members must be on the same client version after the save.
  Exceptions → `ptutil.handle_error(CMD_NAME, show_message_box=True)`.
- `command_destroy(args)`: drops `local_handlers`.

## Data and state

`local_handlers` only. Everything shown is read live from `app.data` and `app.activeDocument.dataFile`; no disk cache, no settings keys, no custom events.

## Diagram

None — a single read-and-display handler.

## Tests

- `tests/test_release_build.py` — pins that `commands/docinfo/resources/docinfo.idraw` is excluded from the release zip.
- `tests/test_command_contract.py` — registry row, `CMD_Description`, docs pair, `CMD_ID` shape.

The icon set is not pinned in `tests/test_command_icons.py` (it is the `placeholder` three other pinned sets are asserted to differ from). `entry.py` is Fusion-bound and is not exercised by the suite; nothing here is verified in Fusion on this branch except by the AST guards in `tests/test_command_contract.py` and `tests/test_command_abort.py`, which import it under the `adsk` stub.

---

*Copyright © 2026 IMA LLC. All rights reserved.*
