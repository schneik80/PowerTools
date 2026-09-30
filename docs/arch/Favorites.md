# Favorites — Architecture

[← Favorites guide](../Favorites.md)

| | |
|---|---|
| **Command ID** | `PTAT_favorites_dropdown` (`CMD_ID`, the QAT dropdown control). Button definitions: `PTAT_favorites_add` (`CMD_ADD_ID`, "Favorite This Location"), `PTAT_favorites_edit` (`CMD_EDIT_ID`, "Edit Favorites"), and one generated `PTAT_fav_<i>` per saved entry |
| **Registry** | group `document` (`Document Tools`); enabled by default |
| **UI location** | a dropdown added directly to the `QAT` toolbar (not inside the File menu), anchored before the first of `FileSubMenuCommand`, `NewDocumentCommand`, `new`; else after the first of `ShowDataPanelCommand`, `DataPanelCommand`; else appended |
| **Files** | `commands/favorites/entry.py`; `resources/` (16/32/64 px light and dark icons used by the dropdown) |
| **Shared helpers** | [`ptutil.add_handler`](architecture.md#event_utils), [`ptutil.log`](architecture.md#general_utils), [`ptutil.read_json`, `ptutil.write_json_atomic`](architecture.md#json_utils) |
| **Tests** | none of its own; `tests/test_command_contract.py`, `tests/test_command_abort.py` |

## Purpose

A QAT dropdown of saved Fusion Team locations: two fixed actions (add the active document's location, edit the list) followed by one generated button per favorite that runs `Dashboard.ShowInLocation <urn>` to reveal it in the Data Panel. The shaping constraint is that favorites are stored per hub, so the menu must be rebuilt whenever the active hub changes, and Fusion offers no hub-changed event — the command watches document events instead.

## How it is wired

- `start()`, in order:
  1. `_remove_legacy_cache()` deletes `cache/favorites.json` if present.
  2. `_active_hub_id = _get_active_hub_id()` (`app.data.activeHub.id`, falling back to `hubId`; `""` on any failure or when no hub is in context yet).
  3. Creates or reuses the `CMD_ADD_ID` and `CMD_EDIT_ID` button definitions and registers `_add_favorite_created` / `_edit_favorites_created` on their `commandCreated`.
  4. Deletes any stale `CMD_ID` control on the `QAT` toolbar, then `qat.controls.addDropDown(CMD_NAME, ICON_FOLDER, CMD_ID, anchor, is_before)` using the anchor ladder in the table above.
  5. Adds the add and edit commands and a separator to the dropdown, then `_rebuild_menu()`.
  6. Registers `_favorites_document_event` on both `app.documentActivated` and `app.documentOpened`.
- `stop()`: deletes the dropdown control, the add/edit definitions and every id in `_fav_cmd_ids`, then resets all module state and rebinds `local_handlers` to a new empty list.
- `_favorites_document_event(args)`: re-reads the hub id; when it is non-empty and differs from `_active_hub_id`, `_on_hub_changed()` records it and calls `_rebuild_menu()`. Exceptions are logged at `ErrorLogLevel` and swallowed.
- `_rebuild_menu()`: deletes the controls and definitions listed in `_fav_cmd_ids`, loads the active hub's file with `_load_favorites()`, and for each entry `i` creates (or reuses) button definition `PTAT_fav_{i}` titled with the entry's `display`, registers the closure from `_make_navigate_handler(urn, display)` on its `commandCreated`, and adds it to the dropdown.
- Navigation: `_make_navigate_handler` returns `_created`, which registers a nested `_execute` on `args.command.execute`. The command builds no inputs, so Fusion auto-executes it and `_execute` runs `app.executeTextCommand(f"Dashboard.ShowInLocation {urn}")`; a failure logs and shows a message box. Because the work is in `execute`, not `commandCreated`, it depends on `execute` being raised — which Fusion does not do with no document open (rule 1); Open Recent, by contrast, acts from `commandCreated`.
- Add (`PTAT_favorites_add`): `_add_favorite_created` registers `_add_favorite_execute`, which requires `app.activeDocument`, `doc.isSaved` and `doc.dataFile`; takes `dataFile.id` as the URN, `_get_folder_lineage(dataFile.parentFolder)` for the display string (up to ten ancestors joined with `" > "`), `_get_document_name()` for the name; rejects a duplicate URN; appends, `_save_favorites()`, `_rebuild_menu()`.
- Edit (`PTAT_favorites_edit`): `_edit_favorites_created` copies the loaded list into `_edit_staged_favorites`, builds the dialog with `_build_edit_dialog_inputs()`, and registers `_edit_favorites_input_changed`, `_edit_favorites_execute` and `_edit_favorites_destroy`. Deletes are staged in memory and committed only by `execute` (OK); `destroy` clears the staged state on OK and Cancel alike.

Neither `_add_favorite_execute` nor the navigate `_execute` reads command inputs, so [`ptutil.capture_selections`](architecture.md#selection_utils) is not involved.

## Data and state

- Module-level: `_favorites_dropdown` (the control), `_fav_cmd_ids` (generated definition ids), `_active_hub_id`, `local_handlers`, and the edit-dialog triple `_edit_staged_favorites` / `_edit_checkbox_map` / `_edit_build_version`.
- On disk: one file per hub, `cache/favorites_<sanitised hub id>.json`, where `_hub_cache_file()` replaces every character that is not alphanumeric, `-` or `_` with `_` (`b.abc123` -> `favorites_b_abc123.json`; an empty hub id maps to `favorites_unknown.json`). `cache/` is `<add-in root>/cache`. Reads go through `ptutil.read_json(path, {})` (missing or corrupt file -> empty list); writes through `ptutil.write_json_atomic`.
- Legacy file `cache/favorites.json` is deleted on every `start()` if it exists.
- No settings keys, custom events or temp files.
- Every `_rebuild_menu()` appends new handler objects to `local_handlers` without removing the previous ones; they are released together in `stop()`.

## Data model

```json
{
  "hub_id": "b.abc123def456",
  "favorites": [
    {
      "name": "Document Name",
      "display": "Project > Folder > Subfolder",
      "urn": "urn:adsk.wipprod:dm.lineage:..."
    }
  ]
}
```

- `hub_id`: the hub the file belongs to (informational; the filename is the key).
- `name`: document name, shown in the edit table; `_get_favorite_name()` falls back to the last `display` segment when it is empty.
- `display`: folder lineage, used as the button title and the edit table's location column.
- `urn`: `dataFile.id` of the document that was active when the favorite was added — the same URN form Show In Location uses. Navigation therefore reveals that document, and with it the folder shown in `display`.

## Edit dialog

`_build_edit_dialog_inputs()` deletes and recreates three inputs each time it runs: a read-only count text box (`PTAT_favorites_edit_count`), a three-column table (`PTAT_favorites_edit_table`, ratio `1:3:6`, 3-12 visible rows) with one checkbox + two read-only text boxes per staged favorite, and a full-width bool "Delete Selected" button (`PTAT_favorites_edit_delete`) that starts disabled. Per-row input ids carry a build counter (`fav_edit_sel_<build>_<i>`) so ids never collide across rebuilds inside one dialog; `_edit_checkbox_map` maps checkbox id -> staged index.

`_edit_favorites_input_changed`: a `fav_edit_sel_*` change only toggles the delete button (`_update_delete_button_enabled`); a click on the delete button collects the checked indices, filters `_edit_staged_favorites`, sets `btn.value = False` **before** rebuilding (after the rebuild the old input object is deleted and can no longer be written), and rebuilds the inputs.

## Tests

- `tests/test_command_contract.py` — imports `entry.py` under the `adsk` stub; checks `CMD_Description`, the registry/doc/README contract, that `CMD_ID` is a literal with the Fusion id shape, and that the `PTAT_favorites_add`, `PTAT_favorites_edit`, `PTAT_fav_`, `PTAT_favorites_edit_*` literals are the known non-command ids (`KNOWN_NON_COMMAND_PT_LITERALS`).
- `tests/test_command_abort.py` — the repo-wide `doExecute` AST guard; pins that the three oddly named `commandCreated` handlers here (`_created`, `_add_favorite_created`, `_edit_favorites_created`) are found by the registration walk.

`entry.py` is Fusion-bound and is not exercised by the suite; nothing here is verified in Fusion on this branch except by the AST guards above, which import it under the `adsk` stub. The icon set is not pinned in `tests/test_command_icons.py`. The JSON round-trip, hub-id sanitising and lineage walk have no unit tests of their own.

---

*Copyright © 2026 IMA LLC. All rights reserved.*
