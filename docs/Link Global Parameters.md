# Link Global Parameters

[Back to README](../README.md)

## Overview

Link Global Parameters derives a shared parameter set from the project's `_Global Parameters` folder into the active design.

A set created with [Global Parameters](./Global%20Parameters.md) is only useful once a design can use its numbers. This command lists the sets in the active project, previews the one you pick, and derives it into the design so its parameters appear in the Parameters dialog as favorites and can be used in any expression. The derive stays linked, so a later edit to the set flows into the design when its references update.

## Prerequisites

- The active design must be saved to a hub; the command refuses an unsaved document.
- A project must be active in the Data Panel, with at least one set in its `_Global Parameters` folder.

## Where to find it

**Utilities** tab › **Power Tools** panel › **Link Global Parameters**, in the Design workspace, next to **Global Parameters**.

## How to use

1. Open the design that should use the parameters.
2. Select **Link Global Parameters**. The project's `_Global Parameters` folder is scanned and its sets listed in **Parameter Set**.
3. Choose a set. The preview table shows its parameters:

   | Column | Content |
   |---|---|
   | **Name** | Parameter name |
   | **Expression** | Stored expression, for example `25.4 mm` |
   | **Unit** | Unit |
   | **Comment** | Comment, if any |

4. Select **OK**. The set document is derived into the design at the start of the timeline; the timeline marker is then returned to the end. Parameters new to the design are marked as favorites.

The set document is opened briefly in the background for the derive and closed again; focus returns to your design.

## Preferences

Shares one checkbox with Global Parameters under **File › PowerTools Preferences › Assembly**. Changes apply after a Fusion restart.

## Limitations

- The **Parameter Set** list comes from a fresh scan of the hub each time the dialog opens; the preview comes from a sidecar file written by Global Parameters and does not reflect edits made to the set document outside the add-in.
- With no sets in the project the dialog says so and suggests creating one with Global Parameters.
- If the `_Global Parameters` folder has been deleted and recreated, run [Refresh Global Parameters Cache](./Refresh%20Global%20Parameters%20Cache.md) so the folder is found again.

> **Developers:** see the [architecture notes](./arch/Link%20Global%20Parameters.md).

---

[Back to README](../README.md)

*Copyright © 2026 IMA LLC. All rights reserved.*
