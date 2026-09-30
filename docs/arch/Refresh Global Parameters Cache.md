# Refresh Global Parameters Cache — Architecture

[← Refresh Global Parameters Cache guide](../Refresh%20Global%20Parameters%20Cache.md)

| | |
|---|---|
| **Command ID** | `PTAT_refreshGlobalParametersCache` |
| **Registry** | group `assembly` (`Assembly`); enabled by default. Member of the `globalParameters` `COMMAND_SETS` entry — it starts on Global Parameters' enabled flag ([settings_store](architecture.md#settings_store)) |
| **UI location** | Shared **Power Tools** panel ([`_ui_bootstrap.get_power_tools_panel`](architecture.md#_ui_bootstrap)), appended with no anchor, `isPromoted = False` |
| **Files** | `commands/refreshGlobalParametersCache/entry.py`; `resources/` (button icons) |
| **Shared helpers** | [`cache_utils`](architecture.md#cache_utils): `get_active_project`, `GLOBAL_PARAMS_FOLDER_NAME`, `write_global_params_folder_cache`, `write_param_docs_cache`; [`ptutil.add_handler`](architecture.md#event_utils); [`ptutil.log`, `handle_error`](architecture.md#general_utils) |
| **Tests** | `tests/test_settings_command_sets.py` |

## Purpose

Rebuilds the two project-scoped cache files that Global Parameters and Link Global Parameters read at start-up — the `_Global Parameters` folder id and the list of parameter documents — from a fresh scan of the Hub, bypassing whatever is cached. It exists for the case where a parameter document was added, removed or renamed outside the add-in and the folder-id cache or document list has gone stale. There is no dialog: the whole command is one function run from `commandCreated`.

## How it is wired

- `start()`: deletes any stale definition, `addButtonDefinition` with the `resources/` icon folder, attaches `command_created`, adds the control to the Power Tools panel. `stop()` removes the control and deletes the definition. The `WORKSPACE_ID` / `TAB_ID` / `PANEL_ID` constants copied from `config` are not used for placement; the panel comes from `_ui_bootstrap`.
- `command_created(args)` → `refresh_cache_for_active_project()`. The command builds no inputs and attaches no other handlers, following the [act-from-commandCreated pattern](architecture.md#acting-from-commandcreated-when-there-are-no-inputs):
  1. [`cache_utils.get_active_project`](architecture.md#cache_utils); none → message box `No active Fusion project found.` and return.
  2. Scans `project.rootFolder.dataFolders` for a folder named `cache.GLOBAL_PARAMS_FOLDER_NAME` (`_Global Parameters`). The scan deliberately does not go through `find_global_params_folder`, so a stale `gp_folder` cache cannot short-circuit it. A raised exception goes to `handle_error` and ends the command; a missing folder → message box and return.
  3. `cache.write_global_params_folder_cache(project, folder, CMD_NAME)`.
  4. Enumerates `folder.dataFiles` into `{name: DataFile}` and calls `cache.write_param_docs_cache(project, doc_map, CMD_NAME)`.
  5. Logs and reports `Global Parameters cache refreshed for project '<name>'. N parameter set(s) found.` in a message box.
- No `execute` or `destroy` handler is attached; Fusion auto-executes and ends the input-less command.

## Data and state

- No module state beyond the constants.
- Files written under `cache/` (`cache_utils.CACHE_FOLDER`): `gp_folder_<project-key>.json` (`projectName`, `projectKey`, `folderId`, `folderName`) and `gp_docs_<project-key>.json` (`projectName`, `projectKey`, `docs: [{name, id}]`). The `<project-key>` is `cache_utils.project_cache_key` — the project id (or name) with non-word characters replaced by `_`.
- Settings keys, custom events, temp files: none.

## Diagram

None — the flow is linear with two early exits, all stated above.

## Tests

- `tests/test_settings_command_sets.py` — `refreshGlobalParametersCache` is a member of the `globalParameters` set: registered in the same group, gated on the lead's enabled flag and on the group.

`entry.py` is Fusion-bound and is not exercised by the suite; nothing here is verified in Fusion on this branch except by the AST guards in `tests/test_command_contract.py` and `tests/test_command_abort.py`, which import it under the `adsk` stub. The cache writers it calls live in `lib/ptAddInUtils/cache_utils.py`, which has no unit tests either. The icon set is not pinned in `tests/test_command_icons.py`.

---

*Copyright © 2026 IMA LLC. All rights reserved.*
