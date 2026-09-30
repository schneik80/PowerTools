# Sync Item to Part Number

[Back to README](../README.md)

## Overview

Sync Item to Part Number copies the active design's Fusion Manage Item Number into its Part Number.

Teams on the Fusion Manage Extension carry two identifiers on every design: the Item Number that Manage assigns (**Properties › Manage**) and the Part Number that drawings, BOMs and exports read. When the two should be the same, keeping them so by hand is a copy-and-paste per document. This command does it in one click, checks first whether the Part Number is shared with other models, and writes the result straight to the cloud so no save is needed.

Its sibling numbering commands are [Assign Part Numbers](./Assign%20Part%20Numbers.md) and [Assign Drawing Number](./Assign%20Drawing%20Number.md).

## Prerequisites

- The **Fusion Manage Extension** must be enabled for the active hub. Without it Fusion has no **Manage** tab and the command's panel is not shown.
- The active document must be a Fusion design saved to the cloud with an Item Number assigned.
- The design must have no **local** child components. External (referenced) children are fine.

## Where to find it

**Manage** tab › **Power Tools** panel › **Sync Item to Part Number**, in the Design workspace. The panel is added when PowerTools starts; if the Manage Extension was enabled after that, restart Fusion.

## How to use

1. Open the design whose Part Number should match its Item Number.
2. Select **Sync Item to Part Number**. The command reads the Item Number and the current Part Number from the cloud.
   - If there is no Item Number, or it already matches, a message says so and nothing changes.
3. If the current Part Number is shared by two or more models, a dialog explains this and asks whether to continue. **Cancel** makes no change.
4. A summary shows the component name, the old Part Number and the new one.

## What it produces

- The root component's Part Number becomes the Item Number (for example `PN-000038`). The write is persisted to the cloud immediately; there is no save step.
- A Fusion-generated placeholder Part Number (`YYYY-MM-DD-HH-MM-SS-mmm`) is treated as empty, so it is replaced without the shared-number prompt and shown as `(none)` in the summary.

## Limitations

- Requires the Fusion Manage Extension.
- Designs containing local child components are rejected; the command works on a single model.
- If cloud metadata is not ready yet (a design saved moments ago), the command asks you to try again shortly.
- If the shared-number check cannot reach the service, the command asks for confirmation before overwriting rather than assuming the number is unique.

> **Developers:** see the [architecture notes](./arch/Sync%20Item%20to%20Part%20Number.md).

---

[Back to README](../README.md)

*Copyright © 2026 IMA LLC. All rights reserved.*
