# Timeline Compute Report — Architecture

[← Timeline Compute Report guide](../Timeline%20Compute%20Times.md)

| | |
|---|---|
| **Command ID** | `PTPM_timelinecompute` |
| **Registry** | group `partmodeling` (`Part Modeling`); enabled by default |
| **UI location** | Design workspace, **Solid** tab (`SolidTab`), **Inspect** panel (`InspectPanel`); appended at the end of the panel with `addCommand(cmd_def, "", True)`, not promoted. Only this one Inspect panel, unlike Measure Path, which uses [`_inspect_panels`](architecture.md#_inspect_panels) to reach every design tab. `CMD_AFTER = "InterferenceCheckCommand"` is defined but never passed as a `positionID`. |
| **Files** | `commands/timelinecompute/entry.py`; `resources/` PNG icons (16/32/64, light and dark); `resources/bar/sequence/000.svg` … `100.svg` (101 percentage-bar images referenced from the report) |
| **Shared helpers** | [`ptutil.add_handler`](architecture.md#event_utils); [`ptutil.log`, `ptutil.handle_error`, `ptutil.require_document`](architecture.md#general_utils); [`config.design_workspace`](architecture.md#config) |
| **Tests** | none module-specific (see [Tests](#tests)) |

## Purpose

Produces an HTML report of the compute time of every feature in a parametric design's timeline, sorted by Fusion from shortest to longest, and opens it in Fusion's embedded browser; the raw CSV is left in the system temp directory as source data. The command has no inputs, so Fusion auto-executes it. Direct Design documents are refused because they have no timeline.

## How it is wired

- `start()`: `addButtonDefinition(...)`; `ptutil.add_handler(cmd_def.commandCreated, command_created)`; `ui.workspaces.itemById(config.design_workspace)` (log and return if missing); `toolbarTabs.itemById("SolidTab")` or `toolbarTabs.add("SolidTab", "Solid")`; `toolbarPanels.itemById("InspectPanel")` or `toolbarPanels.add("InspectPanel", "Inspect", "", False)`; `panel.controls.addCommand(cmd_def, "", True)`, `isPromoted = False`. Both containers are built in, so the create branches do not run in practice.
- `stop()`: deletes the control and the definition; the trailing delete-if-empty branches for the panel and the tab cannot fire on built-in containers that still hold Fusion's own controls.
- `command_created(args)`: registers `execute` → `command_execute` and `destroy` → `command_destroy`. No `CommandInputs`, so Fusion's default `isAutoExecute` runs the command immediately; the Solid tab is only reachable with a design open, so `execute` does fire ([why that matters](architecture.md#acting-from-commandcreated-when-there-are-no-inputs)).
- `command_execute(args)`, in order:
  1. `design = ptutil.require_document(CMD_NAME, "design")` (`None` → it has shown the standard message; return), then `doc_name = app.activeDocument.name`; if `design.designType == DirectDesignType`, message box and return.
  2. `features_data = app.executeTextCommand("fusion.DumpFeaturesByComputeTime /csv")`.
  3. `_create_temp_csv_file(features_data)` writes it to `tempfile.gettempdir()/<secrets.token_urlsafe(8)>.csv`.
  4. `_calculate_total_compute_time(csv_path)`: `csv.reader`, skip the header, sum `float(row[2])`; malformed rows are logged and skipped.
  5. `_generate_html_report(doc_name, csv_path, total)` writes `<tmp>/<token>.html` as the concatenation of `_get_html_css()` (the `<style>` block, emitted *before* the `<!DOCTYPE html>` that `_get_html_header` opens), `_get_html_header` (title, total as `format_time_duration` → `h:mm:ss.mmm`), `_get_table_header` (Component, Feature, Time (seconds), Percent, Health), `_generate_table_content` and `_get_html_footer`; returns the POSIX path.
  6. `app.executeTextCommand(f"QTWebBrowser.Display file:///{html_filepath}")`.
  Any exception goes to `ptutil.handle_error("Timeline compute")` and a message box.
- `command_destroy(args)`: clears `local_handlers`.

## Data and state

Two files per run in `tempfile.gettempdir()`, `<random>.csv` and `<random>.html`, named with `secrets.token_urlsafe(8)`; neither is deleted. No settings keys, no custom events, no module state beyond `local_handlers`.

## The report

`_generate_table_content` re-reads the CSV. For each data row: percent = `round(time / total × 100)` clamped to 0–100 and formatted `03d` (a bad or zero total gives `000`); the row is padded to four columns and every cell passes through `_escape_html`; the fourth column is wrapped in a badge whose class is chosen by substring (`error` → `health-error`, `warning` → `health-warning`, any other non-empty text → `health-healthy`); the percent cell is `<img src="file:///<add-in>/commands/timelinecompute/resources/bar/sequence/NNN.svg"> NN%`, so the bar graphics are read straight from the installed add-in folder by `_get_bar_sequence_path`. The CSV layout is assumed, not checked: column 3 is seconds and column 4 is the health state. The whole page is stdlib-built text with no script or external asset other than those SVGs.

## Diagram

None: the flow is a single ordered pipeline (text command → CSV → total → HTML → browser) and the numbered list above states it exactly.

## Tests

- No module-specific test. `tests/test_command_contract.py` imports `entry.py` under the `adsk` stub and checks the `CMD_ID` shape, `CMD_Description`, the registered doc filename, this note, the arch index row and the README row; `tests/test_command_abort.py` scans `command_created` for `doExecute` calls.
- `tests/test_release_build.py::test_runtime_paths_ship` uses a `commands/timelinecompute/resources/…svg` path only as an example that resource SVGs are not excluded from the release zip; it does not exercise this command.
- `entry.py` is Fusion-bound and is not otherwise exercised by the suite; nothing here is verified in Fusion on this branch except by those AST guards. The icon set is not pinned in `tests/test_command_icons.py`.

---

*Copyright © 2026 IMA LLC. All rights reserved.*
