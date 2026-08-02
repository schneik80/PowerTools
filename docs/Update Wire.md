# Update Wire

[Back to PowerTools](../README.md)

The Update Wire command rebuilds a wire or multi-conductor cable created by [Route Wire](./Route%20Wire.md). Routed assemblies follow connector moves on their own (their routing sketches are linked to the connector points), but a connector that is **swapped, re-inserted, or has its wire points redefined** breaks those links. Update Wire is the recovery path: pick the route, and it re-resolves both connectors from the stored route data, deletes the old assembly, and routes it again with the same name, gauge, and diameters — creating fresh links to wherever the connectors are now.

> **Prove-out status:** this is a beta test command in the Cable prove-out family. Its behavior may change.

## What it does

- Lists every **routed wire and cable** in the design (components stamped with the `PowerTools.Cable` / `route` attribute).
- Resolves each end of the selected route back to a connector occurrence — by the stored **occurrence token** first (survives renames and tells apart multiple instances of the same connector), then by unique **connector id** (survives a dead token after re-insertion). The dialog shows how each end matched.
- Finds each wire by its stored **wire id**, falling back to the **pin** when the wire was redefined. Cables reconstruct their **original pairing** from the stored ordered pin lists — even after pins were renamed — and require the cable point on both connectors.
- On **Rebuild**: deletes the old `Wire <name>` / `Cable <name>` timeline group (or its assembly occurrence) and rebuilds with the stored name, gauge, and diameters.

## When resolution fails

The dialog reports the reason and keeps Rebuild disabled:

- **Connector occurrence not found** — the connector was removed and nothing carries its connector id.
- **Several instances of that connector exist** — the stored token is dead and the connector id alone cannot say which instance the wire used. Delete the wire group and use Route Wire to pick the connectors explicitly.
- **Wire no longer defined** — the pin was removed in Define Wires (for cables, the missing pins are listed).
- **No cable point** — a cable's connector lost its cable point; re-run Define Wires on the part.
- **Wire counts differ** — a cable's connectors no longer define matching wire sets, so the pairing cannot be reconstructed.

## Prerequisites

- **Beta mode** enabled in PowerTools Preferences.
- A **parametric** Fusion 3D design containing at least one routed wire.

## How to use Update Wire

1. On the **Utilities** tab, open the **Power Tools** panel and click **Update Wire**.
2. Pick the wire from the **Wire** dropdown; check the resolution report.
3. Click **Rebuild**.

> **Note:** the old wire's timeline group is deleted with its contents. If you manually added unrelated items into that group, move them out first.

## Access

**Update Wire** is on the **Design** workspace **Utilities** tab, in the **Power Tools** panel (with beta mode enabled).

> **Developers:** see the [architecture notes](./arch/Update%20Wire.md).

---

[Back to PowerTools](../README.md)

---

*Copyright © 2026 IMA LLC. All rights reserved.*
