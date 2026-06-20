# Local Recovery Save — Architecture

[← Local Recovery Save guide](../Recovery%20Save.md)

## Architecture

The Local Recovery Save command is a thin wrapper around Fusion's built-in `AutoSaveFilesCommand`. It registers a button control in the QAT File dropdown during add-in startup and delegates execution directly to the internal Fusion command on click.

### Command ID

`PTND-autoSave`

### Execution flow

1. The add-in registers the command definition and inserts a button after the **Save as Latest** control in the QAT File dropdown.
2. The user selects **Local Recovery Save**.
3. The `command_execute` handler retrieves the internal `AutoSaveFilesCommand` command definition from the Fusion UI.
4. `AutoSaveFilesCommand` is executed, writing the local recovery checkpoint.

### Component diagram

```mermaid
C4Component
    title Local Recovery Save – Component Architecture

    Person(user, "Designer", "Fusion user working on a design")
    Component(addin, "PowerTools Add-In", "Python, Fusion API", "Hosts and registers all PowerTools commands")
    Component(cmd, "Local Recovery Save", "autosave/entry.py", "Registers QAT button control and delegates to Fusion on execute")
    Component(fusion, "AutoSaveFilesCommand", "Fusion Internal API", "Writes local recovery checkpoint to disk")

    Rel(user, addin, "Loads add-in on Fusion start")
    Rel(addin, cmd, "Calls start() – registers button in QAT File dropdown")
    Rel(user, cmd, "Clicks Local Recovery Save in QAT File menu")
    Rel(cmd, fusion, "Executes AutoSaveFilesCommand")
```
