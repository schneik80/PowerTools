# PowerTools Add Project Folders

[Back to README](../README.md)

## Overview

PowerTools Add Project Folders creates a standard set of folders in the root of the active project, skipping any that already exist.

A new Fusion project is an empty root folder, and every team member fills it differently. Data-management systems such as Vault and SolidWorks PDM solve this with folder templates; Fusion has none. This command gives a project the same structure every time, from one of two folder sets you can edit in **PowerTools Preferences**, and is safe to run again on a project that already has some of the folders.

## Prerequisites

- A document must be open.
- A project must be active in the Data Panel. That project's root is where the folders are created.
- You need write access to the project.

## Where to find it

**File › PowerTools Add Project Folders** on the Quick Access Toolbar. The entry is at the end of the File menu.

## How to use

1. In the Data Panel, open the project you want to set up.
2. Select **File › PowerTools Add Project Folders**.
3. Choose a **Folder set**. The **Folders to create** box previews the result: each folder is listed with `+` if it will be created or `(exists)` if it is already there and will be skipped.
4. Select **OK**. The missing folders are created. There is no completion message; the Data Panel shows the result.

If no project is active, the preview shows every folder as new and **OK** reports *No active project* and asks you to select one in the Data Panel.

## Options

| Option | Default | Effect |
|---|---|---|
| **Folder set** | Basic | Chooses the **Basic** or **Advanced** list below. |
| **Folders to create** | — | Read-only preview of the chosen set with `+` / `(exists)` markers. |

## Folder sets

A fresh install starts with these lists. Existing folders are matched case-insensitively.

| Basic | Advanced |
|---|---|
| `_Global Parameters` | `01 - Assemblies` |
| `Drawings` | `02 - ECAD` |
| `Archive` | `03 - Parts` |
| `Obit` | `04 - Purchased Parts` |
| `Wiki` | `05 - 3DPCB Parts` |
| | `06 - Drawings` |
| | `07 - Documents` |
| | `08 - Render` |
| | `09 - Manufacture` |
| | `10 - Archive` |
| | `XX - Obit` |

`_Global Parameters` is the folder [Global Parameters](./Global%20Parameters.md) uses for shared parameter sets.

## Preferences

Under **File › PowerTools Preferences › Document Tools › Add Project Folders settings** you can edit both lists. Your edited lists are kept across updates; blank lines are ignored.

## Limitations

- Folders are created only at the project root, never nested.
- Nothing is renamed or deleted.

> **Developers:** see the [architecture notes](./arch/Default%20Folders.md).

---

[Back to README](../README.md)

*Copyright © 2026 IMA LLC. All rights reserved.*
