# Insert STEP File — Architecture
[← Insert STEP File guide](../Insert%20Step.md)

## Architecture

The following diagram shows how the Insert STEP File command interacts with Autodesk Fusion.

```mermaid
C4Context
  title Insert STEP File – System Context

  Person(user, "Design Engineer", "Autodesk Fusion user inserting a local STEP model")
  System(addin, "PowerTools Assembly", "Autodesk Fusion add-in")
  System_Ext(fusion, "Autodesk Fusion", "Host application and Python API (adsk.core / adsk.fusion)")
  System_Ext(fs, "Local File System", "Source of STEP or F3D files")

  Rel(user, addin, "Runs Insert STEP File")
  Rel(addin, fusion, "Opens file dialog; executes Fusion.ImportComponent text command")
  Rel(addin, fs, "Reads STEP or F3D file path via OS file dialog")
  Rel(fusion, fs, "Reads and imports file content as inline component")
```

```mermaid
C4Component
  title Insert STEP File – Component View

  Person(user, "Design Engineer")
  Component(cmd, "insertSTEP/entry.py", "PowerTools Command", "Registers button in Assembly and Solid tabs; handles command lifecycle")
  Component(file_dlg, "adsk.core.FileDialog", "Fusion API", "Presents OS file browser filtered to STEP and F3D extensions")
  Component(text_cmd, "Fusion.ImportComponent", "Fusion Text Command", "Imports the selected file as an inline component in the active design")
  System_Ext(fs, "Local File System", "STEP / F3D file source")

  Rel(user, cmd, "Clicks Insert STEP file…")
  Rel(cmd, file_dlg, "Displays file open dialog with STEP/F3D filter")
  Rel(file_dlg, fs, "User selects a file")
  Rel(cmd, text_cmd, "Executes with quoted file path")
```

### User flow

```mermaid
sequenceDiagram
  autonumber
  actor User
  participant Panel as Assembly / Solid panel
  participant Cmd as Insert STEP File
  participant Dlg as adsk.core.FileDialog
  participant FS as Local File System
  participant Text as Fusion.ImportComponent

  User->>Panel: Click Insert STEP file…
  Panel->>Cmd: command_created fires
  Cmd->>Dlg: createFileDialog with STEP filter
  Dlg-->>User: Display OS file browser
  User->>Dlg: Choose .stp / .step / .f3d file
  Dlg-->>Cmd: filename
  Cmd->>Text: executeTextCommand("Fusion.ImportComponent <filename>")
  Text->>FS: Read file content
  FS-->>Text: Geometry data
  Text-->>User: Inserted as inline component at origin
```
