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

Both sets are editable in **PowerTools Preferences → Add Project Folders**. The lists below are what a fresh install starts with; once you edit a set, your version is kept and is not overwritten by later updates.

### Basic

| Folder name |
|---|
| _Global Parameters |
| Drawings |
| Archive |
| Obit |
| Wiki |

### Advanced

| Folder name |
|---|
| 01 - Assemblies |
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

- A Fusion project must be active in the Data Panel (a document does not need to be open). If no project is in context, the command reports *No active project* and asks you to select one in the Data Panel, rather than failing silently.
- The add-in must have write access to the active project.

## Notes

- Existing folders are matched case-insensitively and skipped.
- The preview marks existing folders as `(exists)` before execution.
- The command is safe to run repeatedly on the same project.

## Access

Select **PowerTools Add Project Folders** from the **File** dropdown on the **Quick Access Toolbar (QAT)**.

UI label note: the command is documented as **Add Default Project Folders** and appears in Fusion as **PowerTools Add Project Folders**.

> **Developers:** see the [architecture notes](./arch/Default%20Folders.md).

[Back to README](../README.md)

*Copyright © 2026 IMA LLC. All rights reserved.*
