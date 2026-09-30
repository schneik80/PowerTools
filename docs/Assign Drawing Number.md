# Assign Drawing Number

[Back to README](../README.md)

## Overview

Assign Drawing Number reserves the next `DWG-NNNNNN` number from the hub-wide counter and stamps it on the active drawing.

Controlled drawing numbers are normally a PDM job: SolidWorks PDM and Vault hand out serial numbers from a shared counter so two people never mint the same one. Fusion has no such counter. Assign Drawing Number keeps one in your hub, shared with [Assign Part Numbers](./Assign%20Part%20Numbers.md), so every number across designs and drawings is unique, and writes the number both onto the drawing and into the source design's **Drawing Number** custom property so a titleblock bound to that property fills itself in.

## Prerequisites

- The active document must be a saved 2D drawing.
- The hub must contain a project named **Assets**, and you need write access to it. Creating a project needs administrator rights, so PowerTools does not do it.
- For the titleblock sync, the hub's Custom Properties must include a property named **Drawing Number** (exact case) for designs. Without it the drawing is still numbered; only the sync is skipped.

## Where to find it

**Power Tools** panel on the Drawing workspace's toolbar tab › **Assign Drawing Number**.

## How to use

1. Open the drawing.
2. Select **Assign Drawing Number**. Opening the dialog reads the hub counter (and creates the `Assets / Pn-Cache` folder if it is missing).
3. The dialog shows:
   - **Scheme**: `DWG — Drawing (controlled document)`.
   - **Current number** and a warning note, only when the drawing already has a number, saying that **Assign** will replace it.
   - **Will assign**: the next `DWG-NNNNNN`.
4. Select **Assign**, or **Cancel** to change nothing.

On **Assign**, the counter is committed, the number is written to the drawing, and the same number is written into the source design's **Drawing Number** custom property, opening the source design invisibly if it is not already loaded. The dialog closes when these finish. Saving the drawing is left to you.

## What it produces

- The number (for example `DWG-000042`) stored on the drawing document itself.
- The source design's root component **Drawing Number** custom property set to the same value, directly in the cloud; the design does not need saving.
- `Assets / Pn-Cache / pn-cache.json` updated with the new `DWG` counter. Fusion versions this file, so the history of assignments is in Fusion Team.

## Limitations

- Numbers are never recycled and never roll back; the counter only increases.
- The counter is committed before the drawing is stamped, so a failed stamp still consumes a number; the message says so.
- Concurrent users are handled by re-reading the counter and retrying up to three attempts. If all three lose the race, the command reports an error and nothing is written.
- If the **Assets** project is missing, the preview reads `DWG-000001 (baseline unavailable)` and **Assign** reports the missing project.
- A drawing with no source design (one started from scratch) is numbered, but the titleblock sync is skipped.
- If the source design has never been saved to the cloud, or the **Drawing Number** property does not exist in the hub, the sync is skipped with a message and the drawing keeps its number.

> **Developers:** see the [architecture notes](./arch/Assign%20Drawing%20Number.md).

---

[Back to README](../README.md)

*Copyright © 2026 IMA LLC. All rights reserved.*
