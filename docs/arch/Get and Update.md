# Get and Update — Architecture

[← Get and Update guide](../Get%20and%20Update.md)

| | |
|---|---|
| **Command ID** | `PTAT_getandupdate` |
| **Registry** | group `assembly` (`Assembly`); **ships disabled** (`settings_store.DEFAULT_DISABLED_COMMANDS`) |
| **UI location** | Quick Access Toolbar (`ui.toolbars.itemById("QAT")`), `addCommand(cmd_def, "save", True)` — placed after Fusion's Save control |
| **Files** | `commands/getandupdate/entry.py`; `resources/` PNGs (16 light/dark/disabled, 32 light/disabled, 64) plus two `force rebuild *.pxd` source bundles, which `tools/release/build_release.py` excludes from the zip |
| **Shared helpers** | [`ptutil.add_handler`](architecture.md#event_utils); [`ptutil.log`, `handle_error`](architecture.md#general_utils) |
| **Tests** | none module-specific |

## Purpose

One QAT button that runs two of Fusion's own commands back to back: **Get All
Latest** (`GetAllLatestCmd`) and then **Update All From Parent**
(`ContextUpdateAllFromParentCmd`). It owns no logic of its own; the constraint
is that both are UI commands executed through their `CommandDefinition`, so the
add-in neither waits for nor observes their completion.

## How it is wired

- `start()`: `addButtonDefinition(CMD_ID, …)`, `commandCreated -> command_created`,
  `qat.controls.addCommand(cmd_def, "save", True)`. `stop()`: removes the QAT
  control and the definition.
- `command_created`: registers `execute -> command_execute` and
  `destroy -> command_destroy`. No `CommandInputs`, so Fusion runs
  `command_execute` immediately.
- `command_execute`: `ui.commandDefinitions.itemById("GetAllLatestCmd").execute()`
  followed at once by `itemById("ContextUpdateAllFromParentCmd").execute()`.
  There is no wait between the two and no check of either return value;
  exceptions (for example a missing definition returning `None`) go to
  `ptutil.handle_error(CMD_NAME, show_message_box=True)`.
- `command_destroy`: clears `local_handlers`.

## Data and state

None. No module state beyond `local_handlers`, no cache, settings keys or
custom events. Enablement is the registry default plus the user's Preferences
choice, applied at the next `commands.start()`.

## Diagram

None — two consecutive `execute()` calls with no branching.

## Tests

- No module-specific test. `tests/test_command_contract.py` checks the
  registry entry, `CMD_ID` literal and description casing; `tests/test_command_abort.py`
  includes `command_created` in its AST guard; `tests/test_release_build.py`
  asserts the `.pxd` bundle content is excluded from the release zip.
- `entry.py` is Fusion-bound and is not exercised by the suite; nothing here is
  verified in Fusion on this branch except by the AST guards in
  `tests/test_command_contract.py` and `tests/test_command_abort.py`, which
  import it under the `adsk` stub. Whether the second command waits for the
  first inside Fusion is not observed by the add-in. The icon set is not pinned
  in `tests/test_command_icons.py`.

---

*Copyright © 2026 IMA LLC. All rights reserved.*
