# Assign Part Numbers

[Back to README](../README.md)

## Overview

The **Assign Part Numbers** command stamps controlled, team-unique part numbers onto the active Autodesk Fusion 3D design. Numbers are drawn from hub-wide sequential schemes — `PRT`, `ASY`, `WLD`, `COT`, and `TOL` — whose counters are persisted in a shared JSON cache inside the active hub so multiple users never mint duplicate numbers.

When the active design has local components, the dialog presents a per-component table so each local can be assigned its own scheme and sequential number in a single atomic cache update. When the design has no local components, a single scheme dropdown appears instead. Scheme choices are filtered by the design's `DesignIntentTypes` so, for example, a Part Intent design can never be assigned an `ASY` number.

> **Note:** This command is available only in the Autodesk Fusion Design workspace. Drawings use the separate [Assign Drawing Number](./Assign%20Drawing%20Number.md) command, which shares the same hub cache.

## Capabilities

| Capability | Details |
|---|---|
| Intent-filtered schemes | Scheme dropdown lists only the prefixes allowed for the design's `DesignIntentTypes` (Part, Assembly, or Hybrid) |
| Per-local-component numbering | Table mode shows one row per local (non-referenced) occurrence plus the root component; each row picks its own scheme and receives its own sequential number |
| Hub-shared counters | Counters live in `Assets / Pn-Cache / pn-cache.json` so multiple users on the same hub get distinct numbers without coordination |
| Optimistic retry | Cache commit uses download → modify → upload → verify with up to 3 retries to handle concurrent writers |
| Auto-PN suppression | Fusion's auto-generated placeholder part numbers (`YYYY-MM-DD-HH-MM-SS-mmm`) are treated as no existing assignment and do not trigger the overwrite prompt |
| Live preview | Each row previews its next-in-scheme number as the user picks a scheme; numbers stay sequential across rows that share a prefix |
| Atomic commit | All rows in a single invocation bump the cache in one version, so the numbers assigned are contiguous and never interleave with another user's numbers |
| Inline overwrite notice | When any target already has a user-assigned part number, the dialog shows an inline warning listing the affected components and their current values. No extra modal confirmation — clicking Assign on a chosen scheme replaces the existing number; leaving a row at `(skip)` preserves it |
| Readback verification | After each `component.partNumber` set, the value is re-read; a mismatch is reported as a stamp failure even when the set call itself did not raise. This is the primary safety net against the MFGDM silent-set failure mode |

## Schemes

| Prefix | Item class | Allowed for intent |
|---|---|---|
| `PRT` | Custom part (single piece, any process) | Part, Hybrid |
| `ASY` | Assembly (has a BOM; one or more children) | Assembly, Hybrid |
| `WLD` | Weldment (as-welded item treated as a single deliverable) | Assembly, Hybrid |
| `COT` | Commercial off-the-shelf (fasteners, bearings, vendor components) | Part, Hybrid |
| `TOL` | Tooling, fixture, or jig | All design intents |
| `DWG` | Drawing (controlled document) | Reserved for drawings — not available in this command |

Numbers are zero-padded to six digits: `PRT-000001`, `ASY-000042`, `TOL-000017`, etc.

## Prerequisites

- The active document must be a saved Autodesk Fusion 3D design.
- The active hub must contain a project named **Assets** (project creation is deliberately not automated — it usually requires admin permissions).
- The user must have write permission on the **Assets** project.
- Ideally all targets have been saved to the cloud at least once so their MFGDM metadata exists. If not, the stamp step will fail for those targets and the failures will be listed in the post-close warning. See *Cloud metadata (MFGDM) readiness* under **Architecture**.

## Notes

- The **Pn-Cache** folder under **Assets** is auto-created on first use.
- `pn-cache.json` is auto-created on first commit and versioned thereafter by Fusion's normal file-versioning.
- Document save after assignment is intentionally left to the user so the command dialog closes promptly on **Assign**.
- Deleted documents do not release their numbers back to the pool — numbering is monotonic.
- The command verifies every `component.partNumber` write with an immediate readback. Discrepancies are reported as stamp errors in the post-close warning message rather than silently ignored.

## Access

The **Assign Part Numbers** command is located on the **Tools** tab, in the **Power Tools** panel of the Autodesk Fusion Design workspace.

1. Open a saved Fusion 3D design.
2. On the **Tools** tab, in the **Power Tools** panel, select **Assign Part Numbers**.

## How to use

### Simple mode — no local components

1. Open a saved design that has no local occurrences.
2. Run **Assign Part Numbers**.
3. The dialog shows the design intent, the component name, a **Scheme** dropdown, and a read-only **Preview**.
4. Pick a scheme (e.g., `PRT — Custom part`). The preview updates to the real next number from the hub cache.
5. Click **Assign**. The cache counter is bumped; `rootComponent.partNumber` is set; the dialog closes.

### Table mode — design has local components

1. Open a saved design that contains at least one local (non-referenced) occurrence.
2. Run **Assign Part Numbers**.
3. The dialog shows:
   - The design intent (e.g., `Hybrid Intent`).
   - An inline warning note listing affected components, shown only when any target already has a user-assigned part number.
   - A **Components** group with a table. Row 1 is the root component, tagged `(root)`. Subsequent rows are each unique local component.
   - Each row has its own **Scheme** dropdown (defaulted to `(skip)`) and read-only **Preview**.
4. Pick schemes per row. The **Preview** column updates live so each row previews the actual number it will receive. Rows sharing a prefix advance sequentially (first `PRT` row previews the next number, second previews the one after, and so on).
5. Leave any row at `(skip)` to exclude it from the assignment. This also preserves an existing part number on that component.
6. The **Assign** button is disabled until at least one row picks a real scheme.
7. Click **Assign**. All chosen rows are committed to the hub cache in a single atomic update; `component.partNumber` is stamped on each chosen component; the dialog closes. Rows whose targets had a prior part number are replaced in-place with no further confirmation.

### Overwrite notice

If any target already has a user-assigned part number (not a Fusion auto-generated placeholder), an inline warning is shown in the dialog listing the affected components and their current values. No extra modal confirmation is shown — the dialog has all the information up front, so clicking **Assign** proceeds directly:

- Rows with a real scheme chosen have their existing part number replaced by the new one.
- Rows left at `(skip)` keep their existing part number unchanged.

To back out without making any changes, click **Cancel**.

## Output

- `component.partNumber` is set to the formatted number (e.g., `PRT-000042`) on each chosen target.
- `Assets / Pn-Cache / pn-cache.json` is updated with the new `lastUsed` counter for each affected scheme. The file is versioned by Fusion; previous versions remain accessible in the Fusion Team web UI for audit.

## Limitations

- The **Assets** project must exist; if absent, the command aborts with a clear error message.
- Stamping a local component that was added since the last document save routes through the MFGDM GraphQL API and silently fails because the component has no cloud metadata yet. The readback verification catches this and surfaces the affected component names in the post-close warning; the user should save the document and re-run for those targets. The hub cache counter is still consumed for the failed stamp — the number it would have assigned is simply not written to the component. See *Cloud metadata (MFGDM) readiness* under **Architecture** for the full rationale.
- Numbers are not recycled when documents or components are deleted.
- Part numbers for referenced (linked) components are **not** assigned by this command — those belong to the source design and must be assigned there.
- The preview number shown in the dialog reflects the cache state at the moment the dialog opened. If a teammate commits between dialog open and **Assign**, the optimistic-retry loop transparently picks a fresh baseline and the actual assigned number may differ from the preview.
- After more than 3 consecutive lost-race retries, the command aborts cleanly with an error and no component is stamped.
- Scheme counters are stored as six-digit numbers; a single scheme can hold up to 999,999 assignments.

> **Developers:** see the [architecture notes](./Arch/Assign%20Part%20Numbers.md).

---

[Back to README](../README.md)

---

*Copyright © 2026 IMA LLC. All rights reserved.*
