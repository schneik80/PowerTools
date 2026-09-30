# Radial Hole Circle

[Back to README](../README.md)

## Overview

Radial Hole Circle places a construction circle in the active sketch by picking its centre point and dragging to set the diameter, then adds a sketch point constrained vertically above the centre.

A bolt-circle pattern starts the same way every time: a construction circle on a centre, a diameter dimension, and one point on the circle at twelve o'clock to pattern from. Radial Hole Circle draws all of that, already constrained, in two clicks.

> **Beta, and off by default.** Tick **Show beta commands** under **General** in **File › PowerTools Preferences**, then enable **Radial Hole Circle** under **Part Modeling**, and restart Fusion.

## Prerequisites

- A design document must be open.
- A sketch must be in edit mode, with a sketch point or vertex to use as the centre.

## Where to find it

**Sketch** tab › **Create** panel › **Radial Hole Circle**, while editing a sketch.

## How to use

1. Double-click the sketch to edit it and select **Radial Hole Circle**.
2. Pick a sketch point or vertex for the centre. A white preview circle and crosshair follow the cursor, and the **Diameter** field shows the current value.
3. Move the cursor to the diameter you want and click to commit, or type a value in **Diameter** and select **Create**.

The command closes after one circle. Run it again for another.

## Options

| Option | Default | Effect |
|---|---|---|
| **Circle Center** | — | The sketch point or vertex to centre on; the box hides once picked |
| **Diameter** | 25 mm, in the document's units | Set by dragging or by typing |

**Create** is enabled once a centre is picked and the diameter is greater than zero.

## What it produces

| Object | Notes |
|---|---|
| Construction circle | Centred on the picked point, with a coincident constraint holding it there |
| Diameter dimension | A driving dimension you can edit later |
| Sketch point | On the circle, directly above the centre, held by a coincident constraint |
| Construction line | From the centre to that point, with a vertical constraint |

## Limitations

- The centre must be an existing point; the command cannot place a free circle.
- The preview is not visible when the sketch plane is viewed edge-on.

> **Developers:** see the [architecture notes](./arch/RadialHoleCircle.md).

---

[Back to README](../README.md)

*Copyright © 2026 IMA LLC. All rights reserved.*
