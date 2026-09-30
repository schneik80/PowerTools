# Assign Part Numbers

[Back to README](../README.md)

## Overview

Assign Part Numbers assigns controlled part numbers to the active design and its local components from hub-shared sequential schemes: `PRT`, `ASY`, `WLD`, `COT` and `TOL`.

A part number is only controlled if nobody else can mint the same one. SolidWorks PDM and Vault do this with a serial-number generator on the server; without a PDM system it is a spreadsheet somebody forgets to update. Assign Part Numbers keeps the counters in a file in your hub's **Assets** project, so every user draws from the same sequence, and stamps the numbers on the components in one atomic step. Drawings draw from the same counter file through [Assign Drawing Number](./Assign%20Drawing%20Number.md).

## Prerequisites

- The active document must be a saved design.
- The hub must contain a project named **Assets**, and you need write access to it. Creating a project needs administrator rights, so PowerTools does not do it.
- Components should have been saved to the cloud at least once, so their metadata exists to be written to.

## Where to find it

**Utilities** tab › **Power Tools** panel › **Assign Part Numbers**, in the Design workspace.

## Schemes

| Prefix | Item class | Offered for design intent |
|---|---|---|
| `PRT` | Custom part (single piece, any process) | Part, Hybrid |
| `ASY` | Assembly (has a BOM; one or more children) | Assembly, Hybrid |
| `WLD` | Weldment (as-welded item treated as a single deliverable) | Assembly, Hybrid |
| `COT` | Commercial off-the-shelf (fasteners, bearings, vendor components) | Part, Hybrid |
| `TOL` | Tooling, fixture or jig | All |
| `DWG` | Drawing | Reserved for Assign Drawing Number |

Numbers are zero-padded to six digits: `PRT-000001`, `ASY-000042`. The schemes offered are filtered by the *design's* intent, and the same filter applies to every local component row, so in an Assembly-intent design the local components can only take `ASY`, `WLD` or `TOL`.

## How to use

1. Open the saved design.
2. Select **Assign Part Numbers**. Opening the dialog reads the hub counters (and creates the `Assets / Pn-Cache` folder if it is missing).
3. The dialog shows the design intent and then one of two layouts:
   - **No local components**: the component name, its **Current P/N** if any, a **Scheme** dropdown and a read-only **Preview**.
   - **Local components present**: a **Components** table with one row for the root component, tagged `(root)`, and one for each unique top-level local component. Each row has its own **Scheme** dropdown and **Preview**.
4. Pick a scheme per row. Rows start at `(skip)`. The preview shows the actual next number for that scheme; rows sharing a prefix advance in sequence, so the second `PRT` row previews the number after the first.
5. If any target already has a part number, an inline warning lists the affected components and their current values. Choosing a scheme replaces the number; leaving `(skip)` keeps it. There is no further confirmation.
6. Select **Assign**. It is enabled once at least one row has a scheme. All chosen numbers are committed to the hub counter in one update, then stamped on the components. Saving the document is left to you.

## What it produces

- Each chosen component's part number set to its new value.
- `Assets / Pn-Cache / pn-cache.json` updated with the new `lastUsed` per scheme. Fusion versions this file, so the history of assignments is in Fusion Team.
- Fusion's own placeholder part numbers (`YYYY-MM-DD-HH-MM-SS-mmm`) are treated as empty and do not trigger the overwrite warning.
- Every stamp is read back and verified. A component whose stamp did not take is named in a warning after the dialog closes.

## Limitations

- Referenced (external) components are not numbered here; they belong to their own design.
- Only top-level local components are listed; nested local components are not.
- A local component added since the last save has no cloud metadata yet, so its stamp fails and is reported. Its number is consumed anyway. Save the document and run the command again for those components.
- Numbers are never recycled and never roll back.
- The preview reflects the counters when the dialog opened. If a teammate commits first, the commit is retried from a fresh baseline (up to three attempts) and the number assigned can differ from the preview. If all three attempts lose the race, nothing is stamped.
- If the **Assets** project is missing, previews fall back to `1` with a note and **Assign** reports the missing project.

> **Developers:** see the [architecture notes](./arch/Assign%20Part%20Numbers.md).

---

[Back to README](../README.md)

*Copyright © 2026 IMA LLC. All rights reserved.*
