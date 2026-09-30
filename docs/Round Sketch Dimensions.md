# Round Sketch Dimensions

[Back to README](../README.md)

## Overview

Round Sketch Dimensions rounds the length and angular dimensions of the active sketch to clean, adjustable increments, leaving formula-driven and reference dimensions untouched.

Tracing, importing, auto-constraining or free-form modeling leaves dimensions like `12.4837 mm` or `0.7431 in`. Rounding them by hand means editing every one. This command does the whole sketch, or just the dimensions you pick, with a slider for the grid and a live preview so you see the result before committing.

## Prerequisites

- A design document must be open.
- A sketch must be in edit mode.

## Where to find it

**Sketch** tab › **Modify** panel › **Round Sketch Dimensions**, while editing a sketch.

## How to use

1. Double-click the sketch to edit it and select **Round Sketch Dimensions**.
2. Leave **Mode** on *Round all dimensions*, or choose a selection mode and pick dimensions in the **Dimensions** box.
3. Move the **Length increment** slider until **Length rounds to** shows the grid you want. For inch and foot documents choose **Fractions** or **Decimal** first. Do the same with **Angle increment** if the sketch has angles.
4. With **Preview** on, the sketch updates as you move the sliders.
5. Select **Round** to commit, or **Cancel** to revert.

## Options

| Option | Default | Effect |
|---|---|---|
| **Document units** | — | Read-only; the document's default length unit |
| **Mode** | Round all dimensions | *Only round selected dimensions* rounds what you pick; *Ignore selected dimensions* rounds everything else |
| **Dimensions** | — | Shown in the two selection modes; pick sketch dimensions |
| **Value format** | Fractions | Inch and foot documents only: *Fractions* rounds on a fractional-inch grid, *Decimal* on a decimal-inch grid |
| **Length increment** / **Length rounds to** | Sized to the sketch | Slider over the grid below; shown only when the sketch has eligible length dimensions |
| **Angle increment** / **Angle rounds to** | Sized to the sketch | Slider over the angle grid below; shown only when the sketch has eligible angles |
| **Preview** | On | Applies the rounding live; reverted on Cancel |

The grids:

| Units | Steps |
|---|---|
| Millimetre (also cm and m documents) | 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 25, 50 mm |
| Inch or foot, Fractions | 1/64 in to 1 in |
| Inch or foot, Decimal | 0.005, 0.01, 0.05, 0.1, 0.25, 0.5, 1 in |
| Angles | 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 15, 30, 45 deg |

The default step is the largest that is no more than 5% of the median dimension in the sketch.

## Results

- Every targeted length dimension (distance, radius, diameter) and angle is snapped to the nearest multiple of its increment.
- In **Fractions** mode the value lands on the fractional grid; whether it displays as a fraction or a decimal follows the document's unit settings.
- Dimensions defined by a formula or by another parameter are unchanged. A plain numeric fraction such as `3/8` counts as a value and is rounded.
- The **Round** button is disabled when there is nothing eligible, or a selection mode has no selection.

## Limitations

- Only the active sketch is affected.
- Centimetre and metre documents round on the millimetre grid, and the rewritten expressions are in `mm`.

> **Developers:** see the [architecture notes](./arch/Round%20Sketch%20Dimensions.md).

---

[Back to README](../README.md)

*Copyright © 2026 IMA LLC. All rights reserved.*
