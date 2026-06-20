# Export Mermaid Diagram — Architecture

[← Export Mermaid Diagram guide](../Export%20Mermaid.md)

## Architecture

### System context

The following C4 context diagram shows how the **Export Mermaid Diagram** command interacts with Autodesk Fusion and external rendering tools.

```mermaid
C4Context
    title Export Mermaid Diagram — System Context

    Person(user, "Designer", "Autodesk Fusion user with an active assembly open.")

    System(addin, "Power Tools – Export Mermaid", "Autodesk Fusion add-in command that traverses the component hierarchy and writes a Mermaid flowchart file.")

    System_Ext(fusion, "Autodesk Fusion", "CAD platform. Provides the design API, component occurrence tree, and the folder browser dialog.")

    System_Ext(fs, "Local File System", "Receives the exported Mermaid file named after the active document.")

    System_Ext(viewer, "Mermaid Viewer", "Renders the .mmd file into a visual diagram. Can be Mermaid Live, a VS Code extension, GitHub, or any compatible Markdown renderer.")

    Rel(user, fusion, "Invokes Export Mermaid Diagram via File menu")
    Rel(fusion, addin, "Fires CommandCreated and Execute events")
    Rel(addin, fusion, "Reads rootComponent.occurrences recursively")
    Rel(addin, fs, "Writes {DocumentName}.mmd")
    Rel(user, viewer, "Opens .mmd file for rendering")
    Rel(viewer, fs, "Reads .mmd file")
```

### Command processing flow

The following diagram shows the internal processing steps that run when the command executes.

```mermaid
flowchart TD
    A([User selects Export Mermaid Diagram]) --> B[CommandExecute event fires]
    B --> C{Active product\nis a Fusion Design?}
    C -- No --> D[Show error:\nA Design Must be Active]
    C -- Yes --> E[Get rootComponent and document name]
    E --> F[Write Mermaid front matter\ntheme init block]
    F --> G[Write graph LR declaration]
    G --> H[traverseAssembly:\nIterate rootComponent.occurrences]
    H --> I[Sanitize parent and child names\nReplace or remove special characters]
    I --> J[Write relationship string:\nParent--&#62;Child]
    J --> K{Child has\nchild occurrences?}
    K -- Yes --> L[Recurse into\nchild occurrences]
    L --> I
    K -- No --> M{More occurrences\nat this level?}
    M -- Yes --> I
    M -- No --> N[Show folder picker dialog]
    N --> O{User confirmed\ndestination folder?}
    O -- No --> P([Exit — no file written])
    O -- Yes --> Q[Write {DocumentName}.mmd]
    Q --> R[Show confirmation message\nwith full file path]
    R --> P
```
