# Sketch Under-constrained

[Back to README](../README.md)

## Overview

Sketch Under-constrained highlights the sketch objects in the active sketch that are not fully constrained.

In a dense sketch it is hard to see which line or point still has a degree of freedom. This command asks Fusion's sketch solver for the list and highlights every under-constrained object on the canvas, so you can work through them rather than dragging things to find out.

## Prerequisites

- A design document must be open.
- A sketch must be in edit mode.

## Where to find it

**Sketch** tab › **Modify** panel › **Sketch Under-constrained**, while editing a sketch.

## How to use

1. Double-click the sketch to edit it.
2. Select **Sketch Under-constrained** from the **Modify** panel.
3. Under-constrained objects are highlighted on the canvas and a message summarises the result.
4. Add dimensions or constraints, then run the command again to check.

## Limitations

- The command only reports; it applies no constraints.
- Run it again after each change to refresh the highlight.

> **Developers:** see the [architecture notes](./arch/SketchUnder.md).

---

[Back to README](../README.md)

*Copyright © 2026 IMA LLC. All rights reserved.*
