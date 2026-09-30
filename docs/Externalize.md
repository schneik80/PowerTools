# Externalize

[Back to README](../README.md)

## Overview

Externalize saves a local component as its own cloud document and re-inserts it into the assembly at its original position.

SolidWorks users know this as **Save Part (in External File)** on a virtual component. Fusion has no equivalent: a component created in place, or imported with a STEP, stays inside the parent document with no versions, no drawings and no reuse of its own. Externalize turns it into a referenced document without disturbing the assembly, one component or all of them, and is the quickest way to convert an imported assembly into a distributed design.

## Prerequisites

- A design document saved to a hub. The new documents go in that document's folder or a sub-folder of it.

## Where to find it

**Utilities** tab › **Power Tools** panel › **Externalize**, in the Design workspace.

## How to use

### One component

1. Select **Externalize**.
2. On the **Main** tab, pick the component in the browser or on the canvas. A component that is already external is refused with a message.
3. Choose a **Save Location**.
4. Select **OK**. The dialog closes at once and the run continues in the background; watch the live log viewer or the status bar.

### All local components

1. Select **Externalize** and tick **Externalize All**. The selector hides and **Replace all instances** is forced on.
2. Choose a **Save Location** and select **OK**.

Each first-level local component is uploaded in turn, its occurrences removed, and the new document inserted at the same position and orientation. When every component has been processed the parent assembly is saved once, with the comment `Externalize: N components replaced`, and a dialog reports how many components were externalized this run.

## Options

| Option | Default | Effect |
|---|---|---|
| **Component** | — | The local occurrence to externalize (hidden when Externalize All is on) |
| **Externalize All** | Off | Process every first-level local component |
| **Replace all instances** | On | Replace every occurrence of the selected component, not just the one picked; forced on with Externalize All |
| **Save Location** | Same as Document | **Same as Document** saves next to the assembly (or in an existing sub-folder named after it); **Create Sub-folder** creates that sub-folder |
| **Run status** | — | Read-only: whether the run will start fresh or resume |
| **Log Progress** (Logging tab) | On | Writes a text log to your system's temporary folder |
| **Log file path** | `<document name>_externalize.log` | **Browse…** to choose another |
| **Open live log viewer** | On | Opens Console.app (macOS) or a PowerShell tail window (Windows) when the run starts |

## How a run behaves

- A cloud file of the same name already in the target folder is reused rather than duplicated.
- An upload Fusion never finishes is abandoned after 5 minutes and logged as `TIMED OUT`; the run moves on and that component is retried on the next run. Two failed uploads in a row stop the run early; the parent is still saved with everything that succeeded.
- Between components a recovery save is triggered, so in-memory replacements survive a crash.
- Starting a second run while one is in progress is refused.

### Resuming

If a run did not finish, **Run status** tells you what is available when the dialog opens: *Resume available — N of M already done*, *Previous run completed successfully…* (the log is reset), or *A full run will start*. A resumed run skips the components whose `CHECKPOINT|REPLACE_COMPLETE` line is in the log and processes the rest. A run made with a different Fusion version is not resumed.

## Limitations

- Only first-level local components are eligible; they are re-inserted into the root component.
- A component that cannot be uploaded is skipped and logged; the others are still replaced and committed.
- The parent is saved only when at least one component was replaced.

> **Developers:** see the [architecture notes](./arch/Externalize.md).

---

[Back to README](../README.md)

*Copyright © 2026 IMA LLC. All rights reserved.*
