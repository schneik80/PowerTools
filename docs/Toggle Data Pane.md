# Toggle Data Pane

[Back to README](../README.md)

## Overview

The **Toggle Data Pane** command adds a button to the Fusion Navigation Toolbar that opens or closes the Data Pane with a single click. By default, toggling the Data Pane requires navigating a nested menu or using a keyboard shortcut that many users are unaware of. This command surfaces that action directly on the Navigation Toolbar for fast, discoverable access.

## Capabilities

| Capability | Details |
|---|---|
| Open the Data Pane | Shows the Data Pane if it is currently hidden |
| Close the Data Pane | Hides the Data Pane if it is currently visible |
| Single-click toggle | Automatically detects the current state and takes the correct action |
| Persistent toolbar button | Button is always visible in the Navigation Toolbar while the add-in is active |

## Prerequisites

- A Fusion document must be open.
- The PowerTools add-in must be active.

## Notes

- The command uses the current `app.data.isDataPanelVisible` state to decide whether to open or close the Data Pane.
- The toolbar button is available while the add-in is running.

## Access

Select **Toggle Data** on the **Navigation Toolbar** at the bottom of the Fusion canvas.

![access](./assets/toggledata.png)

## Architecture

The Toggle Data Pane command registers a button control on the Fusion Navigation Toolbar. On execution, it reads the current state of the Data Pane from the Fusion Application object and dispatches to either the built-in `DashboardModeOpenCommand` or `DashboardModeCloseCommand` accordingly.

### Command ID

`NavBarBtn`

### Execution flow

1. The add-in registers the command definition with a custom icon and inserts a button control on the Navigation Toolbar.
2. The user clicks the **Toggle Data** button.
3. The `command_created` handler checks `app.data.isDataPanelVisible`.
4. If `True`, the handler executes `DashboardModeCloseCommand` to hide the Data Pane.
5. If `False`, the handler executes `DashboardModeOpenCommand` to show the Data Pane.

### Component diagram

```mermaid
C4Component
    title Toggle Data Pane – Component Architecture

    Person(user, "Designer", "Fusion user working on a design")
    Component(addin, "PowerTools Add-In", "Python, Fusion API", "Hosts and registers all PowerTools commands")
    Component(cmd, "Toggle Data Pane", "datatoggle/entry.py", "Registers Navigation Toolbar button and reads panel state")
    Component(openCmd, "DashboardModeOpenCommand", "Fusion Internal API", "Opens the Data Pane")
    Component(closeCmd, "DashboardModeCloseCommand", "Fusion Internal API", "Closes the Data Pane")
    Component(appData, "app.data", "Fusion Application API", "Exposes isDataPanelVisible state")

    Rel(user, addin, "Loads add-in on Fusion start")
    Rel(addin, cmd, "Calls start() – registers button on Navigation Toolbar")
    Rel(user, cmd, "Clicks Toggle Data on Navigation Toolbar")
    Rel(cmd, appData, "Reads isDataPanelVisible")
    Rel(cmd, openCmd, "Executes if panel is hidden")
    Rel(cmd, closeCmd, "Executes if panel is visible")
```

---

[Back to README](../README.md)

*Copyright © 2026 IMA LLC. All rights reserved.*