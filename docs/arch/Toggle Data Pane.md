# Toggle Data Pane — Architecture

[← Toggle Data Pane guide](../Toggle%20Data%20Pane.md)

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
