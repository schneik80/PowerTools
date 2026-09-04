# Version Diff — Architecture

[← Version Diff guide](../Version%20Diff.md)

## Architecture

### System context

The following diagram shows the relationship between the user, the Version Diff command, Autodesk Fusion, and the file system.

```mermaid
C4Context
    title System Context — Version Diff
    Person(user, "Fusion User", "Designer comparing design versions")
    System(addin, "PowerTools Document Tools", "Autodesk Fusion add-in that compares timeline features between document versions")
    System_Ext(fusion, "Autodesk Fusion", "CAD platform, host application, and Python API")
    System_Ext(hub, "Autodesk Hub", "Cloud document storage with version history")
    System_Ext(filesystem, "File System", "System temporary directory for JSON and HTML output")
    Rel(user, addin, "Invokes from Tools > PowerTools panel")
    Rel(addin, fusion, "Reads timeline features and version metadata via Fusion API")
    Rel(fusion, hub, "Retrieves document versions and opens comparison version read-only")
    Rel(addin, filesystem, "Writes JSON data and HTML report files")
    Rel(fusion, user, "Opens HTML report in built-in browser")
```

### Component diagram

The following diagram shows how the internal components of the command interact during execution.

```mermaid
C4Component
    title Component Diagram — Version Diff
    Container_Boundary(addin, "Version Diff Command") {
        Component(button, "Command Button", "Fusion UI Control", "Toolbar button in Tools > PowerTools panel")
        Component(dialog, "command_created()", "Python", "Validates design state; builds dialog with version metadata and comparison dropdown")
        Component(handler, "command_execute()", "Python", "Opens comparison version, walks both timelines, computes diff, generates report")
        Component(walker, "walk_timeline()", "Python", "Iterates timeline items; extracts feature name, type, health state; parses XREF occurrence names for component and version")
        Component(differ, "compute_diff()", "Python", "Matches features by identity key; classifies as newer, deleted, unchanged, or version_changed; builds aligned two-column rows")
        Component(htmlgen, "generate_html_report()", "Python", "Builds version cards, summary badges, and two-column diff table; writes styled HTML to temp file")
        Component(jsongen, "save_diff_json()", "Python", "Serializes complete DiffResult to JSON temp file")
    }
    System_Ext(fusion, "Autodesk Fusion", "Provides Timeline API, DataFile version access, and built-in QT browser")
    System_Ext(filesystem, "File System (Temp)", "Stores output JSON and HTML files")

    Rel(button, dialog, "Triggers on click")
    Rel(dialog, handler, "Fires on OK with selected version")
    Rel(handler, walker, "Walks baseline and comparison timelines")
    Rel(walker, fusion, "Reads timeline items and occurrence names")
    Rel(handler, differ, "Passes two feature lists")
    Rel(handler, jsongen, "Passes DiffResult")
    Rel(jsongen, filesystem, "Writes .json file")
    Rel(handler, htmlgen, "Passes DiffResult")
    Rel(htmlgen, filesystem, "Writes .html file")
    Rel(handler, fusion, "Opens HTML in QT browser")
```

### Command execution flow

The following diagram shows the step-by-step execution flow when the user runs the Version Diff command.

```mermaid
flowchart TD
    A[User clicks Version Diff] --> B{Document saved?}
    B -- No --> B1[Show error message]
    B -- Yes --> C{Active Fusion 3D Design?}
    C -- No --> C1[Show error message]
    C -- Yes --> C2{Parametric design?}
    C2 -- No --> C3[Show error message]
    C2 -- Yes --> D{At least 2 versions?}
    D -- No --> D1[Show error message]
    D -- Yes --> E[Show dialog with current version info\nand comparison dropdown]
    E --> F[User selects comparison version\nand clicks OK]
    F --> G[Walk baseline timeline\nextract sketch fingerprints\nextract feature parameters\nextract design properties]
    G --> H[Open comparison version read-only]
    H --> I[Walk comparison timeline\nextract sketch fingerprints\nextract feature parameters\nextract design properties]
    I --> J[Close comparison document]
    J --> K[Compute diff:\nnewer / deleted / unchanged /\nversion_changed / sketch_modified /\nparams_changed / health_changed]
    K --> L[Save JSON to temp file]
    L --> M[Generate HTML report:\nvisual timeline + properties table + diff table]
    M --> N[Open HTML in Fusion browser]
```

### Data model

The following diagram shows the relationships between the data structures used in the diff pipeline.

```mermaid
classDiagram
    class TimelineFeature {
        +str name
        +str feature_type
        +int index
        +bool is_group
        +bool is_suppressed
        +bool is_rolled_back
        +str health_state
        +str entity_type
        +str component_name
        +str component_version
        +SketchFingerprint sketch_fingerprint
        +dict feature_params
    }

    class SketchFingerprint {
        +str revision_id
        +int line_count
        +int circle_count
        +int arc_count
        +int dimension_count
        +int constraint_count
        +int profile_count
        +bool is_fully_constrained
    }

    class DesignProperties {
        +str material
        +list body_appearances
        +float mass
        +float volume
        +float area
        +float density
        +tuple center_of_mass
        +tuple bbox_min
        +tuple bbox_max
        +int body_count
    }

    class VersionInfo {
        +int version_number
        +str version_id
        +str name
        +str date_modified
        +str last_updated_by
        +str description
        +str thumbnail_b64
    }

    class AlignedRow {
        +TimelineFeature older
        +TimelineFeature newer
        +str status
        +str detail
        +str sketch_detail
        +str params_detail
        +str health_detail
    }

    class DiffResult {
        +VersionInfo baseline
        +VersionInfo comparison
        +list~AlignedRow~ aligned_rows
        +dict summary
        +bool older_is_comparison
        +DesignProperties baseline_properties
        +DesignProperties comparison_properties
    }

    DiffResult --> VersionInfo : baseline
    DiffResult --> VersionInfo : comparison
    DiffResult --> AlignedRow : aligned_rows
    DiffResult --> DesignProperties : properties
    AlignedRow --> TimelineFeature : older
    AlignedRow --> TimelineFeature : newer
    TimelineFeature --> SketchFingerprint : sketch_fingerprint
```

## Authorship

`DataFile` cannot attribute a version. `createdBy` returns the file's creator and `lastUpdatedBy` its last editor, and **every version in the collection answers with those same two names** — verified on a 27-version design saved by nine people, where they returned one name each and different names from each other.

The Version Summary used to report `len({ver.lastUpdatedBy for ver in versions})` as "Contributors", which is one by construction; it read "1 user" for that design. The dropdown carried the same name on every row, and the HTML report shows it on both cards. Those are now labelled "Created By" / "Last Saved By" for what they are, the dropdown carries no name at all, and the per-version read is gone from the scan loop — which also removes a cloud round trip per version from the dialog build.

Per-version authorship is reachable only over MFGDM GraphQL, and not from here: this command builds its dialog in `command_created`, where reading `mfgdmModelId` destabilises Fusion (234b043). `commands/dochistory` does it from a deferred custom event; see [Document History](Document%20History.md).
