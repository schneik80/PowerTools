# Global Parameters

[Back to README](../README.md)

## Overview

Global Parameters creates and manages shared parameter sets for the active project, stored as documents in the project's `_Global Parameters` folder.

Onshape has Variable Studios, SolidWorks links equations to an external file, Inventor links parameters to a spreadsheet; Fusion's user parameters live in one document only. A Global Parameters set is a small Fusion document that holds the numbers several designs share, an enclosure's wall thickness, a fastener pitch, a rail spacing, so they are defined once and derived wherever they are needed with [Link Global Parameters](./Link%20Global%20Parameters.md). Edit the set, and every design that links it picks up the change on its next update.

## Prerequisites

- A project must be active in the Data Panel. Sets are stored and found in that project.
- A document must be open.

## Where to find it

**Utilities** tab › **Power Tools** panel › **Global Parameters**, in the Design workspace.

## How to use

### Create a set

1. Select **Global Parameters**. The **Project** field shows the active project.
2. Leave **Parameter Set** on **Create New** and enter a **Name** for the set; it defaults to the active document's name.
3. Fill in the table. **Add** appends a row; tick rows and select **Delete** to remove them.
4. Select **OK**. A new design document with the set's name is created in `_Global Parameters` (the folder is created if missing) and saved with the comment `Global Parameters — PowerTools`.

### Edit a set

1. Select **Global Parameters**.
2. Choose the set in **Parameter Set**. The table fills with its parameters, and the dropdown locks for this session so the loaded data cannot be switched out from under you.
3. Change, add or delete rows and select **OK**. Parameters removed from the table are removed from the set document; one that is still referenced there is kept.

### Unsaved edits

If you cancel with unsaved edits, the command asks whether to reopen the dialog and continue. Answer **No** and the edits are discarded; answer **Yes** and the dialog reopens with them. Edits are kept in a pending file until you save or discard them, so they also survive if Fusion closes first.

## Options

| Column | Rule |
|---|---|
| (checkbox) | Selects the row for **Delete** |
| **Name** | Must start with a letter; letters, digits, `_`, `"`, `$`, `°` and `µ` are allowed. Case-sensitive, unique within the set, and not a Fusion unit name (`mm`, `in`, `deg`, `kg`, `pi`, …) |
| **Value** | A number |
| **Unit** | `in`, `ft`, `mm`, `cm` or `m` |
| **Comment** | Optional |

A status line under the table reads **Up to date**, **Unsaved changes**, or **Cannot save** with the reason. Every parameter in a set is marked as a favorite, so it appears in the Favorites section of the Parameters dialog in any design that links the set.

## Preferences

Global Parameters, Link Global Parameters and Refresh Global Parameters Cache are one capability and share a single checkbox under **File › PowerTools Preferences › Assembly**. Changes apply after a Fusion restart.

## Limitations

- Units outside the five offered are shown as `mm` when a set is loaded, and only the numeric part of an expression is kept, so a set edited elsewhere can be changed by the next save here.
- The set is written to its own document only; the active document is not modified. Use Link Global Parameters to bring the parameters into a design.

> **Developers:** see the [architecture notes](./arch/Global%20Parameters.md).

---

[Back to README](../README.md)

*Copyright © 2026 IMA LLC. All rights reserved.*
