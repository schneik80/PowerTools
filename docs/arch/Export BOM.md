# Export BOM as CSV — Architecture

[← Export BOM as CSV guide](../Export%20BOM.md)

## Architecture

### System context

The following C4 context diagram shows how the **Export BOM as CSV** command interacts with Autodesk Fusion and the local file system.

```mermaid
C4Context
    title Export BOM as CSV — System Context

    Person(user, "Designer", "Autodesk Fusion user with an active assembly open.")

    System(addin, "Power Tools – Export BOM", "Autodesk Fusion add-in command that collects component data from the active design and writes a flat BOM to a CSV file.")

    System_Ext(fusion, "Autodesk Fusion", "CAD platform. Provides the design API, component tree, body and material data, and the folder browser dialog.")

    System_Ext(fs, "Local File System", "Receives the exported CSV file named after the active document.")

    Rel(user, fusion, "Invokes Export BOM as CSV via File menu")
    Rel(fusion, addin, "Fires CommandCreated and Execute events")
    Rel(addin, fusion, "Reads allOccurrences, bRepBodies, and material properties")
    Rel(addin, fs, "Writes {DocumentName}.csv")
    Rel(user, fs, "Opens CSV in a spreadsheet or procurement tool")
```

### Command processing flow

The following diagram shows the internal processing steps that run when the command executes.

```mermaid
flowchart TD
    A([User selects Export BOM as CSV]) --> B[CommandExecute event fires]
    B --> C{Active product\nis a Fusion Design?}
    C -- No --> D[Show error:\nA Design Must be Active]
    C -- Yes --> E[Get rootComponent.allOccurrences]
    E --> F[Iterate all occurrences\nBuild unique component list]
    F --> G{Component already\nin BOM list?}
    G -- Yes --> H[Increment instance count]
    G -- No --> I[Resolve display name\nStrip version suffix if xref]
    I --> J[Read material from\nfirst solid bRepBody]
    J --> K[Append new row to BOM list]
    H --> L{More occurrences?}
    K --> L
    L -- Yes --> F
    L -- No --> M[Generate CSV string\nHeader + leaf component rows]
    M --> N[Show folder picker dialog]
    N --> O{User confirmed\ndestination folder?}
    O -- No --> P([Exit — no file written])
    O -- Yes --> Q[Write {DocumentName}.csv]
    Q --> R[Show confirmation message\nwith full file path]
    R --> P
```
