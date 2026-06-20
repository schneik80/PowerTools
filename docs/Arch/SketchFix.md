# Sketch Repair — Architecture

[← Sketch Repair guide](../SketchFix.md)

## Architecture

### System context

The following diagram shows the relationship between the user, the Sketch Repair command, and Autodesk Fusion.

```mermaid
C4Context
    title System Context — Sketch Repair
    Person(user, "Fusion User", "Part designer working in Autodesk Fusion")
    System(addin, "Sketch Repair", "Power Tools Add-in command that repairs active sketch geometry")
    System_Ext(fusion, "Autodesk Fusion", "CAD platform and host application")
    Rel(user, addin, "Invokes from Sketch > Modify panel")
    Rel(addin, fusion, "Executes repair via Fusion text commands API")
    Rel(fusion, user, "Displays confirmation message box")
```

### Component diagram

The following diagram shows how the internal components of the command interact during execution.

```mermaid
C4Component
    title Component Diagram — Sketch Repair
    Container_Boundary(addin, "Sketch Repair Command") {
        Component(button, "Command Button", "Fusion UI Control", "Toolbar button in Sketch > Modify panel")
        Component(handler, "command_execute()", "Python", "Validates active sketch and dispatches repair text commands")
        Component(repair1, "sketch.repairsketch /3", "Fusion Text Command", "Pass 1: removes tiny segments below tolerance")
        Component(repair2, "sketch.repair", "Fusion Text Command", "Pass 2: closes gaps and merges disconnected endpoints")
        Component(msgbox, "Message Box", "Fusion UI", "Confirms repair completion to the user")
    }
    System_Ext(fusion, "Autodesk Fusion Sketch Engine", "Processes repair text commands and updates sketch geometry")
    Rel(button, handler, "Triggers on click")
    Rel(handler, repair1, "Executes first")
    Rel(handler, repair2, "Executes second")
    Rel(repair1, fusion, "Processed by")
    Rel(repair2, fusion, "Processed by")
    Rel(handler, msgbox, "Displays on success")
```
