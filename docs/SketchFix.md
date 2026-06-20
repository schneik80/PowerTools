# Sketch Repair

[Back to README](../README.md)

## Overview

The **Sketch Repair** command attempts to automatically fix common issues in the active Autodesk Fusion sketch, including tiny gaps between endpoints and disconnected curve segments. Use this command when a sketch fails to form the closed profiles that solid body operations such as Extrude or Revolve require.

> **Note:** Results vary depending on the number and type of issues present in the sketch. The command cannot repair large gaps or fundamentally disconnected geometry.

## Prerequisites

- A design document must be open in Autodesk Fusion.
- A sketch must be in active edit mode.

## Access

The **Sketch Repair** command is available in Fusion's **Sketch** tab, in the **Modify** panel, at the bottom of the panel menu.

1. Open a design document in Autodesk Fusion.
2. Double-click a sketch in the browser or on the canvas to enter sketch edit mode.
3. On the **Sketch** tab, select the **Modify** panel.
4. Select **Sketch Repair** from the panel menu.

## How to use

1. Enter sketch edit mode by double-clicking the sketch you want to repair.
2. Run **Sketch Repair** from the **Modify** panel.
3. The command applies two sequential repair passes to the active sketch:
   - **Pass 1:** Removes tiny segments at or below the geometry tolerance threshold.
   - **Pass 2:** Merges disconnected endpoints and closes small gaps.
4. A confirmation message box appears when the repair is complete.
5. Inspect the sketch to verify the repair results. If open profiles remain, manual correction may be needed.

## Expected results

- Tiny segments at or below the geometry tolerance threshold are removed.
- Endpoints within tolerance are snapped together, closing small gaps.
- A message box confirms that the repair completed successfully.

## Limitations

- The command cannot repair large gaps or fundamentally disconnected geometry.
- Complex sketches with many issues may require multiple repair passes or manual correction.
- Repair quality depends on sketch geometry tolerance settings configured in Autodesk Fusion.

---

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

---

[Back to README](../README.md)

*Copyright © 2026 IMA LLC. All rights reserved.*
