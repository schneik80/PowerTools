# Assembly Statistics — Architecture

[← Assembly Statistics guide](../Assembly%20Statistics.md)

| | |
|---|---|
| **Command ID** | `PTAT_assemblystats` |
| **Registry** | group `assembly` (`Assembly`); enabled by default |
| **UI location** | Power Tools panel (`config.my_panel_id`, Design workspace, Tools tab) via [`_ui_bootstrap.get_power_tools_panel`](architecture.md#_ui_bootstrap); not promoted |
| **Files** | `commands/assemblystats/entry.py`; `resources/` PNG set (16/32/64, light and dark) plus the `assystats.idraw` / `assystats-d.idraw` sources, which `tools/release/build_release.py` excludes from the zip |
| **Shared helpers** | [`ptutil.add_handler`](architecture.md#event_utils); [`ptutil.log`, `isSaved`, `handle_error`](architecture.md#general_utils) |
| **Tests** | none module-specific |

## Purpose

Shows one modal summary of the active assembly: component counts and depth,
unique and out-of-date components, timeline contexts, constraints, tangent
relationships, joints by type and rigid groups. Most of the numbers are not
available through the API, so the command parses the output of two Fusion text
commands (`Component.AnalyseHierarchy`, `timeline.print`) and shows the lines
verbatim.

## How it is wired

- `start()`: `addButtonDefinition(CMD_ID, …)`, `commandCreated -> command_created`,
  control added to the Power Tools panel. `stop()`: removes the control and the
  definition.
- `command_created`: registers `execute -> command_execute` and
  `destroy -> command_destroy`, then stores the module globals `product`,
  `design` (`Design.cast(app.activeProduct)`) and `title`. Without a design it
  shows a message box and returns; then `ptutil.isSaved()` shows its own
  "Please Save" box for an unsaved document and the handler returns. No
  `CommandInputs` are added, so Fusion runs `command_execute` directly after
  `command_created` in every case.
- `command_execute` (all inside one `try`, errors to
  `ptutil.handle_error(CMD_NAME, show_message_box=True)`):
  1. `out_of_date_refs` = count of `app.activeDocument.documentReferences`
     with `isOutOfDate` (logged, not fatal).
  2. `total_unique = design.allComponents.count - 1` (the root excluded).
  3. `app.executeTextCommand("Component.AnalyseHierarchy")`, split into lines;
     the regex `.[a-zA-Z]\.+\D|\d\.+\D` strips the list numbering from each
     line into `statsList`.
  4. `app.executeTextCommand("timeline.print")`; `docContexts` = number of lines
     containing `Context` (an error string on failure).
  5. `rootComponent.assemblyConstraints.count`, `tangentRelationships.count`,
     `rigidGroups.count`.
  6. Builds an HTML string — `statsList[1..3]` (component lines), the two API
     counts, contexts, constraints, tangents, `statsList[4..16]` as the joint
     lines, rigid groups — and shows it with `ui.messageBox(resultString,
     f"{root_name} Component Statistics", 0, 2)`.
- `command_destroy`: clears `local_handlers`.

A block that read `fusion.computetime /f` is commented out because forcing the
compute dirties the document.

## Data and state

Module globals `product`, `design`, `title` set in `command_created` and read
in `command_execute`; `local_handlers`. No cache, settings keys or custom
events.

## Text-command dependence

The message is positional: `statsList[1]`–`[3]` and `[4]`–`[16]` are taken
from `Component.AnalyseHierarchy` by line index and are not parsed for meaning.
A Fusion build that changes the shape of that output changes the dialog (or
raises an `IndexError`, which surfaces through `handle_error`). Nothing in the
suite pins the expected shape.

## Diagram

None — the command is a linear read-and-report in `command_execute`; the
numbered list above is the sequence.

## Tests

- No module-specific test. `tests/test_command_contract.py` checks the
  registry entry, `CMD_ID` literal and description casing;
  `tests/test_command_abort.py` includes `command_created` in its AST guard;
  `tests/test_release_build.py` asserts `resources/assystats.idraw` is excluded
  from the release zip.
- `entry.py` is Fusion-bound and is not exercised by the suite; nothing here is
  verified in Fusion on this branch except by the AST guards in
  `tests/test_command_contract.py` and `tests/test_command_abort.py`, which
  import it under the `adsk` stub. The icon set is not pinned in
  `tests/test_command_icons.py`.

---

*Copyright © 2026 IMA LLC. All rights reserved.*
