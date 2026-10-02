# Document Information — Architecture

[← Document Information guide](../Document%20Information.md)

| | |
|---|---|
| **Command ID** | `PTND_docinfo` |
| **Registry** | module `docinfo`, group `document` (`Document Tools`); enabled by default; not beta |
| **UI location** | Design workspace → Tools tab → shared "Power Tools" panel (`config.my_panel_id`) via `_ui_bootstrap.get_power_tools_panel()`; and Drawing workspace → `FusionDocTab` → "Power Tools" panel (`config.drawing_panel_id`) via `_drawing_panel`, after Assign Drawing Number; and the four electronics panels (project, Schematic Editor, PCB Editor, 3D PCB) via [`_electronics_panels`](architecture.md#_electronics_panels); promoted button everywhere |
| **Files** | `commands/docinfo/entry.py`; `mfgdm_status.py` (adsk-free: MFGDM queries, summaries, dialog HTML); `resources/` (16/32/64 px light + dark icons; `docinfo.idraw` is the design source and is stripped from the release zip) |
| **Shared helpers** | [`_ui_bootstrap.get_power_tools_panel`](architecture.md#_ui_bootstrap); [`_drawing_panel`](architecture.md#_drawing_panel); [`_electronics_panels`](architecture.md#_electronics_panels); [`partnumber_shared.mfgdm_props.gql`](architecture.md#partnumber_shared) (the `mfgdm://v3` transport); [`ptutil.add_handler`](architecture.md#event_utils); [`ptutil.require_document`, `document_required_message`, `log`, `handle_error`](architecture.md#general_utils) |
| **Tests** | `tests/test_docinfo_mfgdm_status.py`; `tests/test_release_build.py`; `tests/test_command_contract.py` |

## Purpose

Shows the cloud data identifiers behind the active design or drawing — hub, project, parent folder, full folder path, document id, version position, the Fusion build that last saved it — and whether MFGDM holds a record for it, in one HTML message box. When the saving build differs from the running one, the title and body warn that the document will migrate to the current schema on save. For a drawing it also compares the design the drawing references locally with the design MFGDM links it to.

## How it is wired

- `start()`: `addButtonDefinition` with the resources folder; `ptutil.add_handler(cmd_def.commandCreated, command_created)`; on the shared Design panel (created by `_ui_bootstrap.create_shared_access_points()`) `panel.controls.addCommand(cmd_def)`, `isPromoted = True`; then `_drawing_panel.add_to_drawing_panel(cmd_def, CMD_NAME, True)`.
- `stop()`: deletes the Design control, `remove_from_drawing_panel(CMD_ID, CMD_NAME)` (the panel goes when empty), then the definition.
- `command_created(args)`: registers `command_execute` and `command_destroy`. No `CommandInputs`, so Fusion auto-executes; with no document open the button does nothing (rule 1). Both toolbars are visible only with a document open, which is why this command is in `KNOWN_EXECUTE_ONLY_INPUTLESS`.
- `command_execute(args)`:
  1. `doc = ptutil.require_document(CMD_NAME, "document", saved=True)` is `None` → return (see [Document preconditions](architecture.md#document-preconditions)).
  2. `isinstance(doc, adsk.drawing.DrawingDocument)` picks the drawing branch, `isinstance(doc, (adsk.electron.EcadDesignDocument, SchematicDocument, BoardDocument))` the electronics branch. Otherwise `_design_of(doc)` (`products.itemByProductType("DesignProductType")`); `None` → the standard "needs a design open" message.
  3. Title from `doc.name` (drawing) or `design.rootComponent.name`. Hub from `dataFile.parentProject.parentHub` — the document's own hub — then project, folder (`"Project Root"` when `isRoot`), the `parentFolder` walk to `A / B / C / <file name>`, `dataFile.id/.name/.versionNumber/.latestVersionNumber/.description`, `doc.version` and `app.version`.
  4. MFGDM block, under `progressBar.showBusy` with one `adsk.doEvents()`:
     - Design (including a 3D PCB): `mfgdm_status.model_summary(gql, mfgdm_props.design_model_id(design))` → `render_design`.
     - Electronics project / schematic / 2D PCB: `item_summary(gql, hub.mfgdmId, dataFile.id)` → `render_file`.
     - Drawing (`_drawing_mfgdm`): `item_summary(gql, hub.mfgdmId, dataFile.id)`; then `documentReferences.item(0)`: its `dataFile.name/.id`, and — only if `referencedDocument` is already loaded — `model_summary` of that design, else a `NOT_LOADED` summary. `render_drawing` adds the mismatch warning when `source_mismatch(ref.dataFile.id, tipDrawing.model.designItem.id)`.
  5. `ui.messageBox(text, title, 0, icon)`: icon `3` when the builds differ or the MFGDM block warns, else `2`; a build difference also changes the title and appends the migration warning.
  Exceptions → `ptutil.handle_error(CMD_NAME, show_message_box=True)`.
- `command_destroy(args)`: drops `local_handlers`.

## MFGDM check

The desktop API reaches MFGDM differently for the two document kinds:

| Kind | Local handle | Query (`mfgdm_status`) |
|---|---|---|
| Design | `rootDataComponent.mfgdmModelId`, falling back to `rootComponent.mfgdmModelId` (`mfgdm_props.design_model_id`) | `MODEL_QUERY`: `model(modelId) { id component { id hub { id } partNumber { value } itemNumber { id } } designItem { id name } }` |
| Electronics project / schematic / 2D PCB | none; `DataHub.mfgdmId` + `DataFile.id`, as for a drawing | `ITEM_QUERY` → `BasicItem { extensionType tipVersion { versionNumber } }`: a file record with no model, rendered by `render_file` |
| Drawing | none; `DataHub.mfgdmId` (`urn:adsk.ace:…`) + `DataFile.id` (lineage urn) | `ITEM_QUERY`: `item(hubId, itemId)` → `DrawingItem { tipVersion { versionNumber } tipDrawing { id itemNumber { id } lifecycle { state { value } revision { value } } model { id designItem { id name } } } }` |

Every summary carries one status: `ok`, `missing` (MFGDM answered with no record), `no_local_id` (nothing to ask with — the ids arrive after a save), `not_loaded` (a drawing's source design is not open; it is never opened), or `error` (transport or GraphQL failure, message kept). `fetch()` never raises, so the identifiers above the block always show. Only `ok` lists ids; every other status renders a one-line verdict. All values are HTML-escaped.

Model-id reads happen in `execute`, never `commandCreated` (234b043).

## Data and state

`local_handlers` only. Everything shown is read live from the active document, its `dataFile` and MFGDM; no disk cache, no settings keys, no custom events.

## Tests

- `tests/test_docinfo_mfgdm_status.py` — summaries of the live-recorded `DrawingItem`, `BasicItem` and `Model` answers, null and partly-null answers, no query without a local id, the transport-error path, the mismatch rule (only a provable disagreement), the warn flag per status, HTML escaping.
- `tests/test_release_build.py` — pins that `commands/docinfo/resources/docinfo.idraw` is excluded from the release zip.
- `tests/test_command_contract.py` — registry row, `CMD_Description`, docs pair, `CMD_ID` shape.

The icon set is not pinned in `tests/test_command_icons.py` (it is the `placeholder` three other pinned sets are asserted to differ from). `entry.py`, `_drawing_panel.py` and the placement half of `_electronics_panels.py` are Fusion-bound and not exercised by the suite.

## Learnings

- **Electronics files are MFGDM `BasicItem`s.** The project, schematic and 2D PCB resolve through `item(hubId, itemId)` like a drawing, but carry only a file record; the 3D PCB is a `DesignItem` whose `rootDataComponent` is populated (ADSKMVG91G2F5W, pre-production 2706.0.116, 2026-10-02).

- **A drawing has no local MFGDM id.** `DrawingDocument` adds only `.drawing`; `Drawing` adds `exportManager`, `activeSheet`, `documentSettings`. `DataHub.mfgdmId` plus `DataFile.id` into `item(hubId, itemId)` is the way in (probed with the Fusion MCP on ADSKMVG91G2F5W, pre-production, 2026-10-01).
- **`productType` raises on a drawing.** `activeProduct.productType` and `doc.products.item(i).productType` threw `InternalValidationError : adapter` with a drawing active; branch on `DrawingDocument` instead.
- **`rootDataComponent` can be `None` on a loaded design.** On the design a drawing referenced, `rootDataComponent` was `None` while `rootComponent.mfgdmModelId` held the id MFGDM's `tipRootModel.id` matched — hence the fallback in `mfgdm_props.design_model_id`, which Assign Drawing Number uses too.
- **MFGDM and the local reference can disagree, through a Fusion bug.** "Arm1 Drawing Copy" referenced "Arm1" locally while `tipDrawing.model.designItem` was "Arm1 Copy". The owner confirmed this is a Fusion defect, not a supported state; the mismatch warning exists to surface it, and the user doc tells users to report it.

---

*Copyright © 2026 IMA LLC. All rights reserved.*
