# Show In Location — Architecture

[← Show In Location guide](../Show%20In%20Location.md)

| | |
|---|---|
| **Command ID** | none — event-only; `entry.py` defines no `CMD_ID` and creates no command definition or control (listed in `KNOWN_NO_CMD_ID` in `tests/test_command_contract.py`) |
| **Registry** | group `document` (`Document Tools`), `settings=True`; **ships disabled** (`settings_store.DEFAULT_DISABLED_COMMANDS`) |
| **UI location** | no button. Its only UI is the two checkboxes rendered inline under its row in the Preferences palette (`commands/preferences/resources/html/app.js`, `docopen` section, `inline: true`) |
| **Files** | `commands/docopen/entry.py`; `resources/` holds a 16/32 px light/dark icon pair, referenced only by the unused `ICON_FOLDER` constant |
| **Shared helpers** | [`ptutil.add_handler`](architecture.md#event_utils), [`ptutil.log`](architecture.md#general_utils), [`settings_store.command_setting`](architecture.md#settings_store) |
| **Tests** | none of its own; `tests/test_command_contract.py`, `tests/test_command_abort.py` (import under the `adsk` stub) |

## Purpose

Keeps Fusion's Data Panel pointed at the active document by running the built-in text command `Dashboard.ShowInLocation <urn>` whenever a document is opened or a document tab is activated. The one constraint that shapes it: it has no command of its own, so everything is driven by application-level document events and gated by settings — there is nothing to click and no `execute`.

## How it is wired

- `start()`: registers two application-event handlers with [`ptutil.add_handler`](architecture.md#event_utils), both kept alive in the module list `local_handlers`:
  - `app.documentOpened` -> `application_documentOpened`
  - `app.documentActivated` -> `application_documentActivated`
- `stop()`: rebinds `local_handlers` to an empty list, dropping the handler references. No `remove()` is called on the events.
- `application_documentOpened(args)`: fires at the end of every document open. Reads `settings_store.command_setting("docopen", "run_on_open", True)`; when true, calls `_show_in_location("documentOpened", args.document)`.
- `application_documentActivated(args)`: fires when the user switches to a different document tab. Reads `command_setting("docopen", "run_on_activate", True)`; when true, calls `_show_in_location("documentActivated", args.document)`.
- `_show_in_location(event_name, doc)`: returns early (with a log line) when `doc` is `None` or `doc.dataFile` is falsy (an unsaved document has no cloud data file). Otherwise takes `doc.dataFile.id` as the URN and calls `app.executeTextCommand(f"Dashboard.ShowInLocation {urn}")`. Any exception is caught and logged with `force_console=True`; nothing is raised into the event dispatcher.

Because `start()` is only called when the command is enabled (see [`commands/__init__.py`](architecture.md#commands__init__)), the enable checkbox in Preferences is the master switch and takes effect on the next add-in start; the two per-event checkboxes are read live on every event.

## Data and state

- Module-level: `local_handlers` (handler references only).
- Settings keys (`settings_store.COMMAND_SETTING_DEFAULTS["docopen"]`): `run_on_open` and `run_on_activate`, both default `False`. The `entry.py` reads pass a fallback of `True`, which is only reached if a key is absent from the merged preferences.
- First-run migration: `settings_store._migrate_legacy()` seeds `commands.docopen.enabled` from the key `show_in_location_enabled` in the legacy `cache/settings.json` (read through `config.load_settings()`) when no preferences file exists yet.
- No caches, temp files or custom events.

## Tests

- `tests/test_command_contract.py` — imports `entry.py` under the `adsk` stub, checks `CMD_Description`, the registry/doc/README contract, and pins that `docopen` is one of exactly three registered modules without a `CMD_ID` (`KNOWN_NO_CMD_ID`).
- `tests/test_command_abort.py` — the repo-wide `doExecute` AST guard; this module registers no `commandCreated` handler, so only the import is exercised.

`entry.py` is Fusion-bound and is not exercised by the suite; nothing here is verified in Fusion on this branch except by the AST guards above, which import it under the `adsk` stub. The icon set is not pinned in `tests/test_command_icons.py`. Whether `Dashboard.ShowInLocation` still accepts a `dataFile.id` URN on the current Fusion build cannot be checked on a Linux checkout.

---

*Copyright © 2026 IMA LLC. All rights reserved.*
