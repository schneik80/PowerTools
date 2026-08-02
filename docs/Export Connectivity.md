# Export Connectivity

[Back to PowerTools](../README.md)

The Export Connectivity command writes the assembly's connectors and routed wires/cables as an industry-practice **CSV wire list** — one row per wire with `From, From Pin, To, To Pin, Color, Gauge (AWG)` plus diameters and measured lengths. The file is meant to be **edited**: add rows to define new connectivity, then run [Import Connectivity](./Import%20Connectivity.md) to build it.

> **Prove-out status:** this is a beta test command in the Cable prove-out family. Its behavior may change.

## What gets written

- A commented (`#`) **connector reference block**: every connector's designator, component name, pins with their allowed AWG ranges, and whether it has a cable point — everything needed to author rows by hand.
- The header row: `Cable, Wire, From, From Pin, To, To Pin, Color, Gauge (AWG), Wire OD (mm), Cable OD (mm), Length (mm)`.
- One row per routed **single wire** (`Cable` empty, `Wire` = the route name).
- One row per wire of each routed **cable** (rows share the `Cable` value; pins are paired row by row).
- **Length (mm)** is measured from the routing sketches (a cable wire's length includes the jacket run) — documentation only, ignored on import.

Connectors are identified by their **reference designators**; the export refuses while any connector is unassigned — run [Assign Designators](./Assign%20Designators.md) first.

## Editing the file

- Open it in Excel or any text editor. Lines starting with `#` and the `Length` column are ignored on import.
- Add a **single wire**: leave `Cable` empty, name it in `Wire`, fill both ends, `Color` (one of the 12 standard colors; blank = default), and `Gauge`.
- Add a **cable**: give every wire row the same `Cable` value — one row per wire, pins paired per row, one gauge for the whole cable. Blank diameters use the standard recommendations.

## Prerequisites

- **Beta mode** enabled in PowerTools Preferences.
- Every connector assigned a designator ([Assign Designators](./Assign%20Designators.md)).

## Access

**Export Connectivity** is on the **Design** workspace **Utilities** tab, in the **Power Tools** panel (with beta mode enabled).

> **Developers:** see the [architecture notes](./arch/Export%20Connectivity.md) — the CSV format specification lives there.

---

[Back to PowerTools](../README.md)

---

*Copyright © 2026 IMA LLC. All rights reserved.*
