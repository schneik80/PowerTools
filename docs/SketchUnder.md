# Sketch Under-Constrained

[Back to README](../README.md)

## Overview

The **Sketch Under-Constrained** command highlights all sketch entities in the active sketch that lack sufficient constraints or dimensions. Use this command to quickly identify which lines, curves, or points still need constraints applied, especially in complex sketches with many entities.

A fully constrained sketch is generally required before using sketch profiles to create solid features such as Extrude or Revolve.

> **Note:** This command is read-only. It highlights under-constrained entities but does not automatically apply constraints.

## Prerequisites

- A design document must be open in Autodesk Fusion.
- A sketch must be in active edit mode.

## Access

The **Sketch Under-Constrained** command is available in Fusion's **Sketch** tab, in the **Modify** panel, at the bottom of the panel menu.

1. Open a design document in Autodesk Fusion.
2. Double-click a sketch in the browser or on the canvas to enter sketch edit mode.
3. On the **Sketch** tab, select the **Modify** panel.
4. Select **Sketch Under-Constrained** from the panel menu.

## How to use

1. Enter sketch edit mode by double-clicking the sketch you want to analyze.
2. Run **Sketch Under-Constrained** from the **Modify** panel.
3. The command queries the active sketch for entities that are not fully constrained.
4. Under-constrained entities are highlighted directly on the canvas.
5. A message box displays a summary of the analysis results.
6. Apply dimensions, geometric constraints, or fix points to the highlighted entities as needed.
7. Re-run the command after making changes to verify that all entities are now fully constrained.

## Expected results

- Under-constrained sketch entities are visually highlighted in the Fusion canvas.
- A message box displays a summary of the under-constrained entity status.

## Limitations

- The command does not apply constraints automatically. All constraint changes must be made manually.
- The command must be re-run after applying constraints to see updated results.
- Fixed geometry and driven dimensions are not flagged as under-constrained.

---

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

---

[Back to README](../README.md)

*Copyright © 2026 IMA LLC. All rights reserved.*
