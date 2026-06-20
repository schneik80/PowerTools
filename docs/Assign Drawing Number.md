# Assign Drawing Number

[Back to README](../README.md)

## Overview

The **Assign Drawing Number** command reserves the next sequential `DWG-NNNNNN` number from the hub-wide Pn-Cache and stamps it on the active Autodesk Fusion 2D drawing document. The number is persisted two ways, both automatic:

1. **Drawing document attribute** — the canonical local record. Because `adsk.drawing` does not expose a first-class `partNumber` property for drawings, the number is stored as an `adsk.core.Attribute` on the `DrawingDocument` (group `PowerTools.PartNumber`, name `assigned`).

2. **Source design's `Drawing Number` custom property** — the titleblock hook. The command navigates the drawing's single `DocumentReference` to the source 3D design (opening it silently in the background if it isn't already in memory), then writes the assigned number through the MFGDM GraphQL `setProperties` mutation into the source root component's `Drawing Number` custom property. A titleblock with a binding to that custom property auto-populates the next time the drawing regenerates — no manual titleblock edits needed.

This command shares the same hub cache (`Assets / Pn-Cache / pn-cache.json`) used by [Assign Part Numbers](./Assign%20Part%20Numbers.md), so drawing numbers and 3D part numbers never collide and every assigned number is unique across the hub.

> **Note:** This command is available only in the Autodesk Fusion Drawing workspace. The 3D design equivalent is [Assign Part Numbers](./Assign%20Part%20Numbers.md).

## Capabilities

| Capability | Details |
|---|---|
| Hub-unique drawing numbers | Single `DWG` scheme shared across the active hub; counter lives alongside the 3D part number counters |
| Durable drawing-side stamp | Assigned number stored as an `adsk.core.Attribute` on the DrawingDocument, group `PowerTools.PartNumber`, name `assigned` |
| Automatic titleblock sync | After the drawing stamp, the command writes the same number into the source design's root component `Drawing Number` custom property via the MFGDM GraphQL `setProperties` mutation. Titleblocks bound to that property auto-populate on next regenerate |
| Silent source-design open | When the source design is not already loaded in Fusion, the command opens it invisibly (`visible=False`), performs the property write, and closes it again — no extra document tab appears |
| Single-reference rule | Fusion drawings reference at most one 3D design; the command uses `documentReferences[0]` and is a no-op if the drawing has no source reference |
| Setup-guide error | If the source design lacks the `Drawing Number` custom property, the command surfaces a rich error message with a clickable link to the setup guide (URL configurable via `DRAWING_NUMBER_SETUP_URL`) |
| Optimistic retry | Cache commit uses download → modify → upload → verify with up to 3 retries to handle concurrent writers |
| Live preview | Dialog shows the actual next `DWG-NNNNNN` by reading the hub cache when the dialog opens |
| Inline overwrite notice | When the drawing already has a number, the dialog shows the current value and an inline warning note. No extra modal confirmation — clicking Assign replaces the existing number |

## Prerequisites

- The active document must be a saved Autodesk Fusion 2D drawing.
- The active hub must contain a project named **Assets** (project creation is deliberately not automated — it usually requires admin permissions).
- The user must have write permission on the **Assets** project.
- The hub's Custom Properties collection should include a property named **Drawing Number** (exact case) linked to the source design's applicable entity type. Without it, the drawing-side stamp still succeeds but the titleblock sync is skipped with a linked setup guide.

## Notes

- The **Pn-Cache** folder under **Assets** is auto-created on first use.
- `pn-cache.json` is auto-created on first commit.
- Document save after assignment is intentionally left to the user so the command dialog closes promptly on **Assign**. The titleblock sync writes to the cloud MFGDM record directly and does not require a local save of the source design.
- Drawing numbers never roll over or recycle — numbering is monotonic across the hub.
- The source design is opened invisibly during sync if it isn't already loaded. The user sees no extra document tab and the source design is closed automatically after the write completes.

## Access

The **Assign Drawing Number** command is located on the **Document** tab, in the **Power Tools** panel of the Autodesk Fusion Drawing workspace.

1. Open a saved Fusion drawing.
2. On the **Document** tab, in the **Power Tools** panel, select **Assign Drawing Number**.

## How to use

1. Open the drawing you want to number.
2. Run **Assign Drawing Number** from the **Power Tools** panel.
3. The dialog shows:
   - **Scheme** — the fixed `DWG — Drawing (controlled document)` label.
   - **Current number** — the drawing's existing assigned number. This row appears only when a prior number exists on the drawing.
   - **Warning note** — an inline yellow warning, shown only when a prior number exists, explaining that clicking **Assign** will replace it with the preview below.
   - **Will assign** — the real next `DWG-NNNNNN` read from the hub cache.
4. Click **Assign**. Three things happen atomically from the user's perspective:
   - The cache counter is bumped via the optimistic-retry commit.
   - The new number is written as a Fusion Attribute on the drawing document.
   - The same number is synced into the source design's root component `Drawing Number` custom property (opening the source design silently if needed). The dialog closes as soon as these steps finish.
5. If the source design is missing the `Drawing Number` custom property, a post-close warning dialog appears with a clickable link to the setup guide. The drawing-side stamp is still correct — only the titleblock auto-sync was skipped.
6. To back out without changing anything, click **Cancel**.

## Output

- A Fusion Attribute named `assigned` is written to the DrawingDocument under group `PowerTools.PartNumber`. The value is the formatted number, e.g., `DWG-000042`.
- The source design's root component `Drawing Number` custom property is set to the same value via the MFGDM GraphQL `setProperties` mutation. This is the field the titleblock binds to.
- `Assets / Pn-Cache / pn-cache.json` is updated with the new `DWG.lastUsed` counter.

## Limitations

- The **Assets** project must exist; if absent, the command aborts with a clear error message.
- Titleblock auto-population depends on the hub's Custom Properties collection defining a `Drawing Number` property and the titleblock being bound to that property. If the property is missing from the hub, the command surfaces a setup-guide error after the drawing-side stamp completes — the drawing is still correctly numbered locally.
- `DataFile.description` is read-only in the current Fusion Python API, so the number is not mirrored to the Fusion Team web UI's description field.
- Numbers are not recycled when drawings are deleted.
- After more than 3 consecutive lost-race retries against the hub cache, the command aborts cleanly with an error and no attribute is written.
- Drawings with no `documentReferences` entry (e.g., drawings authored From Scratch) skip the titleblock sync with a log entry; the drawing-side stamp still succeeds.

> **Developers:** see the [architecture notes](./arch/Assign%20Drawing%20Number.md).

---

[Back to README](../README.md)

---

*Copyright © 2026 IMA LLC. All rights reserved.*
