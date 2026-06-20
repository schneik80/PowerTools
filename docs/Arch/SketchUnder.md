# Sketch Under-Constrained — Architecture

[← Sketch Under-Constrained guide](../SketchUnder.md)

## Architecture

### System context

The following diagram shows the relationship between the user, the Sketch Under-Constrained command, and Autodesk Fusion.

```mermaid
C4Context
    title System Context — Sketch Under-Constrained
    Person(user, "Fusion User", "Part designer working in Autodesk Fusion")
    System(addin, "Sketch Under-Constrained", "Power Tools Add-in command that identifies under-constrained sketch entities")
    System_Ext(fusion, "Autodesk Fusion", "CAD platform and host application")
    Rel(user, addin, "Invokes from Sketch > Modify panel")
    Rel(addin, fusion, "Queries constraint state via Fusion text commands API")
    Rel(fusion, user, "Highlights under-constrained entities on canvas and shows summary message")
```

### Component diagram

The following diagram shows how the internal components of the command interact during execution.

```mermaid
C4Component
    title Component Diagram — Sketch Under-Constrained
    Container_Boundary(addin, "Sketch Under-Constrained Command") {
        Component(button, "Command Button", "Fusion UI Control", "Toolbar button in Sketch > Modify panel")
        Component(handler, "command_execute()", "Python", "Validates active sketch and dispatches the constraint query")
        Component(query, "Sketch.ShowUnderconstrained", "Fusion Text Command", "Queries the sketch and highlights under-constrained entities on canvas")
        Component(msgbox, "Message Box", "Fusion UI", "Displays the constraint analysis result summary to the user")
    }
    System_Ext(fusion, "Autodesk Fusion Sketch Engine", "Processes the query, updates canvas highlighting, and returns result string")
    Rel(button, handler, "Triggers on click")
    Rel(handler, query, "Executes")
    Rel(query, fusion, "Processed by")
    Rel(fusion, handler, "Returns result string")
    Rel(handler, msgbox, "Displays result")
```
