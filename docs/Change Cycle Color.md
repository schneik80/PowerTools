# Change Cycle Color

[Back to README](../README.md)

## Overview

Change Cycle Color sets the per-component color that Fusion's Component Color Cycling uses, for every selected component.

Fusion's **Component Color Cycling** (Shift+N) paints each component a distinguishing color, and its own right-click **Cycle Component Color** re-rolls that color to the next one in the table. You cannot choose. Change Cycle Color sits right after that entry in the marking menu and lets you pick the color, from the swatches of the current lighting environment or from the system color picker, without touching the component's appearance, material or geometry.

## Prerequisites

- A design document must be open.
- One or more components or occurrences must be selected, in the browser or on the canvas. The root component is allowed.

## Where to find it

Right-click a selected component or occurrence and select **Change Cycle Color** from the marking menu, directly after Fusion's **Cycle Component Color**. There is no toolbar button.

## How to use

1. Select the components.
2. Right-click and select **Change Cycle Color**. The dialog's **Targets** box lists what will be changed.
3. Select a swatch from the **Palette** rows; the **Selected** preview shows the color and its name. Or select **Custom color…** to open the system color picker; the picked color is applied at once and the dialog closes.
4. Select **Apply**.
5. To see the colors, turn on **Component Color Cycling**. The assignment is stored on the component, so cycling can be toggled off and on without losing it.

## Options

| Control | Effect |
|---|---|
| **Palette** swatches | The colors of the lighting environment Fusion is currently rendering with, sorted into a rainbow |
| **Custom color…** | The system color picker (the macOS color panel; the standard picker on Windows) |
| **Apply** | Writes the chosen color to every target |

Several occurrences of the same component are collapsed to one write, since the color belongs to the component.

## Preferences

Under **File › PowerTools Preferences › Assembly › Change Cycle Color settings**:

| Setting | Default | Effect |
|---|---|---|
| **Show in the right-click context menu** | On | Untick to hide the entry from the marking menu. Takes effect on the next right-click |

## Limitations

- The swatch palette is read from Fusion's installed lighting environments; if the active environment cannot be determined the River Rubicon palette is used, and if no palette file can be found the dialog offers only **Custom color…**.
- The last-used color is remembered for the session only.
- If some targets could not be written, a warning names them after the dialog closes.

> **Developers:** see the [architecture notes](./arch/Change%20Cycle%20Color.md).

---

[Back to README](../README.md)

*Copyright © 2026 IMA LLC. All rights reserved.*
