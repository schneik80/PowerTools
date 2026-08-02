# Route Wire

[Back to PowerTools](../README.md)

The Route Wire command connects two connectors that carry [Define Wires](./Define%20Wires.md) data. Pick the two connector components in an assembly, choose one pin on each, pick an AWG size that both wires allow, accept or edit the recommended sheathed wire diameter, name the wire, and the command builds the physical wire: two bare-conductor stubs and a smooth sheathed run, organized as a local wire assembly and grouped in the timeline.

> **Prove-out status:** this is a beta test command that validates consuming the PowerTools.Cable attributes across an assembly. Its behavior may change.

## What you can do

- Pick two **connector occurrences**; each is scanned for Define Wires points and its available **pins** are listed.
- Choose a **gauge** from the AWG sizes allowed by *both* selected wires (the intersection of their min/max ranges).
- Get a **recommended wire diameter** (bare conductor for the chosen AWG plus insulation walls) that you can edit before building.
- See a **preview line** between the two connector exit points as soon as both pins are chosen.
- Name the wire; everything created is labeled with it.

## What gets built on OK

```text
Root of the design
  Wire <name>          (local assembly component)
    Conductor          bodies 1 and 2 - bare conductor, start-to-strip, AWG diameter
    Sheath             body 3 - strip-to-exit, smooth exit-to-exit spline,
                       exit-to-strip, at the sheath diameter
```

Each body is a solid circular **Pipe** feature along a 3D-sketch path whose points are **linked to the connector geometry** (Include 3D Geometry), so the wire is **associative** — it follows when connectors move. The exit-to-exit spline is made tangent to both exit segments (falling back to direction-guided fit points where 3D tangency is unavailable). All timeline items are grouped as **Wire \<name\>**, and the sketches, features, and bodies carry `Wire <name> ...` names. The wire assembly component is stamped with a `PowerTools.Cable` / `route` attribute recording both ends (connector ids, wire ids, pins, occurrence tokens), the gauge, and the diameter.

## Prerequisites

- **Beta mode** must be enabled in PowerTools Preferences.
- A **parametric** Fusion 3D design (the features are grouped in the timeline).
- An assembly with at least two occurrences whose components have complete Define Wires data (all three points per wire).

## How to use Route Wire

1. Open the assembly containing the two connectors.
2. On the **Utilities** tab, open the **Power Tools** panel and click **Route Wire**.
3. Pick **Connector 1** and **Connector 2** in the canvas or browser. Each shows its component name and available pins; pick a **Pin** for each side.
4. Choose the **Gauge (AWG)** — only sizes allowed by both wires are offered. The **Wire diameter** updates to the recommended sheathed size; edit it if needed.
5. Enter a **Wire name** and click **OK**. The command reports the pins, gauge, and diameter it built.

> **Note:** the wire follows ordinary connector moves on its own. **Swapping or re-inserting** a connector, or redefining its wire points, breaks the links — run [Update Wire](./Update%20Wire.md) to rebuild the wire from its stored route data.

## Access

**Route Wire** is on the **Design** workspace **Utilities** tab, in the **Power Tools** panel (with beta mode enabled).

> **Developers:** see the [architecture notes](./arch/Route%20Wire.md).

---

[Back to PowerTools](../README.md)

---

*Copyright © 2026 IMA LLC. All rights reserved.*
