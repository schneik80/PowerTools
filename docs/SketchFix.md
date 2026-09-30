# Sketch Repair

[Back to README](../README.md)

## Overview

Sketch Repair attempts to repair the active sketch by removing tiny segments and closing small gaps between endpoints.

SolidWorks users know this as **Repair Sketch**: the tool you reach for when a traced or imported profile refuses to extrude because two endpoints are a hair apart. Fusion has the same repair built in but not on any menu; Sketch Repair runs it from the **Modify** panel.

## Prerequisites

- A design document must be open.
- A sketch must be in edit mode.

## Where to find it

**Sketch** tab › **Modify** panel › **Sketch Repair**, while editing a sketch.

## How to use

1. Double-click the sketch in the browser or on the canvas to edit it.
2. Select **Sketch Repair** from the **Modify** panel.
3. A message reports that the sketch was repaired. Inspect the profiles; if some are still open, the gap was too large for an automatic repair.

## What it does

Two of Fusion's own repair passes run in sequence: the first removes segments at or below the geometry tolerance, the second merges endpoints within tolerance.

## Limitations

- Large gaps and geometry that was never connected are not repaired.
- The completion message is shown regardless of whether anything needed repair.
- Repair quality depends on Fusion's sketch tolerance settings.

> **Developers:** see the [architecture notes](./arch/SketchFix.md).

---

[Back to README](../README.md)

*Copyright © 2026 IMA LLC. All rights reserved.*
