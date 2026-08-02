# Define Wires

[Back to PowerTools](../README.md)

The Define Wires command turns a single-component part into a cable **connector**: for each wire you pick three points on the model — **conductor start**, **strip length**, and **connector exit** — assign a **pin** and an **AWG gauge range**, and the command stores the whole set as durable attributes on those points. Re-running the command on the same part recalls everything for editing. [Route Wire](./Route%20Wire.md) consumes these attributes to build single wires and multi-conductor cables between connectors across an assembly, and [Wire Report](./Wire%20Report.md) reports the results.

> **Prove-out status:** this is a beta test command whose purpose is to validate the attribute scheme. Its behavior and stored format may change.

## What you can do

- Define one or more **wires** in a table; each row shows the wire's pin, gauge range, and how many of its three points are selected.
- Pick each point as a **circular/arc edge**, a **circular/arc sketch curve**, a **sketch point**, or a **work point**. For a sketch circle/arc the command uses its existing center sketch point; for a circular edge it **creates a work point at the edge center** on OK.
- Give each wire a **pin** (must be unique within the connector) and a **min/max gauge** as numeric AWG values (min must not exceed max, 0-40). New wires default to the next pin number (1, 2, 3, ...); edit freely.
- On connectors with **more than one wire**, pick the **cable point** — where a multi-conductor cable meets the connector and its wires fan out to the pins. It accepts the same geometry types as the wire points and is required before OK enables.
- Re-run the command to **recall and edit** the stored set — add or delete wires, change pins or gauges, or re-pick points.
- If a stored point was deleted outside the command, the affected rows are flagged **missing** and OK stays disabled until you re-select those points or delete the rows.

## Prerequisites

- **Beta mode** must be enabled in PowerTools Preferences (this is a beta command).
- An Autodesk Fusion 3D design must be active.
- The design must contain **only the root component** — no occurrences. The component itself is the connector.

## How to use Define Wires

1. Open the connector part file (a single-component design).
2. On the **Utilities** tab, open the **Power Tools** panel and click **Define Wires**.
3. The **Wires** table lists the connector's wires; the **Wire editor** below it always edits one wire. Click **Add** to add a wire, **Delete** to remove the one being edited, or a row's **Edit** button to load that wire into the editor.
4. In the editor, pick the wire's three points in order — conductor start, strip length, connector exit — then enter the pin and gauge range. Edits apply to the row immediately; switching rows never loses changes.
5. With two or more wires, pick the **Cable point** (at the bottom of the dialog) — [Route Wire](./Route%20Wire.md) needs it to route this connector as a cable.
6. Click **OK**. The command creates any needed work points (named `Wire <pin> <role>` / `Cable point`), writes the attributes, and reports what it wrote.

> **Note:** work points created for edge picks are kept even if you later re-pick or delete that wire — only the attributes are removed. Delete unwanted work points in the browser.

## Access

**Define Wires** is on the **Design** workspace **Utilities** tab, in the **Power Tools** panel (with beta mode enabled).

> **Developers:** see the [architecture notes](./arch/Define%20Wires.md) for the attribute schema contract.

---

[Back to PowerTools](../README.md)

---

*Copyright © 2026 IMA LLC. All rights reserved.*
