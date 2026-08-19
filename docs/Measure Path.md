# Measure Path

Measures the **cumulative arc length** of a connected chain of sketch curves and
model edges between two objects you pick.

Fusion's own Measure reports point-to-point distance and single-entity values.
Measure Path adds along the geometry the whole way round — the developed length of
a gasket outline, the run of a routed slot, the perimeter of an irregular flange,
the true length of a spline chain that no single measurement covers.

**Location:** every **Inspect** panel in a design — Solid, Surface, Mesh, Sheet
Metal and Plastic tabs all carry one, alongside Fusion's Measure.

---

## Using it

1. Pick a **Start** object.
2. Pick an **End** object.
3. Read the **Length**. The **Segments** table breaks the total down run by run.
4. **Close** copies the length to the clipboard.

Either selection can be a **sketch point**, a **vertex**, a **sketch curve**, or a
**model edge**. The chain may mix sketch curves and model edges freely, as long as
their ends actually meet.

### Picking a curve or edge rather than a point

Selecting a curve or edge counts its **full length**, at either end of the path:

- A **start** curve is entered from whichever of its ends can reach onward. If both
  ends can, that is itself the first choice and you get a cone at each end.
- An **end** curve is added when the chain arrives at either of its ends.
- Pick the same curve as both Start and End and it is counted once.

The **Length** is always exactly the sum of the rows in the **Segments** table.
Every element of the path is in both, or in neither.

## Reading the viewport

The path is annotated as you go:

| Marker | Meaning |
|---|---|
| Highlighted curves | The chain currently being measured |
| Green dot labelled **Start** | Where the measurement begins |
| Red dot labelled **End** | Where it finishes |
| Amber cone | An available direction at a fork, its point aimed the way that branch runs |
| White cone | The direction under your cursor |

Labels turn to face you from any viewpoint, and the markers stay the same size on
screen however far you zoom.

Once a path resolves there is exactly one Start and one End, on the chain's real
terminals. That is what tells you the path's **sense** — which matters as soon as a
chain doubles back on itself, or the two objects you picked look alike. While a path
is still unresolved, End sits on the target you picked, so you can see where the
measurement is heading rather than only where it has got to.

## Shortest path, or steer it yourself

**Shortest path** is on by default and reports the geometrically shortest route
immediately, with no clicking. That is the right answer most of the time.

Turn it off when you want a *particular* route rather than the shortest one. The
command then resolves as much as it can without guessing:

- Where exactly **one** chain connects the two objects, it is reported directly.
- Where the mixed graph is ambiguous but there is exactly **one** all-edge chain, or
  exactly **one** all-sketch chain, that one is used. This is usually what resolves a
  sketch drawn on top of a solid.
- Otherwise the resolved portion is highlighted, its partial length is shown, and a
  **cone** appears on each available direction at the fork.

Click a cone — or click the highlighted curve itself, whichever you find easier — to
take that direction. The command then carries on to the next real fork, or to the end.
**Undo last direction** steps back one choice.

Directions that cannot reach the End object are never offered. So a fork with only one
viable continuation is followed without asking, and you are only ever asked about a
choice that genuinely changes the answer.

## Worked example: the perimeter of a flange

1. **Inspect › Measure Path**.
2. Click the vertex at one corner of the flange as **Start**.
3. Click the vertex at the far corner as **End**.
4. With **Shortest path** on you get the shorter way round. Uncheck it.
5. Both ways round are valid, so a cone appears at each. Click the one running the
   way you want.
6. The chain completes to the End vertex and the **Length** is the developed length
   of that side.

To measure the *whole* perimeter, pick the two vertices either side of a single edge
and steer the long way round; that one edge is the only part not included.

## Notes and limits

- **Full circles and ellipses have no endpoints** and so cannot be part of a chain.
  Select an arc, a line, an edge or a point. A full circle's length is already
  available from Fusion's Measure.
- **Ends must actually meet.** Endpoints must be coincident within 1 micron
  (0.0001 cm) to count as connected. When no chain is found, the message reports the
  nearest gap, which tells you whether the geometry is genuinely not touching or is
  just outside tolerance.
- **A circle's centre point is not a junction.** A circle or arc centred on a point
  you pass through is not treated as a continuation from it.
- The search spreads outward from your two selections through real connectivity, so
  it does not scan an entire assembly.
- Nothing is added to your design. The command only measures — no feature appears in
  the timeline, and nothing is modified.

## Preferences

Listed under **Part Modeling** in **PowerTools Preferences**, enabled by default.
Disabling it removes the button from every Inspect panel on the next Fusion restart.

---

*Architecture note: [docs/arch/Measure Path.md](arch/Measure%20Path.md).*

*Copyright © 2026 IMA LLC. All rights reserved.*
