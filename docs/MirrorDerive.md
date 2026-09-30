# Create Mirrored Design

[Back to README](../README.md)

## Overview

Create Mirrored Design derives every body of the active design into a new document saved alongside it as `<name>-mirror`, then applies a uniform scale of −1 to produce a mirrored copy without touching the source.

SolidWorks calls this **Mirror Part** and Inventor **Mirror Components › Create New**: the opposite-hand version of a part as its own file, derived from the original so the two always match. Fusion has Derive and Scale but no one-step opposite-hand part. This command chains them: the derive stays associative, so the mirror follows later changes to the source, and the scale features remain editable in the mirror's timeline. (Scaling by −1 to mirror is sometimes called the Lockwood maneuver.)

## Prerequisites

- A design document saved to a hub with no unsaved changes; the mirror is saved in the same folder.
- The Design workspace must be active.

## Where to find it

**Solid** tab › **Create** panel › **Create Mirrored Design**, in the Design workspace, directly after **Derive** inside the Create dropdown.

## How to use

1. Open the saved design to mirror.
2. Select **Solid › Create › Create Mirrored Design**.
3. Wait for the confirmation message naming the new document. The mirror document is left open and active.

## What it produces

- A new document `<document name>-mirror` in the source's folder, containing a Derive of every body of every component in the source, and one Scale feature per component, about that component's origin, with its factor set to −1.
- The source design is not modified.

## Limitations

- Every body is derived, solid or surface. Sketches and construction geometry are not.
- A uniform scale of −1 about a point is a point inversion, which is a mirror plus a 180° rotation; the shape is the opposite-hand part, its orientation may not be.
- If `<document name>-mirror` already exists in the folder, the save fails; rename or delete the existing document first.
- Not available in the Drawing, Simulation or Manufacture workspaces.

> **Developers:** see the [architecture notes](./arch/MirrorDerive.md).

---

[Back to README](../README.md)

*Copyright © 2026 IMA LLC. All rights reserved.*
