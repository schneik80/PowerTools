# Hide Objects

[Back to README](../README.md)

## Overview

Hide Objects hides selected categories of reference and construction geometry across every component in the active design at once.

SolidWorks has **View › Hide All Types** and Inventor has **Object Visibility**; Fusion has a light bulb per folder per component. Before a review, a render or a screenshot of a large assembly, that is a lot of bulbs. Hide Objects switches off the categories you tick in every component, nested ones included. Nothing is deleted or suppressed; anything can be brought back from the browser.

## Prerequisites

- A design document must be open.

## Where to find it

**Utilities** tab › **Utility** panel › **Hide Objects**, in the Design workspace.

## How to use

1. Select **Hide Objects**.
2. Untick any category you want to keep visible. All are ticked by default.
3. Select **OK**.

## Options

| Category | What it hides, in every component |
|---|---|
| **Origin** | The origin folder (point, axes and planes) |
| **Construction Points** | Every construction point |
| **Construction Axes** | Every construction axis |
| **Construction Planes** | Every construction plane |
| **Joint Origins** | Every joint origin |
| **Joints** | The joints folder |
| **Sketches** | Every sketch; the Sketches folder itself is left switched on |
| **Canvas** | The canvases folder |
| **User Coordinate Systems** | Every user coordinate system, one by one |

## Limitations

- There is no per-component or per-object choice, and no matching **Show Objects**; restore visibility from the browser.
- Canvases are controlled at folder level only.
- On a Fusion build without user coordinate systems that category is skipped.

> **Developers:** see the [architecture notes](./arch/HideObjects.md).

---

[Back to README](../README.md)

*Copyright © 2026 IMA LLC. All rights reserved.*
