# Add Default Project Folders — Architecture

[← Add Default Project Folders guide](../Default%20Folders.md)

| | |
|---|---|
| **Command ID** | `PT_defaultfolders` |
| **Registry** | module `defaultfolders`, group `document` (`Document Tools`); enabled by default; not beta; `settings=True` (has a section in the Preferences palette) |
| **UI location** | QAT File dropdown (`ui.toolbars.itemById("QAT")` → `FileSubMenuCommand`), appended at the end (`addCommand(cmd_def)` with no anchor); text item, no icon |
| **Files** | `commands/defaultfolders/entry.py` only (no `resources/`) |
| **Shared helpers** | [`settings_store.command_setting`, `COMMAND_SETTING_DEFAULTS`, `DEFAULT_FOLDER_SETS`](architecture.md#settings_store); [`cache_utils.get_active_project`](architecture.md#cache_utils) (as `ptutil.get_active_project`); [`ptutil.add_handler`](architecture.md#event_utils); [`ptutil.log`, `handle_error`](architecture.md#general_utils) |
| **Tests** | `tests/test_command_contract.py` only |

## Purpose

Creates a predefined set of folders in the root of the active project, skipping any that already exist (case-insensitive), so every project gets the same structure without anyone building it by hand. The user picks **Basic** or **Advanced** in a small dialog with a live preview; both lists are user-editable in Preferences and read from the settings store at run time.

## How it is wired

- `start()`: `addButtonDefinition(CMD_ID, CMD_NAME, CMD_Description)` (no resource folder); `ptutil.add_handler(cmd_def.commandCreated, command_created)`; `fileDropDown.controls.addCommand(cmd_def)`. The QAT and dropdown are read directly, without the `None` guard [`ptutil.get_qat_file_dropdown`](architecture.md#ui_utils) provides.
- `stop()`: deletes the dropdown control and the definition.
- `command_created(args)`: builds a `folderSet` text-list dropdown (**Basic** selected, **Advanced**) and a read-only `folderPreview` text box sized to `max(len(basic), len(advanced)) + 1` rows, filled by `_build_preview("Basic", _get_existing_lower())`. Registers `command_execute`, `command_input_changed`, `command_destroy`.
- `_get_existing_lower()`: `ptutil.get_active_project(CMD_NAME)` (guards `app.data.activeProject`, which raises `InternalValidationError('id.size()')` when no project is in context — rule 8); returns `[f.name.casefold() for f in project.rootFolder.dataFolders]`, or `[]` when there is no project or the read fails.
- `_folder_set(option_key)`: `settings_store.command_setting("defaultfolders", key, fallback)` with `fallback = COMMAND_SETTING_DEFAULTS["defaultfolders"][key]`; a non-list value falls back; blank names are dropped.
- `_build_preview(name, existing_lower)`: one line per folder, `+ name` or `(exists)  name`.
- `command_input_changed(args)`: only for `args.input.id == "folderSet"`; re-reads the project folders and rewrites `folderPreview.text`.
- `command_execute(args)`: reads the dropdown, resolves the list with `_folder_set`, then `ptutil.get_active_project(CMD_NAME)`; `None` → an actionable message box ("Open the Data Panel and click into the project…") and return. Otherwise `root.dataFolders.add(name)` for every name whose `casefold()` is not already present. Exceptions → `ptutil.handle_error(CMD_NAME, show_message_box=True)`.
- `command_destroy(args)`: drops `local_handlers`.

## Data and state

- `local_handlers` only; no module-level caches, no custom events.
- Settings keys: `command_settings.defaultfolders.basic` and `command_settings.defaultfolders.advanced` (lists of folder names), edited in the Preferences palette's **Add Project Folders** section. Defaults seed from `settings_store.DEFAULT_FOLDER_SETS`:
  - `basic`: `_Global Parameters`, `Drawings`, `Archive`, `Obit`, `Wiki`
  - `advanced`: `01 - Assemblies` … `10 - Archive`, `XX - Obit` (eleven names)
- Written: new `DataFolder`s under the active project's `rootFolder`.

## Diagram

None — dropdown → preview → `dataFolders.add` for the missing names.

## Tests

- `tests/test_command_contract.py` — registry row, `CMD_Description`, docs pair, `CMD_ID` shape.

The name comparison, the preview text and the settings fallback have no dedicated test. `entry.py` is Fusion-bound and is not exercised by the suite; nothing here is verified in Fusion on this branch except by the AST guards in `tests/test_command_contract.py` and `tests/test_command_abort.py`, which import it under the `adsk` stub.

## Learnings

- **`app.data.activeProject` raises rather than returning `None`.** With no project in the Data Panel's context it fails with `InternalValidationError('id.size()')`; go through `cache_utils.get_active_project` and show an actionable message instead of a traceback (rule 8).

---

*Copyright © 2026 IMA LLC. All rights reserved.*
