# Assembly Statistics — Architecture
[← Assembly Statistics guide](../Assembly%20Statistics.md)

## Architecture

The following diagram shows how the Assembly Statistics command interacts with Autodesk Fusion and its data model.

```mermaid
C4Context
  title Assembly Statistics – System Context

  Person(user, "Design Engineer", "Autodesk Fusion user reviewing assembly structure")
  System(addin, "PowerTools Assembly", "Autodesk Fusion add-in")
  System_Ext(fusion, "Autodesk Fusion", "Host application and Python API (adsk.core / adsk.fusion)")
  System_Ext(hub, "Autodesk Hub", "Cloud document storage and version management")

  Rel(user, addin, "Runs Assembly Statistics")
  Rel(addin, fusion, "Queries component hierarchy, joints, references, and timeline via adsk API and text commands")
  Rel(fusion, hub, "Resolves document references and version state")
```

```mermaid
C4Component
  title Assembly Statistics – Component View

  Person(user, "Design Engineer")
  Component(cmd, "assemblystats/entry.py", "PowerTools Command", "Registers button in the Power Tools panel and handles command lifecycle")
  Component(api_design, "adsk.fusion.Design", "Fusion API", "Provides allComponents, rootComponent, assemblyConstraints, joints")
  Component(api_doc, "adsk.core.Application / Document", "Fusion API", "Provides documentReferences and text command execution")
  Component(text_cmd, "Component.AnalyseHierarchy", "Fusion Text Command", "Returns assembly depth and instance hierarchy text output")

  Rel(user, cmd, "Clicks Assembly Statistics button")
  Rel(cmd, api_design, "Reads component counts, joints, and constraints")
  Rel(cmd, api_doc, "Reads out-of-date references and timeline contexts")
  Rel(cmd, text_cmd, "Executes to get hierarchy depth and instance data")
  Rel(cmd, user, "Displays results in modal message dialog")
```

### User flow

```mermaid
sequenceDiagram
  autonumber
  actor User
  participant Panel as Power Tools panel
  participant Cmd as Assembly Statistics
  participant API as Fusion API
  participant Text as Fusion Text Commands

  User->>Panel: Click Assembly Statistics
  Panel->>Cmd: command_created fires
  Cmd->>API: design.allComponents, rootComponent.occurrences
  Cmd->>API: rootComponent.joints / assemblyConstraints
  Cmd->>API: documentReferences (out-of-date count)
  Cmd->>Text: Execute Component.AnalyseHierarchy
  Text-->>Cmd: Depth and instance hierarchy text
  Cmd->>Cmd: Aggregate counts and group joints by type
  Cmd-->>User: Show summary message dialog
  User->>Cmd: Click Close
```
