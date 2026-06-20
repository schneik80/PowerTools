# Bottom-Up Update — Architecture
[← Bottom-Up Update guide](../Bottom-Up%20Update.md)

## Architecture

The following diagrams show how the Bottom-Up Update command fits into the Autodesk Fusion ecosystem and how its internal components interact.

```mermaid
C4Context
  title Bottom-Up Update – System Context

  Person(user, "Design Engineer", "Autodesk Fusion user performing bulk assembly maintenance")
  System(addin, "PowerTools Assembly", "Autodesk Fusion add-in")
  System_Ext(fusion, "Autodesk Fusion", "Host application and Python API (adsk.core / adsk.fusion)")
  System_Ext(hub, "Autodesk Hub", "Cloud document storage providing reference version data")
  System_Ext(fs, "Local File System", "OS temp folder log file output")

  Rel(user, addin, "Runs Bottom-Up Update")
  Rel(addin, fusion, "Traverses assembly DAG; opens, updates, rebuilds, and saves each component document in order; polls upload completion via DataFileFuture or findFileById")
  Rel(fusion, hub, "Downloads latest reference versions during updateAllReferences(); confirms version bump after each save")
  Rel(addin, fs, "Writes checkpoint log to OS temp folder; reads log on next launch for resume detection")
```

```mermaid
C4Component
  title Bottom-Up Update – Component View

  Person(user, "Design Engineer")
  Component(cmd, "bottomupupdate/entry.py", "PowerTools Command", "Registers toolbar button; presents three-tab dialog; orchestrates the full bottom-up update lifecycle including resume detection and upload confirmation")
  Component(resume, "_analyze_resume_state()", "Internal Function", "Reads temp log; checks Fusion client version, DAG equality, and last CHECKPOINT to determine full-run vs resume")
  Component(traversal, "traverse_assembly()", "Internal Function", "Recursively builds a nested dictionary representing the full assembly dependency tree")
  Component(dag_sort, "sort_dag_bottom_up()", "Internal Function", "Topologically sorts the dependency tree so leaves are processed before parents")
  Component(upload_wait, "wait_for_upload()", "Internal Function", "Polls DataFileFuture.uploadState / isComplete or hub version bump until upload confirmed or timeout")
  Component(api_design, "adsk.fusion.Design", "Fusion API", "Provides allComponents, rootComponent, and occurrences for traversal")
  Component(api_doc, "adsk.core.Document", "Fusion API", "Opened per component for updateAllReferences(), computeAll(), and save()")
  Component(intent, "Design Intent Logic", "Internal Logic", "Analyzes child occurrences, sketches, and bodies; executes appropriate Fusion text command")
  Component(logger, "Log Writer", "Internal Function", "Writes timestamped UTF-8 checkpoint log to OS temp folder")
  Component(logviewer, "open_live_log_viewer()", "Internal Function", "Opens Console.app (macOS) or PowerShell (Windows) to stream the log file live")
  System_Ext(hub, "Autodesk Hub", "Stores versioned component documents")

  Rel(user, cmd, "Clicks Bottom-up Update button")
  Rel(cmd, resume, "Inspects temp log at dialog open and before first component")
  Rel(cmd, traversal, "Builds dependency tree from rootComponent.occurrences")
  Rel(traversal, api_design, "Reads each component's child occurrences")
  Rel(cmd, dag_sort, "Determines bottom-up processing order")
  Rel(cmd, api_doc, "Opens each component in turn; calls updateAllReferences and computeAll; saves")
  Rel(cmd, upload_wait, "Blocks until each component upload is confirmed before advancing")
  Rel(upload_wait, hub, "Polls version number via app.data.findFileById() when save() returns bool")
  Rel(api_doc, hub, "Pulls latest reference versions; pushes saved versions")
  Rel(cmd, intent, "Applies classification when Apply Design Doc Intent is enabled")
  Rel(cmd, logger, "Writes event, checkpoint, and summary entries")
  Rel(cmd, logviewer, "Launches native log viewer after log file initialization")
```

### User flow

```mermaid
sequenceDiagram
  autonumber
  actor User
  participant Cmd as Bottom-Up Update
  participant Resume as _analyze_resume_state()
  participant Order as traverse / sort_dag_bottom_up
  participant API as Fusion API
  participant Wait as wait_for_upload()
  participant Hub as Autodesk Hub
  participant Log as Log file

  User->>Cmd: Open command
  Cmd->>Resume: Inspect existing temp log
  Resume-->>Cmd: Run-status verdict
  Cmd-->>User: Show three-tab dialog with run status
  User->>Cmd: Configure options and click OK
  Cmd->>Order: Build DAG and produce bottom-up list
  Order-->>Cmd: Ordered component list
  loop For each component (resume index onward)
    Cmd->>API: documents.open(component DataFile)
    Cmd->>API: updateAllReferences / computeAll / visibility / design intent
    Cmd->>API: document.save("Bottom-up update …")
    Cmd->>Wait: Block until upload confirmed
    Wait->>Hub: Poll uploadState / version bump
    Hub-->>Wait: Upload confirmed
    Cmd->>Log: CHECKPOINT|SAVE_UPLOAD_COMPLETE|component=…
    Cmd->>API: Close component (root assembly stays open)
  end
  Cmd->>API: Get All Latest + Update All From Parent on root
  Cmd->>API: Save root assembly
  Cmd->>Wait: Confirm root upload
  Cmd-->>User: Summary message and final log entry
```

### Topological sort

The command must process components in an order where every component's dependencies are saved before the component that uses them. It achieves this through a two-phase algorithm.

**Phase 1 — Build the dependency tree (`traverse_assembly`)**

Starting from the root component, the function walks `component.occurrences` recursively. Each component is stored as a node in a nested dictionary keyed by component name:

```
{
  "Bracket": {
    "component": <adsk.fusion.Component>,
    "children": {
      "Bushing": { "component": ..., "children": {} },
      "Pin":     { "component": ..., "children": {} }
    }
  },
  "Frame": { ... }
}
```

The result is a directed acyclic graph (DAG) where each node points to its child nodes. Components that appear in multiple sub-assemblies are represented once under the first parent that encounters them; duplicate traversal of the same component name is skipped.

**Phase 2 — Post-order traversal (`sort_dag_bottom_up`)**

The sort walks the DAG using a depth-first, post-order traversal. For any given node it recurses into all children before appending the node itself to the output list. This guarantees that a component only appears in the list *after* all of its dependencies have already been appended.

```
traverse_dag("Bracket")
  → traverse_dag("Bushing")  → append "Bushing"
  → traverse_dag("Pin")      → append "Pin"
  → append "Bracket"
```

The final list is the bottom-up processing order. The command iterates it in sequence, opening, updating, and saving each document before moving to the next. The root assembly is excluded from the list and is saved separately at the end after all components have been processed.

**Why post-order matters**

If a parent component is saved before its children are up to date, Autodesk Fusion resolves the parent's references against the old version of each child. The post-order traversal eliminates this problem: by the time any parent document is opened and saved, every document it depends on has already been updated and saved to the Hub.
