# Route Wire

[Back to PowerTools](../README.md)

The Route Wire command connects two connectors that carry [Define Wires](./Define%20Wires.md) data. Pick the two connector components in an assembly, choose the **route type** — a **single wire** (one pin on each side) or a **multi-conductor cable** (every pin, paired in order) — pick an AWG size the wires allow, accept or edit the recommended diameters, name the route, and the command builds the physical geometry as a local assembly grouped in the timeline. (A **ribbon cable** type is listed but not implemented yet.)

> **Prove-out status:** this is a beta test command that validates consuming the PowerTools.Cable attributes across an assembly. Its behavior may change.

## What you can do

- Pick two **connector occurrences**; each is scanned for Define Wires points and its available **pins** are listed.
- Choose a **gauge** from the AWG sizes allowed by *both* selected wires (the intersection of their min/max ranges).
- Get a **recommended wire diameter** (bare conductor for the chosen AWG plus insulation walls) that you can edit before building.
- See a **preview line** as soon as the route is defined — between the two exit points (single wire) or the two cable points (cable).
- Name the route; everything created is labeled with it.

## What gets built on OK

**Single wire:**

```text
Root of the design
  Wire <name>          (local assembly component)
    Conductor          bodies 1 and 2 - bare conductor, start-to-strip, AWG diameter
    Sheath             body 3 - strip-to-exit, smooth exit-to-exit spline,
                       exit-to-strip, at the sheath diameter
```

**Cable** (pins paired in sorted order, 1-1, 2-2, ...; both connectors need the cable point from Define Wires and matching pin counts):

```text
Root of the design
  Cable <name>         (component; owns the jacket body - cable point to
                        cable point, at the cable diameter)
    Wire <pin>         one component per pair, 4 bodies each:
                       2 bare-conductor stubs (start-to-strip, AWG diameter)
                       2 sheathed end segments (strip-to-exit, then a smooth
                        fan-out spline to the cable point, wire diameter)
```

One gauge governs the whole cable (the AWG list is the intersection across every paired wire). The **cable diameter** defaults to the standard cable-design recommendation — packed wire bundle (per-count packing factor), a lay allowance, plus jacket walls — and stays editable.

Each body is a solid circular **Pipe** feature along a 3D-sketch path whose points are **linked to the connector geometry** (Include 3D Geometry), so wires and cables are **associative** — they follow when connectors move. Splines are made tangent to their neighboring segments (falling back to direction-guided fit points where 3D tangency is unavailable, reported in the summary). All timeline items are grouped as **Wire \<name\>** or **Cable \<name\>**, with matching sketch, feature, and body names. The built assembly component is stamped with a `PowerTools.Cable` / `route` attribute recording both ends (connector ids, wire ids, pins, occurrence tokens), the gauge, and the diameters.

## Prerequisites

- **Beta mode** must be enabled in PowerTools Preferences.
- A **parametric** Fusion 3D design (the features are grouped in the timeline).
- An assembly with at least two occurrences whose components have complete Define Wires data (all three points per wire).

## How to use Route Wire

1. Open the assembly containing the two connectors.
2. On the **Utilities** tab, open the **Power Tools** panel and click **Route Wire**.
3. Choose the **Route type**. Pick **Connector 1** and **Connector 2** in the canvas or browser; each shows its component name and available pins.
4. **Single wire**: pick a **Pin** for each side. **Cable**: pins are hidden — every pin connects, paired in sorted order.
5. Choose the **Gauge (AWG)** — only sizes the wires allow are offered. The **Wire diameter** (and for cables the **Cable diameter**) updates to the recommendation; edit if needed.
6. Enter a name and click **OK**. The command reports the pins, gauge, and diameters it built.

> **Note:** wires and cables follow ordinary connector moves on their own. **Swapping or re-inserting** a connector, or redefining its wire points, breaks the links — run [Update Wire](./Update%20Wire.md) to rebuild the wire or cable from its stored route data.

## Access

**Route Wire** is on the **Design** workspace **Utilities** tab, in the **Power Tools** panel (with beta mode enabled).

> **Developers:** see the [architecture notes](./arch/Route%20Wire.md).

---

[Back to PowerTools](../README.md)

---

*Copyright © 2026 IMA LLC. All rights reserved.*
