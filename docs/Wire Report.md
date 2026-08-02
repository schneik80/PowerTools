# Wire Report

[Back to PowerTools](../README.md)

The Wire Report command presents every routed wire and cable in the design in one theme-aware panel — connectors, pins, gauges, diameters, and computed lengths, organized per assembly. Use it to answer "what wire do I cut, and how long?" without measuring anything by hand.

> **Prove-out status:** this is a beta test command in the Cable prove-out family. Its content and layout may change.

## What it shows

- **Totals** — wire and cable counts, plus the summed conductor length across everything (bill-of-materials style).
- **Per single wire** — both connectors and pins, gauge and sheath diameter, the bare conductor stubs, the sheathed run, and the **total wire length** (the cut length).
- **Per cable** — both connectors and pin sets, gauge, wire and jacket diameters, every wire's full path length, the jacket run, and the **cable length — set by the longest wire path** (highlighted, with the governing pin named). All wires in a manufactured cable are cut to the same length, so the longest run governs the cut.

Lengths are measured from the routing sketches the wires were built from (construction geometry excluded) and shown in the document's display units. The **Refresh** button re-measures — use it after moving connectors or adding routes.

## Prerequisites

- **Beta mode** enabled in PowerTools Preferences.
- A design containing wires or cables built by [Route Wire](./Route%20Wire.md).

## How to use Wire Report

1. On the **Utilities** tab, open the **Power Tools** panel and click **Wire Report**.
2. The report opens as a docked panel, matching Fusion's light or dark theme.
3. Click **Refresh** after changing the routing.

## Access

**Wire Report** is on the **Design** workspace **Utilities** tab, in the **Power Tools** panel (with beta mode enabled).

> **Developers:** see the [architecture notes](./arch/Wire%20Report.md).

---

[Back to PowerTools](../README.md)

---

*Copyright © 2026 IMA LLC. All rights reserved.*
