# Version Diff

[Back to README](../README.md)

## Overview

Version Diff compares the timeline of the active design against another saved version of the same document and opens an HTML report of every feature added, deleted, changed or unchanged.

Onshape can compare two versions of a Part Studio and SolidWorks has a Compare Features utility; Fusion shows a version list and nothing about what changed between two entries. Version Diff answers "what did my colleague change in v14?" with a two-column diff: new and deleted features, parameter values that moved, sketches whose content changed, external references that updated, and features whose health went from healthy to error, plus a side-by-side of material, mass, volume and extents.

> **Off by default.** Enable it under **File › PowerTools Preferences › Document Tools › Version Diff** and restart Fusion.

## Prerequisites

- A design document saved to a hub, with at least two versions.
- A parametric design. Direct Design mode is not supported.

Each of these is checked when you select the button, with a message saying which one failed.

## Where to find it

**Utilities** tab › **Power Tools** panel › **Version Diff**, in the Design workspace.

## How to use

1. Open the version you want to treat as the newer side; normally the latest.
2. Select **Version Diff**. The dialog shows:
   - **Current Version**: version number, date saved, last saved by, description.
   - **Version Summary** (collapsed): total versions, creation and last-save dates and users, whether the latest is a milestone or revision, and public share state.
   - **Compare With Version**: every other version, newest first, labelled `V<n> - <date> <time>`. The newest other version is preselected.
3. Choose a version and select **OK**. The comparison version is opened, both timelines are walked, and it is closed again.
4. The report opens in Fusion's built-in browser.

## Reading the report

**Version cards** show the two versions with thumbnails, number, date, last-saved-by and description. Fusion's desktop API reports the last editor of the *file*, so both cards show the same name; for per-version authorship use [History](./Document%20History.md).

**Visual timeline**: both timelines as rows of feature boxes with ribbons between matched features; fan-outs mark insertions, fan-ins deletions. It scrolls sideways on large designs.

**Design properties**: material, appearances, body count, mass, volume, area, density, centre of mass and extents side by side (kg, cm³, cm², cm), with changed values highlighted.

**Summary badges** count the changes by status and filter the table when clicked:

| Badge | Status | Meaning |
|---|---|---|
| **Newer** | `NEW` | Feature present only in the newer version |
| **Deleted** | `DEL` | Feature present only in the older version |
| **XREF Updated** | `VER Δ` | An external reference whose version changed; the transition is shown in the status column |
| **Sketch Modified** | `SK Δ` | A sketch whose content changed, with counts of lines, arcs, circles, splines, points, texts, dimensions, constraints and profiles that differ |
| **Params Changed** | `PRM Δ` | Parameter values that changed, were added or were removed (`d1: 10 mm → 15 mm`) |
| **Health Changed** | `HTH Δ` | Only the health state changed (`Healthy → Error`) |
| **Unchanged** | `SAME` | Identical in both versions |

The XREF, Sketch, Params and Health badges appear only when their count is above zero.

**Diff table**: older version on the left, newer on the right, status in the centre, with feature-type icons and only the changed side highlighted.

## What it produces

Two files in your system's temporary folder, each with its own random name: `version_diff_<id>.json` (the full diff result) and `version_diff_<id>.html` (the report).

## Limitations

- Features are matched by name and type. A renamed feature appears as a deletion and an addition. External references are matched by component name and instance.
- Timeline groups are skipped; the features inside them are compared.
- Statuses are judged from the open document as the newer side. If the version you select is newer than the one you have open, the column headers swap but NEW and DEL still describe the open document.
- Parameter values are compared numerically with a tolerance, so `180.00 deg` and `180 deg` do not count as a change.
- The report is a snapshot; it does not update when the model changes.

> **Developers:** see the [architecture notes](./arch/Version%20Diff.md).

---

[Back to README](../README.md)

*Copyright © 2026 IMA LLC. All rights reserved.*
