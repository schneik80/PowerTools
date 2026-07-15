# Sync Item to Part Number

[Back to README](../README.md)

## Overview

The **Sync Item to Part Number** command copies the active design's Fusion Manage **Item Number** into its **Part Number** (`component.partNumber`) in a single click. It is intended for teams using the **Fusion Manage Extension**, where a design carries both a Manage-assigned Item Number (Properties → *Manage*) and a Part Number, and the Part Number should mirror the Item Number.

Before copying, the command checks whether the current Part Number is part of a **shared part number group** (two or more models sharing one part number). If it is, you are prompted to continue or cancel, so a shared part number is never changed without confirmation. When the copy completes, a summary of the change is shown.

The Item Number and the shared-part-number status are cloud values read through the Manufacturing Data Model GraphQL API (`mfgdm://v3`). The Part Number write persists to the backend immediately — no document save is required.

> **Note:** This command appears only when the **Fusion Manage Extension** is enabled for the hub (it lives on Fusion's built-in **Manage** tab). Its sibling numbering commands are [Assign Part Numbers](./Assign%20Part%20Numbers.md) and [Assign Drawing Number](./Assign%20Drawing%20Number.md).

## Capabilities

| Capability | Details |
|---|---|
| One-click sync | Copies `component.itemNumber` → `component.partNumber` for the active design's root component |
| Enabled with a design | The button is enabled whenever a Fusion design is the active product. All item/part validation happens on invoke — if there is no Item Number, or it already matches the Part Number, the command reports that and changes nothing |
| Shared part number guard | Before changing a Part Number that is shared across multiple models, prompts **OK / Cancel**; Cancel aborts with no change |
| Single-model precheck | Rejects designs that contain **local** child components (external/referenced children are allowed) |
| Immediate persistence | The Part Number write persists to the cloud immediately; no save step |
| Change summary | On completion, shows the component name, old Part Number, and new Part Number |

## Prerequisites

- The **Fusion Manage Extension** must be enabled for the active hub (otherwise the command's panel does not appear).
- The active document must be a Fusion 3D design that is cloud-registered (an assigned Item Number implies this).
- The design must have no **local** child components; external/referenced children are fine.

## Access

The **Sync Item to Part Number** command is located on the **Manage** tab, in the **Power Tools** panel of the Autodesk Fusion Design workspace.

1. Open a cloud-saved Fusion design that has a Manage Item Number.
2. On the **Manage** tab, in the **Power Tools** panel, select **Sync Item to Part Number**.

## How to use

1. Open the design whose Part Number you want to align to its Item Number.
2. Run **Sync Item to Part Number** from the **Power Tools** panel on the **Manage** tab. The command validates the design on invoke: if there is no Item Number, or it already matches the Part Number, it tells you and makes no change.
3. If the current Part Number is part of a shared part number group, a dialog explains this and asks whether to **Continue** (OK) or **Cancel**. Choose Cancel to make no change.
4. On completion, a summary dialog shows the component name, the old Part Number, and the new Part Number (copied from the Item Number).

## Output

- `component.partNumber` is set to the design's Item Number (e.g., `PN-000038`). The change is written to the cloud immediately.
- Re-running the command once the Item Number and Part Number match reports "already match" and makes no change.

## Limitations

- Requires the Fusion Manage Extension; without it the Manage tab (and this command) are not present.
- Designs containing local child components are rejected — the command operates on a single model only.
- The Item Number is read from the cloud (Manufacturing Data Model); if cloud metadata is not yet ready, the command asks you to try again in a moment.
- If the shared-part-number check cannot reach the service, the command errs on the side of caution and prompts to confirm before overwriting.

> **Developers:** see the [architecture notes](./arch/Sync%20Item%20to%20Part%20Number.md).

---

[Back to README](../README.md)

---

*Copyright © 2026 IMA LLC. All rights reserved.*
