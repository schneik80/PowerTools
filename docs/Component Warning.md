# Component Warning

[Back to README](../README.md)

## Overview

Component Warning warns before a feature is created outside a component: directly in the root component, or referencing a component other than the one being edited.

In an assembly, a sketch or extrusion made while the root is active ends up belonging to nobody, and geometry referenced across components creates dependencies you did not mean to make. Fusion lets both happen silently. Component Warning watches the feature-creation commands (sketches, primitives, work geometry, extrude, revolve, sweep, loft, rib, web, emboss, hole, thread, patterns, mirror and the surface commands) and asks before the feature lands in the wrong place.

> **Off by default.** Enable it under **File › PowerTools Preferences › Assembly › Component Warning** and restart Fusion.

## Prerequisites

- A design document with Assembly or Hybrid intent. Part-intent designs are skipped, because features there belong in the root.
- The guard is active in the Design workspace only.

## Where to find it

Component Warning has no button. It is switched on in **PowerTools Preferences** and works in the background.

## How to use

1. Model as usual. Starting a feature command while the root component is active, or with a selection in another component, opens a **Component Warning** dialog.
2. Choose:
   - **Yes**: create the feature anyway. The guard pauses for three seconds so it does not ask twice for the same action.
   - **No**: stop warning for this document for the rest of the session.
   - **Cancel**: cancel the command; nothing is created.

## Preferences

Under **File › PowerTools Preferences › Assembly › Component Warning settings**:

| Setting | Default | Effect |
|---|---|---|
| **Also warn when creating a feature in a non-leaf component** | Off | Also warns when the active component still has child components. Read when the guard attaches on entering the Design workspace |

## Limitations

- A document silenced with **No** is remembered only for the session; reopening it restores the warnings.
- Enabling or disabling the command applies after a Fusion restart.

> **Developers:** see the [architecture notes](./arch/Component%20Warning.md).

---

[Back to README](../README.md)

*Copyright © 2026 IMA LLC. All rights reserved.*
