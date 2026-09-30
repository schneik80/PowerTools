# Infer Constraints

[Back to README](../README.md)

## Overview

Infer Constraints proposes assembly constraints for an assembly whose components are already in position, from concentric cylindrical faces and flush planar faces, and applies the ones you select while keeping the components where they are.

A STEP import arrives with every part exactly where it belongs and not a single relationship between them. SolidWorks SmartMates infer a mate from geometry, but one pair at a time, by dragging. Infer Constraints scans the whole assembly at once, grounds the first component, lists every shaft-in-hole and face-on-face pair it finds with a confidence score, and lets you apply the lot in one step, dropping the ones that would over-constrain the assembly.

> **Beta.** Tick **Show beta commands** under **General** in **File › PowerTools Preferences**, then enable **Infer Constraints** under **Assembly**, and restart Fusion.

## Prerequisites

- A design document must be open.
- The assembly should already be positioned; the command infers relationships from geometry that is mating now and does not move components into place.
- Components (or solid bodies in the root) must expose planar or cylindrical faces, as imported solids do.
- Applying constraints uses Fusion's Assembly Constraints capability, which Autodesk ships as a preview. On a build without it, detection and the table still work but applying a constraint reports an error. Grounding does not depend on it.

## Where to find it

**Utilities** tab › **Power Tools** panel › **Infer Constraints**, in the Design workspace.

## How to use

1. Open the assembly.
2. Select **Infer Constraints**. On an assembly with 4000 or more analytic faces the command asks before scanning. The **Inferred relationships** table fills with one row per relationship: type, the two components, and a confidence score. When the root has top-level components, the first row is a **Ground to Parent** on the first of them.
3. Select a row's **Components** button, tick its box, or change its dropdown, to highlight that pair in the viewport; the **Highlighted pair** box names it.
4. Adjust **Linear tolerance** or **Angular tolerance** if needed; the scan re-runs on each change. **Re-scan** repeats it on demand. Looser tolerances find more and weaker candidates.
5. For each centred pair, choose a joint type from its dropdown.
6. Tick the relationships to apply. Rows with a confidence of 0.60 or higher are pre-ticked.
7. Select **OK**. Grounding is applied first, then the remaining relationships strongest first. The **Summary** reports how many were created, how many redundant ones were skipped, how many failed, and whether anything moved.

## Options

| Option | Default | Effect |
|---|---|---|
| **Linear tolerance** | 0.1 mm | How far apart two faces may be and still count as touching or coaxial |
| **Angular tolerance** | 0.5° | How far from parallel two directions may be |
| **Re-scan** | — | Repeats the scan with the current tolerances |
| Per-row checkbox | Ticked at confidence ≥ 0.60 | Whether the row is applied |
| Per-row joint type (centred pairs) | Rigid | Rigid, Revolute, Slider, Cylindrical, Pin-Slot, Planar or Ball |

## What it detects

| Relationship | Geometry | Applied as |
|---|---|---|
| **Ground to Parent** | The first top-level component | Grounded |
| **Concentric** | Coaxial cylindrical faces, including shaft-in-hole pairs with clearance | Assembly constraint |
| **Coincident** | Planar faces lying flush against one another | Assembly constraint |
| **Centred** | Coincident faces whose centroids also coincide | A joint at the shared face centre, of the type you choose |

Only visible leaf components and solid bodies in the root are scanned.

## Limitations

- Inferring relationships is inherently ambiguous; treat the list as ranked suggestions and review the low-confidence rows.
- Where two orientations of a constraint both fit, the one that moves the part least is chosen; if a part still moves, the summary reports it with the largest displacement so you can undo.
- In a direct-modelling (non-parametric) design the "first component" is taken from the model's own order, which may not match the browser.
- Redundant relationships that would over-constrain the assembly are skipped and counted.

> **Developers:** see the [architecture notes](./arch/Infer%20Constraints.md).

---

[Back to README](../README.md)

*Copyright © 2026 IMA LLC. All rights reserved.*
