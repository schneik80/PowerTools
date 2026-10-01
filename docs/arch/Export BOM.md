# Export BOM as CSV — Architecture

[← Export BOM as CSV guide](../Export%20BOM.md)

| | |
|---|---|
| **Command ID** | `PTE_exportbom` |
| **Registry** | group `exports` (`Exports`); enabled by default |
| **UI location** | QAT **File** dropdown (`FileSubMenuCommand`), `controls.addCommand(cmd_def, "ExportCommand", True)` — directly before Fusion's **Export** item; no icon folder |
| **Files** | `commands/exportbomcsv/entry.py` only |
| **Shared helpers** | [`ptutil.add_handler`](architecture.md#event_utils), [`ptutil.log`, `ptutil.handle_error`](architecture.md#general_utils) |
| **Tests** | `tests/test_csv_injection.py`; `tests/test_command_contract.py`, `tests/test_command_abort.py` |

## Purpose

Writes a flat bill of materials for the active design to `<document name>.csv` in a folder the user picks: one row per unique component (keyed on `Component.id`) with display name, part number, the material names of its solid bodies, and the instance count. The shaping constraint is that names, part numbers and materials come from documents other people authored, so every text cell passes through a formula-injection guard before it reaches a spreadsheet.

## How it is wired

- `start()`: `addButtonDefinition(CMD_ID, CMD_NAME, CMD_Description)`, `command_created` on `commandCreated` (global handler list), then adds the control to the File dropdown before `ExportCommand`.
- `stop()`: deletes the File-dropdown control and the definition.
- `command_created(args)`: registers `command_destroy`, then `ptutil.require_document(CMD_NAME, "design")`; with no active design it shows the standard message ("Export BOM as CSV needs a design open. Open or create a design, then retry.") and returns. Otherwise it calls `_export_bom(design)` inside a `try`. There are no inputs and no `execute` handler: the control sits in the File dropdown, which exists on the start screen, and `execute` never fires there (rule 1, #25).
- `_export_bom(design)`:
  1. No inputs are built, so the module defaults `showversion = True`, `showsubs = False` always apply.
  2. Walks `rootComponent.allOccurrences` once. `rows_by_id` maps `Component.id` -> row; a repeat occurrence increments `instances`, a first sighting builds the row: `name` (`comp.name`; the ` v<n>` suffix of a referenced component would be stripped only when `showversion` is false), `pn = comp.partNumber`, `material` = the concatenated `material.name` of every `isSolid` body in `comp.bRepBodies`, `instances = 1`, `sub = occ.childOccurrences.count` (read once per component).
  3. `resultString = "<document name> BOM\n"` + header `Display Name,Part Number,Material,Count` + `traverseAssembly(bom)`, which with `showsubs` false emits only rows whose `sub < 1` (leaf components); each row is `"name","pn","material",<instances>,EA` — five fields under a four-column header, the unit `EA` being unlabelled. Text cells go through `_csv_cell`.
  4. Logs the CSV, then `ui.createFolderDialog()`; on `DialogOK` writes `os.path.join(folder, safe_name + ".csv")` where `safe_name` replaces `<>:"/\|?*` in `design.parentDocument.name` with `_`, encoding `utf-8-sig` (the BOM makes Excel read UTF-8; Fusion's Python on Windows would otherwise default to the ANSI code page and raise `UnicodeEncodeError` on, say, a diameter sign). Shows "BOM saved at: <path>". Cancel -> return, nothing written.
  5. Exceptions (caught in `command_created`) -> `ptutil.handle_error(CMD_NAME, show_message_box=True)`.
- `command_destroy(args)`: resets `local_handlers`.

## Data and state

- Module-level flags `showversion`, `showsubs` (constant — no inputs set them); `local_handlers`.
- Output: the user-chosen folder, `<sanitised document name>.csv`. No caches, settings, custom events or temp files.

## CSV injection guard

`_csv_cell(value)` stringifies the value and, when its first character is one of `=`, `+`, `-`, `@`, tab or CR, prefixes a single quote so a spreadsheet imports it as literal text. Interior characters are left alone; an empty string is not prefixed. It is applied to name, part number and material, not to the numeric count.

## Tests

- `tests/test_csv_injection.py` — imports `entry.py` under the `adsk` stub and pins `_csv_cell`: plain values pass through, each risky leading character is neutralised, empty values are not prefixed, non-strings are stringified first, interior formula characters are ignored.
- `tests/test_command_contract.py` — `CMD_Description`, literal `CMD_ID` shape, registry/doc/README contract.
- `tests/test_command_abort.py` — the `doExecute` AST guard.

`entry.py` is Fusion-bound and is not exercised by the suite beyond `_csv_cell`; nothing here is verified in Fusion on this branch except by the AST guards above, which import it under the `adsk` stub. The occurrence walk, the material concatenation and the row/header shape have no tests; no icon set exists to pin.

---

*Copyright © 2026 IMA LLC. All rights reserved.*
