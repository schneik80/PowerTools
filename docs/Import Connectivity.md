# Import Connectivity

[Back to PowerTools](../README.md)

The Import Connectivity command reads a connectivity **CSV wire list** (written by [Export Connectivity](./Export%20Connectivity.md) and edited by you) and builds every wire and multi-conductor cable it defines — the same associative construction, colors, and route data as [Route Wire](./Route%20Wire.md), driven in batch across all the assembly's connectors.

> **Prove-out status:** this is a beta test command in the Cable prove-out family. Its behavior may change.

## How it behaves

- **Additive** — a row whose endpoints match an already-routed connection is skipped and counted; nothing is ever deleted or rebuilt (use [Update Wire](./Update%20Wire.md) for that).
- **Tolerant** — an invalid row or cable group is reported and skipped; it never blocks the rest of the file. The summary lists everything built, skipped, and refused, with reasons.
- Connectors are matched by their **reference designators** ([Assign Designators](./Assign%20Designators.md)).
- Cable rows pair pins **row by row** — the pairing you write is the pairing that gets built.
- A cable's rows may span **more than two connectors** (e.g. J1 breaking out to J3 and J4). Each row names its own From/To; the rows are split into the cable's two ends automatically. A multi-connector end fans its wires out to an **implied breakout point** computed between the connectors — that point is not linked to geometry, so after moving those connectors run [Update Wire](./Update%20Wire.md) to recompute it.

## What is validated per row/cable

- Both designators exist (and are unique) in the assembly.
- Every referenced pin is defined on its connector, and the gauge is inside every wire's allowed AWG range.
- Cables: at least two rows, one gauge, every involved connector has a cable point, no (connector, pin) used twice, no row connecting two connectors on the same end, and unique wire labels (blank labels default to the From pin, prefixed like `J1.1` when several connectors share that end).
- Colors are normalized to the 12 standard wire colors (blank = default for single wires, the standard sequence for cable wires); blank diameters use the standard recommendations.

## Prerequisites

- **Beta mode** enabled in PowerTools Preferences.
- A **parametric** Fusion 3D design whose connectors carry Define Wires data and designators.

## How to use Import Connectivity

1. On the **Utilities** tab, open the **Power Tools** panel and click **Import Connectivity**.
2. Pick the edited `.csv` wire list.
3. Review the summary: wires/cables built, already-routed rows skipped, and any problems.

## Access

**Import Connectivity** is on the **Design** workspace **Utilities** tab, in the **Power Tools** panel (with beta mode enabled).

> **Developers:** see the [architecture notes](./arch/Import%20Connectivity.md).

---

[Back to PowerTools](../README.md)

---

*Copyright © 2026 IMA LLC. All rights reserved.*
