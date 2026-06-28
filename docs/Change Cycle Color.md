# Change Cycle Color

[Back to README](../README.md)

The Change Cycle Color command sets the per-component color used by Autodesk Fusion's **View ▸ Color Cycling Toggle**. It writes the `Component.componentColor` property on every selected Component or Occurrence — the value Fusion reads when it assigns distinguishing colors to components in a design. Use it to override the default cycling color for any component without touching its **Appearance**, material, or model geometry.

The command is **context-menu only**: right-click a Component or Occurrence and the **Change Cycle Color** entry appears in the marking menu, immediately after Fusion's built-in **Cycle Component Color**. There is no Power Tools panel button.

## What you can do

- Set a specific cycle color on any Component or Occurrence selected in the browser or picked on the canvas — including the root component.
- Choose from a rainbow palette of swatches sourced live from Fusion's built-in `ColorCycleTable`.
- Pick a fully custom color with the OS-native color picker.
- Apply the same color to several Components or Occurrences at once when more than one is selected.
- Hide the command from the right-click marking menu from **PowerTools Preferences** when you do not need it.

## Prerequisites

- An Autodesk Fusion 3D Design must be open.
- At least one Component or Occurrence must be selected before right-clicking — a browser node, or a component picked on the canvas (the root component is allowed).

## How to use Change Cycle Color

1. In the browser or on the canvas, select one or more Components or Occurrences.
2. Right-click the selection to open the marking menu, then click **Change Cycle Color**. The entry appears immediately after Fusion's built-in **Cycle Component Color** command.
3. In the dialog, click a swatch from the rainbow palette to select a color. The **Selected** preview updates to show the color and its name. Alternatively, click **Custom color…** to open the OS-native color picker and choose any color.
4. Click **Apply** to write the chosen color to `componentColor` for every selected component. (Picking a custom color applies it immediately and closes the dialog.)
5. To render the assigned colors in the viewport, enable **View ▸ Color Cycling Toggle** in Fusion. The assignment is stored on the component, so cycling can be toggled on and off without losing it.

## Notes

- **Multi-select:** When several Components or Occurrences are selected, the chosen color is applied to all of them in one step. If the selection contains multiple occurrences of the same underlying component definition, duplicates are collapsed so each component's `componentColor` is written only once.
- **Palette source:** The swatches are drawn from Fusion's built-in `ColorCycleTable`, defined in `RiverRubicon.xml` inside the Fusion installation. They are sorted by hue into a rainbow grid; the very pale neutrals fall to the end. Swatch icons are generated on first use and cached for the session. The `RiverRubicon.xml` file is located dynamically by walking up from the running Fusion install, so it tracks Fusion `webdeploy` updates automatically. If it cannot be found, the dialog still offers **Custom color…**.
- **Custom color on macOS:** On macOS the native color picker is invoked through `/usr/bin/osascript` (`choose color`), which uses the system color panel. On Windows and other platforms it runs `tkinter.colorchooser` in a separate process. Either way the picked color is applied as soon as you confirm the picker.
- **Session state:** The last-used color is remembered while Fusion is open, but it is not written to disk and does not persist across restarts.
- **Preferences:** In **PowerTools Preferences → Assembly → Change Cycle Color**, the **Show in the right-click context menu** toggle (default ON) controls whether the command appears in the marking menu. The change takes effect on the very next right-click — no Fusion restart is required. As with every command, Change Cycle Color can also be enabled or disabled entirely from the **Commands** section of PowerTools Preferences.

## Access

Right-click a Component or Occurrence in the browser or on the canvas, then choose **Change Cycle Color** from the marking menu (after the built-in **Cycle Component Color**). There is no Power Tools panel button for this command.

> **Developers:** see the [architecture notes](./arch/Change%20Cycle%20Color.md).

---

[Back to README](../README.md)

---

*Copyright © 2026 IMA LLC. All rights reserved.*
