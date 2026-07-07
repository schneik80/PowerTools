# Round Sketch Dimensions

[Back to README](../README.md)

## Overview

The **Round Sketch Dimensions** command snaps the length dimensions of the active Autodesk Fusion sketch to a clean, adjustable increment. It is useful after tracing, importing, or free-form modeling leaves dimensions with untidy values (for example `12.4837 mm` or `0.7431 in`).

By default the command rounds **every** eligible dimension in the active sketch. You can narrow this to only the dimensions you select, or round everything except the dimensions you select. A slider chooses the rounding increment, starting from a smart default sized to your sketch, and a live preview shows the result before you commit.

Formula-driven dimensions (for example `width/2` or `d5`) and reference (driven) dimensions are **left untouched** so parametric relationships are preserved.

## Prerequisites

- A 3D design document — part, assembly, or hybrid, saved or unsaved — must be open in Autodesk Fusion.
- A sketch must be in active edit mode.

## Access

The command is available on Fusion's **Sketch** tab, in the **Modify** panel.

1. Open a design document in Autodesk Fusion.
2. Double-click a sketch in the browser or on the canvas to enter sketch edit mode.
3. On the **Sketch** tab, open the **Modify** panel.
4. Select **Round Sketch Dimensions**.

## Dialog options

- **Document units** — read-only; shows the active document's default length unit.
- **Mode** — how the rounding is scoped:
  - *Round all dimensions* (default) — round every eligible dimension in the sketch.
  - *Only round selected dimensions* — round just the dimensions you pick.
  - *Ignore selected dimensions* — round everything except the dimensions you pick.
- **Dimensions** — appears in the two selection modes; pick the sketch dimensions the mode applies to.
- **Value format** — appears only for inch/foot documents:
  - *Fractions* (default) — round to a fractional-inch grid (1/64 in … 1 in).
  - *Decimal* — round to a decimal-inch grid.
- **Increment** — a slider that sets how coarsely values are rounded. The default is chosen to suit the size of the dimensions in your sketch. The current increment is shown next to **Rounds to** (for example `0.5 mm` or `1/16 in`).
- **Preview** (default on) — updates the sketch live as you adjust the increment. The preview reverts if you cancel and commits if you click **Round**.

## How to use

1. Enter sketch edit mode and run **Round Sketch Dimensions**.
2. Leave the mode on *Round all dimensions*, or choose a selection mode and pick the dimensions.
3. Adjust the **Increment** slider until **Rounds to** shows the grid you want. For inch/foot documents, choose **Fractions** or **Decimal** first.
4. With **Preview** on, watch the sketch update as you drag the slider.
5. Click **Round** to commit, or **Cancel** to revert.

## Expected results

- Every targeted, eligible length dimension is snapped to the nearest multiple of the chosen increment.
- In **Fractions** mode the value lands on a fractional-inch grid; how it is displayed (fraction vs decimal) follows the document's own unit-precision settings.
- Formula-driven and reference (driven) dimensions are unchanged.
- The action is a single undoable step.

## Limitations

- Angular dimensions are not rounded in this release; only length dimensions (distance, radius, diameter) are affected.
- Dimensions whose value is defined by a formula or a reference to another parameter are intentionally skipped to preserve parametric intent.
- The command operates on the active sketch only.

> **Developers:** see the [architecture notes](./arch/Round%20Sketch%20Dimensions.md).

---

[Back to README](../README.md)

*Copyright © 2026 IMA LLC. All rights reserved.*
