# Assign Part Numbers — Architecture

[← Assign Part Numbers guide](../Assign%20Part%20Numbers.md)

## Architecture

### Command ID

`PTND_assignPartNumbers`

### System context

The following diagram shows the relationship between the user, the Assign Part Numbers command, Autodesk Fusion, and the Autodesk Hub.

```mermaid
C4Context
    title System Context — Assign Part Numbers
    Person(user, "Fusion User", "Designer assigning controlled part numbers")
    System(addin, "PowerTools Document Tools", "Autodesk Fusion add-in that stamps hub-unique part numbers onto components")
    System_Ext(fusion, "Autodesk Fusion", "CAD platform, host application, and Python API")
    System_Ext(hub, "Autodesk Hub", "Cloud data platform; holds the Assets project and the Pn-Cache folder")
    Rel(user, addin, "Invokes from Tools > Power Tools panel")
    Rel(addin, fusion, "Reads design intent, enumerates local components, writes partNumber via Fusion API")
    Rel(addin, hub, "Reads and writes Assets/Pn-Cache/pn-cache.json via Fusion DataFolder API")
    Rel(fusion, hub, "Persists component.partNumber on next document save")
```

### Component diagram

The following diagram shows how the internal components interact during a command invocation.

```mermaid
C4Component
    title Component Diagram — Assign Part Numbers
    Container_Boundary(addin, "Assign Part Numbers Command") {
        Component(button, "Command Button", "Fusion UI Control", "Toolbar button in Tools > Power Tools panel")
        Component(created, "command_created()", "Python", "Validates document and design; loads baseline counters; builds simple or table dialog")
        Component(intent, "intent.iter_targets()", "Python / partnumber_shared", "Enumerates root and unique local components; applies Fusion-auto-PN filter via is_fusion_auto_pn()")
        Component(schemes, "schemes.prefixes_for_intent()", "Python / partnumber_shared", "Returns allowed scheme prefixes for Part, Assembly, or Hybrid intent")
        Component(hub_fs, "hub_fs", "Python / partnumber_shared", "find_assets_project(); find_or_create_pn_cache_folder(); find_pn_cache_file()")
        Component(pn_cache, "pn_cache", "Python / partnumber_shared", "download_snapshot(); upload_snapshot(); commit_assignments() with optimistic retry")
        Component(validate, "command_validate_inputs()", "Python", "Disables Assign button until at least one row picks a real scheme")
        Component(input_changed, "command_input_changed()", "Python", "Recomputes per-row preview numbers on every scheme change")
        Component(execute, "command_execute()", "Python", "Confirms overwrites; commits cache; stamps component.partNumber and verifies each write with a readback")
        Component(destroy, "command_destroy()", "Python", "Clears dialog state; surfaces any deferred error after dialog closes")
    }
    System_Ext(fusion, "Autodesk Fusion", "Provides Component.partNumber, DataComponent.mfgdmModelId, DesignIntentTypes, DataFolder upload/download")
    System_Ext(hub, "Autodesk Hub", "Stores Assets/Pn-Cache/pn-cache.json with full version history")
    System_Ext(mfgdm_gql, "MFGDM GraphQL API", "Cloud service that backs Component.partNumber reads and writes for saved documents")

    Rel(button, created, "Triggers on click")
    Rel(created, intent, "Builds Target list")
    Rel(created, schemes, "Filters dropdown items per row")
    Rel(created, pn_cache, "Loads baseline counters for preview")
    Rel(pn_cache, hub_fs, "Resolves Assets project and Pn-Cache folder")
    Rel(hub_fs, fusion, "Walks app.data.activeHub and DataProject.rootFolder")
    Rel(pn_cache, fusion, "Uploads/downloads pn-cache.json via DataFolder")
    Rel(input_changed, schemes, "Formats preview as prefix + (baseline + offset)")
    Rel(validate, execute, "Gates OK button")
    Rel(execute, pn_cache, "commit_assignments() with per-prefix increments")
    Rel(execute, fusion, "Writes component.partNumber; reads it back to verify")
    Rel(fusion, mfgdm_gql, "partNumber set routes through MFGDM GraphQL on saved docs")
    Rel(execute, destroy, "Stashes any error for post-close surfacing")
```

### Execution flow

The following diagram shows the step-by-step flow when the user runs the command.

```mermaid
flowchart TD
    A[User clicks Assign Part Numbers] --> B{Document saved?}
    B -- No --> B1[Show error; abort]
    B -- Yes --> C{Active Fusion 3D Design?}
    C -- No --> C1[Show error; abort]
    C -- Yes --> D[Enumerate targets: root + unique local occurrences]
    D --> E[Filter Fusion auto-generated placeholder PNs to empty]
    E --> F[Download pn-cache.json from hub\npopulate baseline counters]
    F --> G{Local components?}
    G -- No --> G1[Build simple dialog:\nlabel + optional current P/N +\nwarning note if current P/N exists +\nscheme dropdown + preview]
    G -- Yes --> G2[Build table dialog:\nwarning note listing components\nwith existing P/N +\none row per target]
    G1 --> H[User picks schemes]
    G2 --> H
    H --> I[Live preview updates:\nbaseline counter + per-prefix offset]
    I --> J{User clicks Assign?}
    J -- No / Cancel --> J1[Dialog closes; no changes]
    J -- Yes --> L[commit_assignments: download + modify +\nupload + verify, up to 3 retries]
    L --> L1{Cache commit succeeded?}
    L1 -- No --> L2[Stash error; dialog closes;\nerror surfaced in destroy]
    L1 -- Yes --> M[For each target:\nset component.partNumber\nthen read back and verify match]
    M --> M1{All readbacks matched?}
    M1 -- No --> M2[Stash per-target mismatch error]
    M1 -- Yes --> N[Dialog closes]
    M2 --> N
    N --> O[destroy clears state and\nshows any deferred error]
```

### Data model

The following diagram shows the relationships between the core data structures used by the command and the shared `partnumber_shared` package.

```mermaid
classDiagram
    class Target {
        +str label
        +Component component
        +int intent_value
        +str current_pn
        +bool is_root
        +str chosen_prefix
        +int chosen_number
    }

    class SchemeRegistry {
        +list~tuple~ SCHEMES
        +list~str~ SCHEME_PREFIXES
        +dict SCHEME_LABEL
        +int NUMBER_WIDTH
        +prefixes_for_intent(intent_value) list
        +format_number(prefix, n) str
    }

    class Snapshot {
        +dict~str,int~ counters
        +int source_version_number
        +dict raw
        +last_used(prefix) int
    }

    class CommitResult {
        +Snapshot snapshot_before
        +dict~str,int~ counters_after
        +int new_version_number
        +int retries_used
    }

    class HubFs {
        +find_assets_project(app) DataProject
        +find_or_create_pn_cache_folder(project) DataFolder
        +find_pn_cache_file(folder) DataFile
    }

    class PnCache {
        +download_snapshot(folder, tmp_dir) Snapshot
        +upload_snapshot(folder, counters, user, tmp_dir) int
        +commit_assignments(app, increments, user, tmp_dir) CommitResult
    }

    PnCache --> Snapshot : reads/returns
    PnCache --> CommitResult : returns
    PnCache --> HubFs : uses
    CommitResult --> Snapshot : snapshot_before
    Target --> SchemeRegistry : filtered via prefixes_for_intent
```

### Pn-Cache JSON

The shared counter file at `Assets / Pn-Cache / pn-cache.json` has the following shape. All six schemes are always written back, missing counters default to zero.

```json
{
  "version": 1,
  "schemes": {
    "PRT": { "lastUsed": 42 },
    "ASY": { "lastUsed": 7 },
    "WLD": { "lastUsed": 0 },
    "COT": { "lastUsed": 15 },
    "TOL": { "lastUsed": 3 },
    "DWG": { "lastUsed": 9 }
  },
  "updatedAt": "2026-04-19T18:22:10Z",
  "updatedBy": "<user-id>"
}
```

### Concurrency

The cache commit flow is a read-modify-write with optimistic retry, gated so `component.partNumber` is only stamped after the hub cache upload has been verified:

1. Download the latest `pn-cache.json` and remember the baseline counters.
2. Compute the new counters in memory by adding the per-prefix increments.
3. Upload the new JSON (creates a new version of the DataFile).
4. Re-download and verify the live counters match what we just wrote.
5. If another user raced us (the live counters disagree with ours), retry from step 1.
6. Cap at three retries. On the fourth failure, abort without stamping any component.
7. Only after the cache is durable: set `component.partNumber` on each target.

This guarantees the cache and the component stamps never diverge: either the cache records the number and the component is stamped, or neither happens.

### Cloud metadata (MFGDM) readiness

Autodesk's `Component.partNumber` setter routes through the MFGDM GraphQL API for saved documents. The cloud service keys each component by a timeless `mfgdmModelId` that is generated by the cloud when the component is first saved. Two known states produce an empty `mfgdmModelId` and cause the legacy setter to **silently fail**:

- A local component was added to a saved design but the design has not been saved since. Internal components get their cloud ID only on the next parent-document save.
- The document was just opened or saved and the `MFGDMDataReady` event hasn't fired yet — cloud ingestion lag.

**Detection strategy**: the command detects these failures after-the-fact via **readback verification** in `command_execute`. After every `component.partNumber = value`, the property is read back. A mismatch is recorded as a stamp error and surfaced to the user through the post-close warning message — even when the setter call itself did not raise an exception. Affected components are listed by name so the user can save the document and re-run the command.

**Why not pre-flight?** An earlier iteration of this command attempted a synchronous pre-flight that read `component.dataComponent.mfgdmModelId` from inside `command_created`. Autodesk's own sample code only ever accesses this property from inside an `MFGDMDataReady` event callback — the property is part of a preview API and reading it outside that event is not supported. In practice, reading it synchronously followed by a `ui.messageBox` + `args.command.doExecute(True)` cancel sequence crashed Fusion on dismiss. The readback gate covers the same failure mode without entering that fragile code path.

The MFGDM GraphQL API also exposes a direct `assignModelPartNumber` mutation that bypasses the legacy setter. This command deliberately does **not** call it today — the legacy setter remains the canonical path Autodesk is optimizing, and the readback gate covers the documented silent-failure mode. A future migration to direct GraphQL stamping — gated on an `MFGDMDataReady`-driven worker — is straightforward if field testing shows the readback gate is insufficient.

**Trade-off**: because the pre-flight is gone, a silent stamp failure now consumes the cache counter the stamp would have used. The number is not written to the component, but the next successful stamp will use the number after it. Numbers are cheap; a crash is not.
