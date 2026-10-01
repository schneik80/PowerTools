# PowerTools for Autodesk Fusion

PowerTools is a single Autodesk Fusion add-in that puts the missing everyday commands back into Fusion, for people who run distributed assemblies, manage team data in Fusion Team, and want the batch, numbering, export and sharing tools that desktop CAD and PDM systems take for granted. One install adds 52 commands to the places you already work (the Design toolbar, the Quick Access Toolbar, the File and Share menus, the Drawing and Animation workspaces), each switchable from one Preferences page.

- **Assemblies**: plan a hierarchy on a canvas and generate the components, externalize local components, infer constraints on an imported STEP, update a distributed design bottom-up.
- **Team data**: hub-unique part and drawing numbers, shared global parameters, where-used and version history views, one-click refresh and close-all.
- **Modeling**: repair and round sketches, flatten doubly-curved faces with a strain map, measure a chain of edges, mirror a part into an opposite-hand document, see which features cost compute time.
- **Exports and sharing**: BOM, Mermaid and SysML exports from the File menu; share, desktop and Fusion Team links from the Share menu.

## Contents

- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Preferences](#preferences)
- [Commands](#commands)
- [Dev-Notes](#dev-notes)
- [Support](#support)
- [License](#license)

## Prerequisites

- **Autodesk Fusion** on **Windows** or **macOS**, with add-ins enabled.
- A **Fusion Team hub** for the commands that read or write cloud data (references, numbering, related data, team add-ins, sharing).
- The **Fusion Manage Extension** for Sync Item to Part Number only.

## Installation

1. Download or clone this repository.
2. In Fusion, open **Utilities › Add-Ins** (or press **Shift+S**).
3. On the **Add-Ins** tab, select the green **+**.
4. Select the `PowerTools` folder and select **Open**.
5. Select **PowerTools** in the list and select **Run**. Tick **Run on Startup** to load it with Fusion.

## Preferences

**File › PowerTools Preferences** on the Quick Access Toolbar opens a palette with one section per command group: an enable checkbox, summary and guide link per command, and settings beneath the commands that have them. Enabling or disabling a command applies on the next Fusion restart; settings apply immediately. **Open settings file** and **Import settings…** back up or restore every choice.

- **Off by default**: Component Warning, Show In Location, Get and Update, Radial Hole Circle, Version Diff.
- **Beta**, hidden until **Show beta commands** is ticked under **General**: Infer Constraints, Radial Hole Circle, Flatten Surface.
- The **Related Data** section sets up the templates folder; the **Team Add-ins** section shows the shared add-ins folder and its settings.

---

## Commands

Most commands live on the **Utilities** tab of the Design workspace, in the **Power Tools** panel. The **Location** column gives the others. Select a command for its guide.

### Assembly

| Command | Location | Description |
| --- | --- | --- |
| [Assembly Builder](./docs/Assembly%20Builder.md) | Design › Utilities › Power Tools | Design an assembly hierarchy in a visual node editor, then generate every external component with the right design intent in one step. Imports a SysML v2 physical view. |
| [Assembly Palette](./docs/Assembly%20Palette.md) | Design › Assembly › Insert | Quick-start palette for a new assembly: create components in place, insert from thumbnails of open and recent documents, hand off to Assembly Builder, Global Parameters and Fasteners. |
| [Insert STEP File](./docs/Insert%20Step.md) | Design › Assembly › Insert | Insert a STEP file from disk as a component of the active design, with no upload first. |
| [Assembly Statistics](./docs/Assembly%20Statistics.md) | Design › Utilities › Power Tools | Component counts, nesting depth and joint counts for the active design. |
| [Get and Update](./docs/Get%20and%20Update.md) | Quick Access Toolbar | Get all latest versions and update all assembly contexts in one click. Off by default. |
| [Bottom-up Update](./docs/Bottom-Up%20Update.md) | Design › Utilities › Power Tools | Open, update, rebuild and save every referenced document from the leaves up, with a resumable log. |
| [Externalize](./docs/Externalize.md) | Design › Utilities › Power Tools | Save local components as their own cloud documents and re-insert them in place. Converts an imported assembly into a distributed design. |
| [Global Parameters](./docs/Global%20Parameters.md) | Design › Utilities › Power Tools | Create and edit parameter sets shared across a project. |
| [Link Global Parameters](./docs/Link%20Global%20Parameters.md) | Design › Utilities › Power Tools | Derive a shared parameter set into the active design. |
| [Refresh Global Parameters Cache](./docs/Refresh%20Global%20Parameters%20Cache.md) | Design › Utilities › Power Tools | Rescan the project's `_Global Parameters` folder and rewrite the local cache. |
| [Infer Constraints](./docs/Infer%20Constraints.md) | Design › Utilities › Power Tools | Propose concentric and coincident constraints for an already-positioned assembly and apply the ones you pick. Beta. |
| [Component Warning](./docs/Component%20Warning.md) | PowerTools Preferences (background) | Warn before a feature is created in the root component or against another component. Off by default. |
| [Change Cycle Color](./docs/Change%20Cycle%20Color.md) | Right-click menu | Choose the color Component Color Cycling uses for the selected components, instead of the next random one. |
| [Document References](./docs/Document%20References.md) | Design › Utilities › Power Tools | Where-used for the active design: root assemblies, parents, children, drawings, fasteners and [related data](./docs/Related%20Data.md). |
| [Refresh Active Document](./docs/Document%20Refresh.md) | File | Check the hub for a newer version of the open document and reload it. |

### Document Tools

| Command | Location | Description |
| --- | --- | --- |
| [Document Information](./docs/Document%20Information.md) | Design › Utilities › Power Tools; Drawing › Power Tools | Hub, project, folder, version and MFGDM identifiers of the active design or drawing, with a warning when saving would migrate it to a newer Fusion build. |
| [History](./docs/Document%20History.md) | Quick Access Toolbar | The document's version history as day rows: a track per author, saves on a clock axis, elapsed time between days. |
| [Version Diff](./docs/Version%20Diff.md) | Design › Utilities › Power Tools | Compare the timeline of two versions of the active design in an HTML report. Off by default. |
| [Assign Part Numbers](./docs/Assign%20Part%20Numbers.md) | Design › Utilities › Power Tools | Hub-unique sequential part numbers (PRT, ASY, WLD, COT, TOL) for the design and its local components. |
| [Assign Drawing Number](./docs/Assign%20Drawing%20Number.md) | Drawing › Power Tools | Hub-unique DWG numbers for drawings, synced into the source design's Drawing Number property. |
| [Sync Item to Part Number](./docs/Sync%20Item%20to%20Part%20Number.md) | Design › Manage › Power Tools | Copy the Fusion Manage Item Number into the Part Number (Manage Extension). |
| [PowerTools Add Project Folders](./docs/Default%20Folders.md) | File | Create a standard folder set in the active project, from editable Basic and Advanced lists. |
| [Favorites](./docs/Favorites.md) | Quick Access Toolbar | Save folder locations per hub and jump the Data Panel to any of them. |
| [Open Recent](./docs/Open%20Recent.md) | File › Open Recent | Reopen a recent document from the File menu, with location and thumbnail on hover. |
| [Match Units](./docs/Match%20Units.md) | Design › Inspect | Compare the document's units with your Fusion defaults and change them in one click; the icon shows the state. Optional prompts on open and on entering Manufacture. |
| [Show In Location](./docs/Show%20In%20Location.md) | PowerTools Preferences (background) | Reveal the document's folder in the Data Panel when a document opens or is activated. Off by default. |
| [Close All Documents](./docs/Close%20All%20Documents.md) | File | Close every open document, saving or discarding unsaved changes as a group. |
| [Toggle Data](./docs/Toggle%20Data%20Pane.md) | Navigation Toolbar | Open or close the Data Panel with one click. |
| [Local Recovery Save](./docs/Recovery%20Save.md) | File | Write a local recovery checkpoint without creating a cloud version. |

### Exports

| Command | Location | Description |
| --- | --- | --- |
| [Export BOM as CSV](./docs/Export%20BOM.md) | File | Flat bill of materials of the assembly as CSV, without making a drawing. |
| [Export Mermaid Diagram](./docs/Export%20Mermaid.md) | File | The assembly hierarchy as a Mermaid flowchart file, opened in Mermaid Live. |
| [Export SysML Architecture Document](./docs/Export%20SysML.md) | File | The assembly as a 4+1 architecture document with a SysML v2 physical view. |

### Part Modeling

| Command | Location | Description |
| --- | --- | --- |
| [Round Sketch Dimensions](./docs/Round%20Sketch%20Dimensions.md) | Sketch › Modify | Round the sketch's length and angle dimensions to a chosen increment, with live preview. |
| [Sketch Under-constrained](./docs/SketchUnder.md) | Sketch › Modify | Highlight the sketch objects that are not fully constrained. |
| [Radial Hole Circle](./docs/RadialHoleCircle.md) | Sketch › Create | A construction circle on a picked centre with a diameter dimension and a point at twelve o'clock. Beta, off by default. |
| [Create Mirrored Design](./docs/MirrorDerive.md) | Design › Solid › Create | Derive the design into a new `-mirror` document and scale it by −1: an opposite-hand part that follows the source. |
| [Hide Objects](./docs/HideObjects.md) | Design › Utilities › Utility | Hide origins, construction geometry, joints, sketches and canvases in every component at once. |
| [Timeline Compute Report](./docs/Timeline%20Compute%20Times.md) | Design › Solid › Inspect | Compute time per timeline feature in an HTML report, with the source CSV. |
| [Measure Path](./docs/Measure%20Path.md) | Design › Inspect | Total length of a connected chain of edges and sketch curves between two picks. |
| [Flatten Surface](./docs/Flatten%20Surface.md) | Design › Utilities › Power Tools | Flatten curved faces to a sketch pattern with a stretch/gather strain map. Beta. |

### Animation

| Command | Location | Description |
| --- | --- | --- |
| [Save Named View](./docs/Animation%20Named%20View.md) | Animation › Power Tools | Save the Animation viewport camera as a named view on the design, named from the storyboard. |

### Related Data

| Command | Location | Description |
| --- | --- | --- |
| [Create Related Data](./docs/Related%20Data.md) | Design › Solid › Create | Create a Manufacture, Render or other document from a hub template, referencing the active design. |
| [Select Related Data Folder](./docs/Select%20Related%20Data%20Folder.md) | PowerTools Preferences › Related Data | Choose the hub folder that holds the related-data templates, once per hub. |

### Team Add-ins

Share add-ins across a team through one hub folder, `Assets / Shared Addins`. Drop an add-in `.zip` in; everyone else picks it up shortly after Fusion starts, with no restart and nothing to publish.

| Command | Location | Description |
| --- | --- | --- |
| [Team Add-ins](./docs/Team%20Add-ins.md) | Design › Utilities › Power Tools | Check the shared folder now and show what the last check did. |
| [Set Up Shared Add-ins Folder](./docs/Set%20Up%20Shared%20Add-ins%20Folder.md) | PowerTools Preferences › Team Add-ins | Find or create the shared folder in the hub's Assets project. |

### Tools

| Command | Location | Description |
| --- | --- | --- |
| [Scripts and Add-ins](./docs/Scripts%20and%20Add-ins.md) | File | Open Fusion's Scripts and Add-Ins manager from the File menu, which works with no document open. |

### Share

| Command | Location | Description |
| --- | --- | --- |
| [Get a Share Link](./docs/Get%20a%20Share%20Link.md) | Share Menu | Turn on sharing and copy the public link, with the share state reported. |
| [Change Share Settings](./docs/Change%20Share%20Settings.md) | Share Menu | Open Fusion's share settings: download allowed, password. |
| [Get Open on Desktop Link](./docs/Get%20Open%20on%20Desktop%20Link.md) | Share Menu | Copy a link that opens the document in a teammate's Fusion. |
| [Get Open in Team Link](./docs/Get%20Open%20in%20Team%20Link.md) | Share Menu | Copy a link that opens the document in the Fusion Team web client. |
| [Invite to Project](./docs/Invite%20to%20Project.md) | Share Menu | Open the project's Invite Members page in your browser. |
| [Document Project Members](./docs/Document%20Project%20Members.md) | Share Menu | Open the project's Members page in your browser. |

---

## Dev-Notes

Developer documentation, system context, C4 diagrams, the add-in lifecycle and the command-module pattern, is in **[docs/arch/architecture.md](./docs/arch/architecture.md)**. Setup, tooling and debugging are in the **[developer guide](./docs/dev/index.md)**. The user-documentation style guide is **[docs/dev/docs-style.md](./docs/dev/docs-style.md)**.

AI coding agents start at **[AGENTS.md](./AGENTS.md)**, which links the [codebase map](./docs/dev/codebase-map.md) and the [lessons ledger](./docs/dev/lessons.md).

## Support

This add-in is developed and maintained by IMA LLC.

## License

Copyright (C) Industrial Machine Arts LLC WA, USA — All Rights Reserved.

This software is proprietary and confidential. It is protected under international copyright law; all rights are reserved by the copyright holders. It is only available to authorized individuals with the permission of the copyright holders. See [LICENSE](LICENSE) for the full notice.

The three Autodesk-sample-derived modules in `lib/ptAddInUtils`, `general_utils.py`, `event_utils.py` and `attributes_utils.py`, remain under Autodesk, Inc.'s original, permissive license terms (see each file's header), which require that their copyright notice be retained in all copies. The proprietary terms above do not apply to those Autodesk-derived portions.

*Copyright © Industrial Machine Arts LLC WA, USA. All rights reserved.*
