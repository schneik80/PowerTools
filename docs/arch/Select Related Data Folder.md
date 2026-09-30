# Select Related Data Folder — Architecture

[← Select Related Data Folder guide](../Select%20Related%20Data%20Folder.md)

| | |
|---|---|
| **Command ID** | `f"{config.COMPANY_NAME}_{config.ADDIN_NAME}_configHub"`, which resolves to `IMA LLC_PowerTools_configHub` when the add-in folder is named `PowerTools`. The space breaks rule 9; the module is allowlisted in `KNOWN_NONLITERAL_CMD_IDS` in `tests/test_command_contract.py`, and the ID is not fixed because renaming a `CMD_ID` orphans users' QAT pins. `commands/preferences/entry.py` builds the same f-string as `CONFIGHUB_CMD_ID` to launch it. |
| **Registry** | group `related` (`Related Data`); enabled by default |
| **UI location** | none — no toolbar control. Launched from the Preferences palette's Hub Settings section: the `browseHubFolder` HTML action runs `ui.commandDefinitions.itemById(CONFIGHUB_CMD_ID).execute()` (`commands/preferences/entry.py`). |
| **Files** | `commands/confighub/entry.py`; `resources/` (16/32/64 light, dark, disabled PNGs) |
| **Shared helpers** | [`config`](architecture.md#config) (`CACHE_PATH`, `reload_hub_config` / `loadHub`); [`ptutil.add_handler`](architecture.md#event_utils); [`ptutil.read_json`, `write_json_atomic`](architecture.md#json_utils); [`ptutil.log`](architecture.md#general_utils) |
| **Tests** | `tests/test_command_contract.py`, `tests/test_command_icons.py`; `tests/test_config_hub.py` covers the reader of the file this command writes |

## Purpose

Records, once per hub and per machine, which cloud folder holds the templates that [Create Related Data](Related%20Data.md) copies. The user picks the folder in Fusion's cloud folder dialog; the command works out which hub and project own it and writes the three IDs (plus display names) to `cache/hub.json`. The constraint: `config.loadHub` reads that file at import time, so the command reloads it in memory after writing and the sibling command sees the new hub without a restart.

## How it is wired

- `start()`: `ui.commandDefinitions.addButtonDefinition(CMD_ID, ...)` (no reuse of an existing definition), then `commandCreated` → `command_created` via [`ptutil.add_handler`](architecture.md#event_utils). No control is placed anywhere.
- `stop()`: deletes the definition.
- `command_created(args)` does the whole job and adds no command inputs, so Fusion auto-terminates the command afterwards and `execute` never runs ([acting from `commandCreated`](architecture.md#acting-from-commandcreated-when-there-are-no-inputs)); this is also what lets it run from the Preferences palette with no document open. In order:
  1. `active_hub = app.data.activeHub`; `hubs = _load_hubs()` (the `hubs` list from `cache/hub.json`, `[]` when absent).
  2. `_find_hub_entry(active_hub.id, hubs)` non-`None` → OK/Cancel message box "Hub Already Configured" showing the stored project and folder names; Cancel returns.
  3. Information message box telling the user to browse to the templates folder.
  4. `ui.createCloudFolderDialog()`, title "Select Templates Folder"; when a saved document is active, `initialFolder = app.activeDocument.dataFile.parentFolder`. Anything but `DialogOK` returns.
  5. `selected_folder = dialog.dataFolder`; `project = selected_folder.parentProject`; `hub = _resolve_hub_for_folder(selected_folder)`, which walks `app.data.dataHubs` and returns the first hub whose `dataProjects.itemById(project.id)` is not `None` — the owning hub is derived from the pick, not assumed to be the active hub. Either `None` → "Hub Not Found" warning, return.
  6. Builds `{"id", "name", "project_id", "project_name", "folder_id", "folder_name"}` and upserts it into `hubs` by `id` (replace in place, else append).
  7. `ptutil.write_json_atomic(HUB_JSON_PATH, {"hubs": hubs})`, then `config.reload_hub_config()`.
  8. "Hub Configured" message box saying whether the entry was added or updated.

## Data and state

- `cache/hub.json` (`HUB_JSON_PATH = config.CACHE_PATH/hub.json`):

  ```json
  {"hubs": [{"id": "...", "name": "...", "project_id": "...", "project_name": "...", "folder_id": "...", "folder_name": "..."}]}
  ```

  `config.loadHub` filters entries to dicts with an `id` and tolerates a truncated or missing file (`COMPANY_HUB = []`), because it runs at import time where a raise would stop the add-in loading with nothing logged.
- Module state: none beyond the constants. Settings keys: none. Custom events: none.
- The templates cache `cache/<hub_id>.json` written by Create Related Data is not touched here; repointing a hub to a new folder leaves the old template list in place until that file is deleted.

## Diagram

None: the flow is a single linear pass with early returns, listed above in order.

## Tests

- `tests/test_command_contract.py` — registry/doc/description contract; pins `confighub` in `KNOWN_NONLITERAL_CMD_IDS` and asserts the resolved `CMD_ID` still violates the ID shape.
- `tests/test_command_icons.py` — `confighub` is the `placeholder` for the two Team Add-ins icon sets, which are asserted to differ from this command's art.
- `tests/test_config_hub.py` — `config.loadHub` degrades a truncated file, a missing file, an entry without `id`, and non-dict entries to "no hub configured" and still loads a well-formed entry.

Not covered: `entry.py` is Fusion-bound and is not exercised by the suite; nothing here is verified in Fusion on this branch except by the AST guards in `tests/test_command_contract.py` and `tests/test_command_abort.py`, which import it under the `adsk` stub.

---

*Copyright © 2026 IMA LLC. All rights reserved.*
