# PowerTools for Autodesk Fusion

PowerTools is an Autodesk Fusion add-in that consolidates the full suite of IMA LLC productivity commands — assembly management, document and data tools, part-modeling helpers, exports, related-data templates, and document sharing — into a single installable add-in. It adds commands to the Design workspace toolbar, the Quick Access Toolbar (QAT), and the Drawing workspace that reduce the steps required for common design, data, and collaboration tasks.

This add-in replaces the previously separate PowerTools add-ins (Assembly, Document Tools, Exports, Part Modeling, Related Data, and Share Document). Installing PowerTools gives you every command at once; there is nothing to install piecemeal.

## Contents

- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Commands](#commands)
- [Architecture](#architecture)
- [Support](#support)
- [License](#license)

## Prerequisites

Before you install and run this add-in, confirm that you have the following:

- **Autodesk Fusion** (any current subscription tier) with Python add-in support enabled
- **Windows 10/11** or **macOS**
- An **Autodesk Team Hub** (required for commands that access cloud document references, related data, and sharing)

## Installation

1. Download or clone this repository to your local machine.
2. In Autodesk Fusion, open the **Add-Ins** dialog by selecting **Utilities** > **Add-Ins**, or press **Shift+S**.
3. On the **Add-Ins** tab, click the green **+** icon.
4. Navigate to the folder where you placed the add-in files and select the `PowerTools` folder.
5. Click **Open**.
6. Select **PowerTools** in the list, then click **Run**.

To have the add-in load automatically each time Fusion starts, select **Run on Startup** before clicking **Run**.

## Commands

Most commands appear in **Design › Tools › Power Tools**. Some appear in other locations as noted below. Click a command for its detailed guide.

### Assembly

| Command | Location | Description |
| --- | --- | --- |
| [Assembly Builder](./docs/Assembly%20Builder.md) | Design › Tools › Power Tools | Build and manage multi-component assemblies from a guided palette. |
| [New Assembly](./docs/New%20Assembly.md) | Design › Solid | Start a new assembly with the assembly-intent workflow. |
| [Insert Step](./docs/Insert%20Step.md) | Design › Solid | Insert a STEP file as a referenced component. |
| [Assembly Statistics](./docs/Assembly%20Statistics.md) | Design › Tools › Power Tools | Report component, occurrence, and reference counts for the active design. |
| [Get and Update](./docs/Get%20and%20Update.md) | Design › Tools › Power Tools | Fetch and update referenced documents in one step. |
| [Bottom-Up Update](./docs/Bottom-Up%20Update.md) | Design › Tools › Power Tools | Propagate changes from sub-components up through the assembly. |
| [Externalize](./docs/Externalize.md) | Design › Tools › Power Tools | Externalize internal components into managed documents. |
| [Global Parameters](./docs/Global%20Parameters.md) | Design › Tools › Power Tools | View and manage project-wide global parameters. |
| [Link Global Parameters](./docs/Link%20Global%20Parameters.md) | Design › Tools › Power Tools | Link the active design to shared global parameters. |
| [Refresh Global Parameters Cache](./docs/Refresh%20Global%20Parameters%20Cache.md) | File › PowerTools Settings | Rebuild the cached global-parameters folder and document index. |
| [Infer Constraints](./docs/Infer%20Constraints.md) | Design › Tools › Power Tools | Infer assembly joints/constraints from component geometry. |
| [Component Warning](./docs/Component%20Warning.md) | File › PowerTools Settings | Toggle warnings about component edits that affect references. |
| [Change Cycle Color](./docs/Change%20Cycle%20Color.md) | Design › Right-click menu | Set the per-component color used by Fusion's Color Cycling Toggle on selected components. |
| [Reference Manager](./docs/Reference%20Manager.md) | Design › Tools › Power Tools | Inspect and manage all external references of the active design. |
| [Document References](./docs/Document%20References.md) | Design › Tools › Power Tools | List all documents related to the active design. |
| [Document Refresh](./docs/Document%20Refresh.md) | Design › Tools › Power Tools | Refresh out-of-date references in the active design. |

### Document Tools

| Command | Location | Description |
| --- | --- | --- |
| [Document Information](./docs/Document%20Information.md) | Design › Tools › Power Tools | Display cloud data identifiers and metadata for the active document. |
| [Document History](./docs/Document%20History.md) | Design › Tools › Power Tools | Show the version history of the active document. |
| [Version Diff](./docs/Version%20Diff.md) | Design › Tools › Power Tools | Compare versions of the active document. |
| [Assign Part Numbers](./docs/Assign%20Part%20Numbers.md) | Design › Tools › Power Tools | Assign part numbers across the active design. |
| [Assign Drawing Number](./docs/Assign%20Drawing%20Number.md) | Drawing › Power Tools | Assign a drawing number inside the Drawing workspace. |
| [Sync Item to Part Number](./docs/Sync%20Item%20to%20Part%20Number.md) | Design › Manage › Power Tools | Copy the Fusion Manage Item Number into the Part Number (Manage Extension). |
| [Default Folders](./docs/Default%20Folders.md) | Design › Tools › Power Tools | Configure default project folders. |
| [Favorites](./docs/Favorites.md) | Design › Tools › Power Tools | Manage favorite documents and folders. |
| [Open Recent](./docs/Open%20Recent.md) | File › Open Recent | Reopen a recently used document from a File-menu flyout, with location and thumbnail tooltips. |
| [Show In Location](./docs/Show%20In%20Location.md) | File › PowerTools Settings | Open the active document's location in the data panel. |
| [Close All Documents](./docs/Close%20All%20Documents.md) | File | Close every open document, saving or discarding unsaved changes as a group. |
| [Toggle Data Pane](./docs/Toggle%20Data%20Pane.md) | Navigation bar | Toggle the visibility of the data panel. |
| [Recovery Save](./docs/Recovery%20Save.md) | Design › Tools › Power Tools | Periodic recovery autosave for the active document. |

### Exports

| Command | Location | Description |
| --- | --- | --- |
| [Export BOM](./docs/Export%20BOM.md) | Design › Tools › Power Tools | Export the bill of materials to CSV. |
| [Export Mermaid](./docs/Export%20Mermaid.md) | Design › Tools › Power Tools | Export the assembly structure as a Mermaid diagram. |

### Part Modeling

| Command | Location | Description |
| --- | --- | --- |
| [Sketch Repair](./docs/SketchFix.md) | Sketch › Modify | Repair common sketch profile issues automatically. |
| [Round Sketch Dimensions](./docs/Round%20Sketch%20Dimensions.md) | Sketch › Modify | Round the active sketch's dimensions to an adjustable increment, with a live preview. |
| [Under-Constrained Sketch](./docs/SketchUnder.md) | Sketch | Highlight under-constrained sketch geometry. |
| [Radial Hole Circle](./docs/RadialHoleCircle.md) | Sketch | Add center points for a radial pattern of holes. |
| [Mirror Derive](./docs/MirrorDerive.md) | Design › Solid | Create a mirrored derived component. |
| [Hide Objects](./docs/HideObjects.md) | Design › Tools | Quickly hide selected objects. |
| [Timeline Compute Times](./docs/Timeline%20Compute%20Times.md) | Design › Solid | Measure per-feature timeline compute times. |

### Animation

| Command | Location | Description |
| --- | --- | --- |
| [Save Named View](./docs/Animation%20Named%20View.md) | Animation › Power Tools | Save the Animation viewport camera as a named view on the design, named from the active storyboard. Panel sits after **View**, before **Publish**. |

### Related Data

| Command | Location | Description |
| --- | --- | --- |
| [Create Related Data](./docs/Related%20Data.md) | Design › Solid | Create related documents from configured templates. |
| [Select Related Data Folder](./docs/Select%20Related%20Data%20Folder.md) | File › PowerTools Settings | Configure the hub/project/folder used for related data. |

### Tools

| Command | Location | Description |
| --- | --- | --- |
| [Scripts and Add-ins](./docs/Scripts%20and%20Add-ins.md) | QAT › File menu | Open Fusion's built-in Scripts and Add-Ins manager from the File menu, above PowerTools Preferences. |

### Share

All sharing commands appear in the **Share Menu** flyout on the right-hand Quick Access Toolbar.

| Command | Location | Description |
| --- | --- | --- |
| [Get a Share Link](./docs/Get%20a%20Share%20Link.md) | QAT › Share Menu | Create or copy a public share link for the active document. |
| [Change Share Settings](./docs/Change%20Share%20Settings.md) | QAT › Share Menu | Manage download and password protection for the share link. |
| [Get Open on Desktop Link](./docs/Get%20Open%20on%20Desktop%20Link.md) | QAT › Share Menu | Get a link that opens the document in the Fusion desktop app. |
| [Get Open in Team Link](./docs/Get%20Open%20in%20Team%20Link.md) | QAT › Share Menu | Get a link that opens the document in Autodesk Fusion Team. |
| [Invite to Project](./docs/Invite%20to%20Project.md) | QAT › Share Menu | Invite a collaborator to the active project. |
| [Document Project Members](./docs/Document%20Project%20Members.md) | QAT › Share Menu | List the members of the active project. |

## Architecture

PowerTools is a standard Fusion Python add-in: `PowerTools.py` starts and stops the add-in, `commands/__init__.py` registers every command, and a single startup bootstrap creates the shared UI access points (the **Power Tools** panel and the **PowerTools Settings** QAT flyout) exactly once. All commands share the vendored utility library `lib/ptAddInUtils` and a merged `config.py`.

For developer-oriented documentation — system context, C4 diagrams, the add-in lifecycle, the shared-access-point model, and the command-module pattern — see **[docs/arch/architecture.md](./docs/arch/architecture.md)**.

For local development setup, tooling, and how to debug the add-in in VS Code or Zed, see the **[developer guide](./docs/dev/index.md)**.

## Support

This add-in is developed and maintained by IMA LLC.

---

## License

Copyright (C) Industrial Machine Arts LLC WA, USA — All Rights Reserved.

This software is proprietary and confidential. It is protected under international copyright law; all rights are reserved by the copyright holders. It is only available to authorized individuals with the permission of the copyright holders. See [LICENSE](LICENSE) for the full notice.

The three Autodesk-sample-derived modules in `lib/ptAddInUtils` — `general_utils.py`, `event_utils.py`, and `attributes_utils.py` — remain under Autodesk, Inc.'s original, permissive license terms (see each file's header), which require that their copyright notice be retained in all copies. The proprietary terms above do not apply to those Autodesk-derived portions.

---

*Copyright © Industrial Machine Arts LLC WA, USA. All rights reserved.*
