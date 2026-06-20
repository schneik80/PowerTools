# Add Default Project Folders

[Back to README](../README.md)

## Overview

The **Add Default Project Folders** command creates a predefined set of folders in the root of the active Fusion project if those folders do not already exist. Running the command on a project that already has some or all of the default folders is safe. Existing folders are detected by a case-insensitive name match and are not duplicated.

This command enforces a consistent folder structure across projects without requiring each team member to create folders manually.

## Capabilities

| Capability | Details |
|---|---|
| Create default project folders | Adds missing folders to the root of the active Fusion project |
| Skip existing folders | Detects existing folders by case-insensitive name comparison and skips them |
| Choose folder set interactively | A **Folder set** dropdown in the command dialog lets the user choose between **Basic** and **Advanced** |
| Live folder preview | The dialog shows a live preview of each folder in the selected set; folders that already exist in the project are marked `(exists)` and will be skipped |
| Idempotent operation | Running the command multiple times on the same project produces no duplicate folders |

## Folder sets

### Basic

| Folder name |
|---|
| Drawings |
| Archive |
| Obit |

### Advanced

| Folder name |
|---|
| 00 - Products |
| 01 - Sub Assemblies |
| 02 - ECAD |
| 03 - Parts |
| 04 - Purchased Parts |
| 05 - 3DPCB Parts |
| 06 - Drawings |
| 07 - Documents |
| 08 - Render |
| 09 - Manufacture |
| 10 - Archive |
| XX - Obit |

## Prerequisites

- A Fusion project must be active (a document does not need to be open).
- The add-in must have write access to the active project.

## Notes

- Existing folders are matched case-insensitively and skipped.
- The preview marks existing folders as `(exists)` before execution.
- The command is safe to run repeatedly on the same project.

## Access

Select **PowerTools Add Project Folders** from the **File** dropdown on the **Quick Access Toolbar (QAT)**.

UI label note: the command is documented as **Add Default Project Folders** and appears in Fusion as **PowerTools Add Project Folders**.

## Architecture

The Add Default Project Folders command registers a button in the QAT File dropdown. On execute, it retrieves the root folder of the active project, reads all existing folder names into a lowercase list, and then iterates through the selected folder set, calling `dataFolders.add()` only for names that are not already present.

### Command ID

`PT-defaultfolders`

### Execution flow

1. The add-in registers the command definition and appends a button to the QAT File dropdown.
2. The user selects **PowerTools Add Project Folders**.
3. A command dialog opens with a **Folder set** dropdown (defaulting to **Basic**) and a read-only **Folders to create** preview.
4. The preview lists every folder in the selected set; folders already present in the project root are shown as `(exists)`.
5. Switching the dropdown immediately refreshes the preview via the `inputChanged` event.
6. The user confirms with **OK**.
7. The `command_execute` handler reads the dropdown selection, retrieves `app.data.activeProject.rootFolder.dataFolders`, and calls `dataFolders.add(name)` only for folder names that are not already present (case-insensitive).

### Component diagram

```mermaid
C4Component
    title Add Default Project Folders – Component Architecture

    Person(user, "Designer", "Fusion user managing a project")
    Component(addin, "PowerTools Add-In", "Python, Fusion API", "Hosts and registers all PowerTools commands")
    Component(cmd, "Default Folders", "defaultfolders/entry.py", "Registers QAT button and manages folder creation logic")
    Component(projectData, "app.data.activeProject", "Fusion Data API", "Provides access to the active project root folder and its child folders")

    Rel(user, addin, "Loads add-in on Fusion start")
    Rel(addin, cmd, "Calls start() – registers button in QAT File dropdown")
    Rel(user, cmd, "Clicks PowerTools Add Project Folders in QAT File menu")
    Rel(cmd, projectData, "Reads rootFolder.dataFolders and calls dataFolders.add() for missing folders")
```

---

[Back to README](../README.md)

*Copyright © 2026 IMA LLC. All rights reserved.*
