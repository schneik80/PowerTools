# Measure Path

[Back to README](../README.md)

## Overview

Measure Path measures the cumulative length of a connected chain of sketch curves and model edges between two objects you pick.

Fusion's **Measure** reports the length of what you select, so measuring the developed length of a gasket outline, the run of a routed slot or a spline chain means clicking every segment and hoping none was missed. Measure Path finds the chain for you: pick where it starts and where it ends, and it follows the geometry between them, numbers each segment, and copies the total to the clipboard.

## Prerequisites

- A design document must be open.

## Where to find it

The **Inspect** panel of the design tabs (Solid, Surface, Mesh, Sheet Metal, Plastic), alongside Fusion's **Measure**.

## How to use

1. Pick a **Start** object.
2. Pick an **End** object.
3. Read the **Length**. The **Segments** table breaks the total down run by run, numbered to match the cones in the viewport.
4. **Close** copies the length to the clipboard, formatted in the document's units.

Either selection can be a sketch point, a construction point, a vertex, a sketch curve or a model edge. The chain may mix sketch curves and model edges as long as their ends meet.

Selecting a curve or edge, rather than a point, counts its full length at either end of the path. A start curve is entered from whichever end can reach onward; an end curve is added when the chain arrives at either of its ends; the same curve picked as both Start and End is counted once. The **Length** is always exactly the sum of the rows in **Segments**.

## Reading the viewport

| Marker | Meaning |
|---|---|
| Highlighted curves | The chain being measured |
| Green dot **Start** | Where the measurement begins |
| Red dot **End** | Where it finishes |
| Numbered cone, green through red | One per segment of a finished path, at its midpoint, pointing the way the path runs; the number matches the **Segments** row |
| Amber cone | An available direction at a fork |
| White cone | The direction under your cursor |

Labels face you from any viewpoint and markers keep their size on screen as you zoom. Once a path resolves there is exactly one Start and one End, on the chain's real terminals, which tells you the path's direction even when a chain doubles back on itself. Above 250 segments the cones are skipped and the status line says so.

## Options

| Option | Default | Effect |
|---|---|---|
| **Shortest path** | On | Reports the geometrically shortest route immediately, with no clicking |
| **Undo last direction** | — | Steps back one choice when steering by hand |

Turn **Shortest path** off when you want a particular route. The command then resolves as much as it can without guessing: where exactly one chain connects the two objects it is reported directly; where the mixed graph is ambiguous but there is exactly one all-edge or one all-sketch chain, that one is used (this usually resolves a sketch drawn on top of a solid); otherwise the resolved portion is highlighted with its partial length, and an amber cone marks each available direction at the fork. Click a cone, or the highlighted curve itself, to take that direction. Directions that cannot reach the End object are never offered, so you are only asked about a choice that changes the answer.

### Worked example: the perimeter of a flange

1. Select **Inspect › Measure Path**.
2. Pick the vertex at one corner of the flange as **Start** and the vertex at the far corner as **End**.
3. With **Shortest path** on you get the shorter way round. Untick it.
4. Both ways round are valid, so a cone appears at each. Click the one running the way you want.
5. The chain completes and **Length** is the developed length of that side.

To measure the whole perimeter, pick the two vertices either side of a single edge and steer the long way round; that one edge is the only part not included.

## Limitations

- Full circles and ellipses have no endpoints and cannot be part of a chain; select an arc, a line, an edge or a point instead. A full circle's length is already available from **Measure**.
- Endpoints must be coincident within 1 micron (0.0001 cm) to count as connected. When no chain is found, the message reports the nearest gap.
- A circle's centre point is not a junction: a circle or arc centred on a point you pass through is not a continuation from it.
- Nothing is added to the design; no feature appears in the timeline.
- Disabling the command under **File › PowerTools Preferences › Part Modeling** removes the button on the next Fusion restart.

> **Developers:** see the [architecture notes](./arch/Measure%20Path.md).

---

[Back to README](../README.md)

*Copyright © 2026 IMA LLC. All rights reserved.*
