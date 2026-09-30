# Insert STEP File — Architecture

[← Insert STEP File guide](../Insert%20Step.md)

| | |
|---|---|
| **Command ID** | `PTAT_insertSTEP` |
| **Registry** | group `assembly` (`Assembly`); enabled by default. Registered before `assemblypalette`, whose launch button anchors on this control id |
| **UI location** | Design workspace (`FusionSolidEnvironment`), two panels from `TABS`: ASSEMBLY tab › INSERT panel (`InsertAssemblePanel`) and SOLID tab › Insert panel (`InsertPanel`). Tab and panel are created when absent; the control is appended with no `positionID`; not promoted |
| **Files** | `commands/insertSTEP/entry.py`; `resources/16x16.png`, `32x32.png`, `64x64.png` (no dark or disabled variants) |
| **Shared helpers** | [`ptutil.add_handler`](architecture.md#event_utils); [`ptutil.log`, `handle_error`](architecture.md#general_utils) |
| **Tests** | none module-specific |

## Purpose

Puts a STEP import one click away in the assembly workflow: the user picks a
`.stp` / `.step` file in an OS file dialog and Fusion imports it into the active
design through its own `Fusion.ImportComponent` text command. The command has no
dialog of its own, so all of its work happens in `commandCreated`.

## How it is wired

- `start()`: `addButtonDefinition(CMD_ID, …)`, `commandCreated -> command_created`,
  then for each `TABS` entry: look up the tab (`toolbarTabs.itemById`, else
  `add`), the panel (`toolbarPanels.itemById`, else `add`), and
  `panel.controls.addCommand(cmd_def)`.
- `stop()`: for each `TABS` entry, removes this control from the panel
  (looked up through `workspace.toolbarPanels.itemById`); deletes the panel
  when it has no controls left and the tab when it has no panels left; then
  deletes the definition. In practice only the add-in-created ASSEMBLY tab
  panel can become empty; Fusion's own panels keep their native controls.
- `command_created` — the whole command, following
  [Acting from commandCreated when there are no inputs](architecture.md#acting-from-commandcreated-when-there-are-no-inputs):
  casts `app.activeProduct` to `Design` (else `messageBox("No active Fusion
  design")` and return); `ui.createFileDialog()` with title `Fusion Insert
  STEP`, single select, filter `STEP Files(*.stp;*.STP;*.step;*.STEP);;All files
  (*.*)`; on `DialogOK` wraps the path in double quotes and runs
  `app.executeTextCommand(f"Fusion.ImportComponent {filename}")`. Exceptions go
  to `ptutil.handle_error(CMD_NAME, show_message_box=True)`.

## Data and state

None. No module state beyond `local_handlers` (unused), no cache, no settings
keys, no custom events.

## Diagram

None — the flow is `command_created` → file dialog → one text command, and the
prose above covers it.

## Tests

- No module-specific test. `tests/test_command_contract.py` checks the
  registry entry, `CMD_ID` literal and description casing; `tests/test_command_abort.py`
  includes `command_created` in its AST guard.
- `entry.py` is Fusion-bound and is not exercised by the suite; nothing here is
  verified in Fusion on this branch except by the AST guards in
  `tests/test_command_contract.py` and `tests/test_command_abort.py`, which
  import it under the `adsk` stub. How `Fusion.ImportComponent` places the
  imported geometry is Fusion's behaviour and is not asserted anywhere. The icon
  set is not pinned in `tests/test_command_icons.py`.

---

*Copyright © 2026 IMA LLC. All rights reserved.*
