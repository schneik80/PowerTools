# Favorites — Architecture

[← Favorites guide](../Favorites.md)

| | |
|---|---|
| **Command ID** | `PTAT_favorites_dropdown` (`CMD_ID`, the QAT dropdown control). Button definitions: `PTAT_favorites_add` (`CMD_ADD_ID`, "Favorite This Location"), `PTAT_favorites_edit` (`CMD_EDIT_ID`, "Edit Favorites"), and one positional `PTAT_fav_<i>` per saved entry (`ITEM_ID_PREFIX`; `SLOTS = MenuSlots(ITEM_ID_PREFIX, MENU_LIMIT)`, `MENU_LIMIT = 100`, no empty-state placeholder) |
| **Registry** | group `document` (`Document Tools`); enabled by default |
| **UI location** | a dropdown added directly to the `QAT` toolbar (not inside the File menu), anchored before the first of `FileSubMenuCommand`, `NewDocumentCommand`, `new`; else after the first of `ShowDataPanelCommand`, `DataPanelCommand`; else appended |
| **Files** | `commands/favorites/entry.py` (Fusion-bound); the keep/remove rule for the generated items is the shared adsk-free [`commands/_menu_plan.py`](architecture.md#_menu_plan) (also used by Open Recent); `resources/` (16/32/64 px light and dark icons used by the dropdown) |
| **Shared helpers** | [`_menu_plan`](architecture.md#_menu_plan); [`ptutil.add_handler`](architecture.md#event_utils), [`ptutil.log`](architecture.md#general_utils), [`ptutil.read_json`, `ptutil.write_json_atomic`](architecture.md#json_utils) |
| **Tests** | `tests/test_favorites_menu.py` (pure `_menu_plan` cases with this command's `SLOTS` plus `_rebuild_menu` / `_on_hub_changed` driven against fakes that refuse `deleteMe()` and raise on a duplicate id); `tests/test_command_contract.py`, `tests/test_command_abort.py` |

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
- `stop()`: `_clear_items()` sweeps the full id range the dropdown can ever own (`SLOTS.all_ids()`), deleting control then definition and re-querying rather than trusting the bool; then deletes the dropdown control and the add/edit definitions, resets all module state (`_owned_ids`, `_item_targets`, `_leftover_ids`, the edit-dialog triple, `_active_hub_id`) and rebinds `local_handlers` to a new empty list.
- `_favorites_document_event(args)`: re-reads the hub id; when it is non-empty and differs from `_active_hub_id`, `_on_hub_changed()` records it and calls `_rebuild_menu()`. Exceptions are logged at `ErrorLogLevel` and swallowed.
- `_rebuild_menu()`: loads the active hub's file with `_load_favorites()` (truncated to `MENU_LIMIT` with a log line), then `SLOTS.plan_menu(len(favorites))` splits the id range into `keep` and `remove`. Each removed id goes through `_remove_item` (control then definition, re-queried; an id Fusion refuses to delete -- its command is in flight -- is parked in `_leftover_ids` and retried next time). Each kept slot `i` goes through `_ensure_definition` -- reuse the owned definition in place (`name` = the entry's `display`, `tooltip` = `Navigate to <display> in Fusion Hub`), adopt or recreate a foreign one, never `addButtonDefinition` for an id that is still present -- records `(urn, display)` in `_item_targets[cmd_id]`, and `_ensure_control`, which adds the control only if missing, after the previous slot (the first one appends below the fixed rows). Never delete-then-add: the slot whose navigation triggered a hub-change rebuild cannot be deleted while its command is in flight (lesson #29, issue #34). There is no "unchanged, skip" fast path and no signature -- a rebuild runs only on a hub change or after Add / Edit, when the list has changed by construction.
- Navigation: `_make_navigate_handler(cmd_id)` returns `_created`, registered once per definition for its lifetime; at click time it reads the slot's current `(urn, display)` from `_item_targets` (a slot with no target -- removed but not yet deletable -- logs and ignores the click) and calls `_navigate`, which runs `app.executeTextCommand(f"Dashboard.ShowInLocation {urn}")` directly from `commandCreated` ([pattern](architecture.md#acting-from-commandcreated-when-there-are-no-inputs); issue #16 moved it out of `execute`, which Fusion never raises with no document open). A failure logs and shows "Unable to navigate to ...". No `execute` handler is registered for these items.
- Add (`PTAT_favorites_add`): `_add_favorite_created` does the whole job in `commandCreated` (issue #16) via `_add_favorite()`, which requires `app.activeDocument`, `doc.isSaved` and `doc.dataFile`; takes `dataFile.id` as the URN, `_get_folder_lineage(dataFile.parentFolder)` for the display string (up to ten ancestors joined with `" > "`), `_get_document_name()` for the name; rejects a duplicate URN; appends, `_save_favorites()`, `_rebuild_menu()`.
- Edit (`PTAT_favorites_edit`): `_edit_favorites_created` copies the loaded list into `_edit_staged_favorites`, builds the dialog with `_build_edit_dialog_inputs()`, and registers `_edit_favorites_input_changed`, `_edit_favorites_execute` and `_edit_favorites_destroy`. Deletes are staged in memory and committed only by `execute` (OK); `destroy` clears the staged state on OK and Cancel alike.

Neither `_add_favorite` nor the navigate `_created` reads command inputs, so [`ptutil.capture_selections`](architecture.md#selection_utils) is not involved.

## Data and state

- Module-level: `_favorites_dropdown` (the control), `_owned_ids` (slot definitions this module instance has wired a handler to), `_item_targets` (slot -> current `(urn, display)`), `_leftover_ids` (ids whose `deleteMe()` did not take), `_active_hub_id`, `local_handlers`, and the edit-dialog triple `_edit_staged_favorites` / `_edit_checkbox_map` / `_edit_build_version`.
- On disk: one file per hub, `cache/favorites_<sanitised hub id>.json`, where `_hub_cache_file()` replaces every character that is not alphanumeric, `-` or `_` with `_` (`b.abc123` -> `favorites_b_abc123.json`; an empty hub id maps to `favorites_unknown.json`). `cache/` is `<add-in root>/cache`. Reads go through `ptutil.read_json(path, {})` (missing or corrupt file -> empty list); writes through `ptutil.write_json_atomic`.
- Legacy file `cache/favorites.json` is deleted on every `start()` if it exists.
- No settings keys, custom events or temp files.
- One `commandCreated` handler per slot definition for its lifetime (attached when the definition is first owned, never a second time); released together in `stop()`.

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
- `tests/test_favorites_menu.py` -- `_menu_plan` buckets and bounds with this command's `SLOTS` (no placeholder), `item_text` and `menu_signature`; and `_rebuild_menu` / `_on_hub_changed` against fake `commandDefinitions`/controls (seeded with the fixed Add / Edit / separator rows) that raise on a duplicate id and refuse `deleteMe()` for a locked id: ordered first build, same-list rebuild reuses every slot, the #34 sequence (a click whose navigation switches hub and rebuilds inside the in-flight slot's own command: reused, no second add, one handler, the same handler then serves the new hub's entry), grow/shrink, empty hub, mid-rebuild exception retried, foreign definition adopted once, refused deletion retried, click navigates to the slot's current target, failed navigation shows the message, over-limit list truncated, `_clear_items` sweeps ghosts and leaves the fixed rows.

The hub detection, QAT placement, Add flow and Edit dialog are Fusion-only behaviour and are not exercised by the suite. The icon set is not pinned in `tests/test_command_icons.py`. The JSON round-trip, hub-id sanitising and lineage walk have no unit tests of their own.

---

*Copyright © 2026 IMA LLC. All rights reserved.*
