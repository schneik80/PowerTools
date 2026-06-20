# Assign Drawing Number — Architecture

[← Assign Drawing Number guide](../Assign%20Drawing%20Number.md)

## Architecture

### Command ID

`PTND-assignDrawingNumber`

### System context

The following diagram shows the relationship between the user, the Assign Drawing Number command, Autodesk Fusion, and the Autodesk Hub.

```mermaid
C4Context
    title System Context — Assign Drawing Number
    Person(user, "Fusion User", "Designer assigning controlled drawing numbers")
    System(addin, "PowerTools Document Tools", "Autodesk Fusion add-in that stamps hub-unique drawing numbers")
    System_Ext(fusion, "Autodesk Fusion", "CAD platform, host application, and Python API")
    System_Ext(hub, "Autodesk Hub", "Cloud data platform; holds the Assets project and the Pn-Cache folder")
    Rel(user, addin, "Invokes from Document > Power Tools panel")
    Rel(addin, fusion, "Reads active drawing; writes Fusion Attribute via Fusion API")
    Rel(addin, hub, "Reads and writes Assets/Pn-Cache/pn-cache.json via Fusion DataFolder API")
    Rel(fusion, hub, "Persists drawing attribute on next document save")
```

### Component diagram

The following diagram shows how the internal components interact during a command invocation.

```mermaid
C4Component
    title Component Diagram — Assign Drawing Number
    Container_Boundary(addin, "Assign Drawing Number Command") {
        Component(button, "Command Button", "Fusion UI Control", "Toolbar button in Drawing workspace > Document tab > Power Tools panel")
        Component(created, "command_created()", "Python", "Validates drawing document; peeks the next DWG number; builds a simple preview dialog")
        Component(peek, "_peek_next_drawing_number()", "Python", "Best-effort read of the hub DWG counter for the dialog preview")
        Component(hub_fs, "hub_fs", "Python / partnumber_shared", "find_assets_project(); find_or_create_pn_cache_folder(); find_pn_cache_file()")
        Component(pn_cache, "pn_cache", "Python / partnumber_shared", "download_snapshot(); upload_snapshot(); commit_assignments() with optimistic retry")
        Component(execute, "command_execute()", "Python", "Confirms overwrite; commits cache; writes Fusion Attribute on the drawing; invokes titleblock sync")
        Component(read_attr, "_read_existing_drawing_number()", "Python", "Reads PowerTools.PartNumber/assigned attribute if present")
        Component(write_attr, "_write_drawing_attribute()", "Python", "Writes PowerTools.PartNumber/assigned attribute on the DrawingDocument")
        Component(sync, "_sync_drawing_number_to_source_design()", "Python", "Navigates drawing's first DocumentReference; silently opens the source design if needed; calls mfgdm_props.set_component_custom_property(); closes the silently-opened doc")
        Component(mfgdm_props, "mfgdm_props", "Python / partnumber_shared", "Generic MFGDM GraphQL client: _gql() HTTP wrapper + set_component_custom_property() runs a two-tier definition-id lookup (Component.allProperties fast path; Hub.propertyDefinitionCollections fallback) then calls setProperties mutation")
        Component(missing_html, "_missing_custom_property_html()", "Python", "Builds an HTML-formatted warning with a clickable link to DRAWING_NUMBER_SETUP_URL when the source design has no Drawing Number custom property")
        Component(destroy, "command_destroy()", "Python", "Clears state; surfaces any deferred error (including the titleblock-sync error HTML) after dialog closes")
    }
    System_Ext(fusion, "Autodesk Fusion", "Provides DrawingDocument, DocumentReferences, adsk.core.Attribute, DataFolder upload/download, silent documents.open()")
    System_Ext(hub, "Autodesk Hub", "Stores Assets/Pn-Cache/pn-cache.json with full version history")
    System_Ext(mfgdm_gql, "MFGDM GraphQL API (mfgdm://v3)", "Cloud service that backs custom-property reads and writes. Exposes setProperties mutation on Component when isWritableByUser=True")

    Rel(button, created, "Triggers on click")
    Rel(created, peek, "Loads next DWG number for preview")
    Rel(created, read_attr, "Reads existing assigned attribute")
    Rel(peek, pn_cache, "download_snapshot()")
    Rel(pn_cache, hub_fs, "Resolves Assets project and Pn-Cache folder")
    Rel(hub_fs, fusion, "Walks app.data.activeHub and DataProject.rootFolder")
    Rel(pn_cache, fusion, "Uploads/downloads pn-cache.json via DataFolder")
    Rel(execute, pn_cache, "commit_assignments({'DWG': 1})")
    Rel(execute, write_attr, "Stamps attribute on successful commit")
    Rel(write_attr, fusion, "doc.attributes.add(group, name, value)")
    Rel(execute, sync, "Calls titleblock sync after successful drawing-side stamp")
    Rel(sync, fusion, "documentReferences; silent app.documents.open(); rootDataComponent.mfgdmModelId; doc.close()")
    Rel(sync, mfgdm_props, "set_component_custom_property(modelId, 'Drawing Number', number)")
    Rel(mfgdm_props, mfgdm_gql, "Query componentId + allProperties (fast path); if miss, query Hub.propertyDefinitionCollections (fallback); then setProperties mutation — all via HttpRequest('mfgdm://v3')")
    Rel(sync, missing_html, "Builds error HTML on PropertyNotFoundError")
    Rel(execute, destroy, "Stashes any error for post-close surfacing")
```

### Execution flow

The following diagram shows the step-by-step flow when the user runs the command.

```mermaid
flowchart TD
    A[User clicks Assign Drawing Number] --> B{Document saved?}
    B -- No --> B1[Show error; abort]
    B -- Yes --> C{Active document is a DrawingDocument?}
    C -- No --> C1[Show error; abort]
    C -- Yes --> D[Read existing assigned attribute if any]
    D --> E[Peek next DWG number from hub cache]
    E --> F{Existing assigned\nattribute found?}
    F -- Yes --> F1[Build dialog:\nScheme + Current number + inline\noverwrite warning + Will assign preview]
    F -- No --> F2[Build dialog:\nScheme + Will assign preview]
    F1 --> G{User clicks Assign?}
    F2 --> G
    G -- No / Cancel --> G1[Dialog closes; no changes]
    G -- Yes --> I[commit_assignments: download + modify +\nupload + verify, up to 3 retries]
    I --> I1{Cache commit succeeded?}
    I1 -- No --> I2[Stash error; dialog closes;\nerror surfaced in destroy]
    I1 -- Yes --> J[Write Fusion Attribute:\ngroup=PowerTools.PartNumber name=assigned\nreplacing any prior value]
    J --> S1{drawing.documentReferences\ncount >= 1?}
    S1 -- No --> S1a[Log 'no source reference';\nskip titleblock sync]
    S1 -- Yes --> S2{Source design\nalready open?}
    S2 -- No --> S2a[app.documents.open\nvisible=False]
    S2 -- Yes --> S3
    S2a --> S3[Resolve source design's\nrootDataComponent.mfgdmModelId]
    S3 --> S4{modelId non-empty?}
    S4 -- No --> S4a[Log 'cloud metadata\nnot ready';\nstash warning]
    S4 -- Yes --> S5[mfgdm_props:\nfetch componentId +\nallProperties.results]
    S5 --> S5a{Drawing Number present in\nallProperties?}
    S5a -- Yes --> S7
    S5a -- No --> S5b[Walk hub's\npropertyDefinitionCollections\nfor name=Drawing Number\nnot archived]
    S5b --> S6{Match found\nin any collection?}
    S6 -- No --> S6a[Stash HTML error with\nsetup-guide link]
    S6 -- Yes --> S7[setProperties mutation\ntargetId=componentId,\npropertyDefinitionId,\nvalue=new DWG number]
    S7 --> S8{Silently opened source doc?}
    S1a --> K
    S4a --> K
    S6a --> K
    S8 -- Yes --> S8a[Close source doc no-save]
    S8 -- No --> K
    S8a --> K[Dialog closes]
    K --> L[destroy clears state and\nshows any deferred error\nHTML rendered with clickable link]
```

### Storage

The assigned drawing number is written to two locations on successful Assign:

**On the drawing document itself** (canonical local record):

| Location | Value |
|---|---|
| `DrawingDocument.attributes` | — |
| &nbsp;&nbsp;group | `PowerTools.PartNumber` |
| &nbsp;&nbsp;name | `assigned` |
| &nbsp;&nbsp;value | formatted number, e.g., `DWG-000042` |

**On the source design's root component** (titleblock hook):

| Location | Value |
|---|---|
| MFGDM GraphQL — `Component.customProperties` on the root `mfgdmModelId` | — |
| &nbsp;&nbsp;propertyDefinition.name | `Drawing Number` (configurable via `DRAWING_NUMBER_PROPERTY_NAME`) |
| &nbsp;&nbsp;value | same formatted number, e.g., `DWG-000042` |

Both writes persist independently: the drawing-side attribute survives even if the titleblock sync fails, so the drawing is still correctly numbered locally.

### MFGDM GraphQL titleblock sync

The custom-property write goes through the MFGDM v3 GraphQL endpoint. Key facts the implementation depends on:

- Custom properties are **not** exposed through `Component.propertyGroups` on the Fusion Desktop Python API — that surface only covers the built-in `General` group (Part Name, Part Number, Description).
- `setProperties` is callable from the Fusion Desktop API despite Autodesk's own documentation suggesting it is blocked. The mutation succeeds when the target component's `isWritableByUser` is `True` and the property's `definition.isReadOnly` is `False` — both true for a user's own hub-configured Custom Properties collection.
- `SetPropertiesInput.targetId` must be the **`Component.id`** (time-specific, obtained via `model(modelId).component.id`). Using the timeless `mfgdmModelId` returns `"The targetId is not a valid Component or Drawing ID."`
- `SetPropertiesInput.propertyInputs` is a list of `{ propertyDefinitionId, value }`. The implementation never hard-codes a definition id — it's resolved dynamically via a two-tier lookup (below).

#### Two-tier property-definition lookup

The helper `set_component_custom_property()` resolves the property definition id through two queries in sequence:

1. **Fast path — `Component.allProperties`.** Reads the component's current property snapshot. This surfaces the definition id quickly when the property already has a value on this component, or when it is a base property (Part Name, Part Number, Description, etc.).

2. **Fallback — `Hub.propertyDefinitionCollections`.** When the fast path misses, the helper walks the hub's property-definition collections looking for a non-archived definition whose `name` matches. This is required because MFGDM's `Component.allProperties` and `Component.customProperties` only include properties that have a value set on the specific component — a defined-but-unset custom property (typical on the first-ever write to a new design) is filtered out and would otherwise look "missing." Walking the hub's collections surfaces the definition regardless of whether it has ever been assigned a value.

Only when **both** lookups fail does the helper raise `PropertyNotFoundError`, which triggers the setup-guide error dialog in the drawing command.

The plumbing lives in `commands/partnumber_shared/mfgdm_props.py`:

| Symbol | Role |
|---|---|
| `MFGDM_URL` | `"mfgdm://v3"` — Fusion-internal URL scheme that transparently attaches user auth |
| `MfgdmPropsError` | Base exception for HTTP, GraphQL, or auth failures |
| `PropertyNotFoundError` | Raised when the named property is not defined anywhere in the hub's property-definition collections. Callers treat this distinctly to trigger the setup-guide error dialog |
| `_find_definition_in_hub(hub_id, name)` | Private helper — walks `Hub.propertyDefinitionCollections.results[].definitions.results[]` and returns the first non-archived match |
| `set_component_custom_property(model_id, property_name, value)` | Public one-shot helper: fetches componentId, runs the two-tier definition lookup, runs the `setProperties` mutation, returns the echoed value |

The drawing command's `_sync_drawing_number_to_source_design()` orchestrates the workflow above (navigate `documentReferences[0]` → silently open source design if needed → call `set_component_custom_property` → close source design if we opened it).

### Shared infrastructure

This command shares the hub cache infrastructure with [Assign Part Numbers](../Assign%20Part%20Numbers.md). See that document for:

- The **Pn-Cache JSON** shape and location.
- The **concurrency** model (optimistic retry + upload verification).
- Details of the `partnumber_shared.hub_fs`, `partnumber_shared.pn_cache`, and `partnumber_shared.schemes` modules.

The `partnumber_shared.mfgdm_props` module introduced for this command is also available for reuse by any future command that needs to read or write custom properties via MFGDM GraphQL.
