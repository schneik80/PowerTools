# Power Tools — Architecture Documentation

This folder contains developer-oriented architecture documentation for the
consolidated **Power Tools** add-in for Autodesk Fusion — the single add-in
formed by merging the Assembly, Document Tools, Exports, Part Modeling, Related
Data, and Share Document add-ins into one installable unit.

---

## Documents

| Document | Description |
|---|---|
| [Architecture](architecture.md) | System context, component diagram, add-in lifecycle, the shared-access-point model, command registration and execution, the `lib/ptAddInUtils` shared library, and the merged `config.py`. |

Each command also has a focused architecture note describing its command ID,
execution flow, and component diagram (extracted from the end-user guide). The
matching end-user guide lives in [`../`](..).

### Per-command architecture notes

**Assembly**

- [Assembly Builder](Assembly%20Builder.md)
- [Assembly Palette](Assembly%20Palette.md)
- [Insert Step](Insert%20Step.md)
- [Assembly Statistics](Assembly%20Statistics.md)
- [Get and Update](Get%20and%20Update.md)
- [Bottom-Up Update](Bottom-Up%20Update.md)
  - [Bottom-Up Update — Dependency Ordering (DAG)](Bottom-Up%20Update%20Dependency%20Ordering.md)
- [Externalize](Externalize.md)
- [Global Parameters](Global%20Parameters.md)
- [Link Global Parameters](Link%20Global%20Parameters.md)
- [Refresh Global Parameters Cache](Refresh%20Global%20Parameters%20Cache.md)
- [Infer Constraints](Infer%20Constraints.md)
- [Component Warning](Component%20Warning.md)
- [Change Cycle Color](Change%20Cycle%20Color.md)
- [Reference Manager](Reference%20Manager.md)
- [Document References](Document%20References.md)
- [Document Refresh](Document%20Refresh.md)

**Document Tools**

- [Document Information](Document%20Information.md)
- [Document History](Document%20History.md)
- [Version Diff](Version%20Diff.md)
- [Assign Part Numbers](Assign%20Part%20Numbers.md)
- [Assign Drawing Number](Assign%20Drawing%20Number.md)
- [Default Folders](Default%20Folders.md)
- [Favorites](Favorites.md)
- [Open Recent](Open%20Recent.md)
- [Show In Location](Show%20In%20Location.md)
- [Toggle Data Pane](Toggle%20Data%20Pane.md)
- [Recovery Save](Recovery%20Save.md)

**Exports**

- [Export BOM](Export%20BOM.md)
- [Export Mermaid](Export%20Mermaid.md)

**Part Modeling**

- [SketchFix](SketchFix.md)
- [Round Sketch Dimensions](Round%20Sketch%20Dimensions.md)
- [SketchUnder](SketchUnder.md)
- [RadialHoleCircle](RadialHoleCircle.md)
- [MirrorDerive](MirrorDerive.md)
- [HideObjects](HideObjects.md)
- [Timeline Compute Times](Timeline%20Compute%20Times.md)

**Related Data**

- [Related Data](Related%20Data.md)
- [Select Related Data Folder](Select%20Related%20Data%20Folder.md)

**Tools**

- [Scripts and Add-ins](Scripts%20and%20Add-ins.md)

**Share**

- [Get a Share Link](Get%20a%20Share%20Link.md)
- [Change Share Settings](Change%20Share%20Settings.md)
- [Get Open on Desktop Link](Get%20Open%20on%20Desktop%20Link.md)
- [Get Open in Team Link](Get%20Open%20in%20Team%20Link.md)
- [Invite to Project](Invite%20to%20Project.md)
- [Document Project Members](Document%20Project%20Members.md)

---

## Section index

- [System context](architecture.md#system-context) — users and external systems (Fusion, APS / Fusion Team, browser, file system).
- [Component structure](architecture.md#component-structure) — entry point, command registry, bootstrap, command modules, and shared library.
- [Add-in lifecycle](architecture.md#add-in-lifecycle) — `run`/`stop` → bootstrap → command start/stop.
- [Shared UI access points](architecture.md#shared-ui-access-points) — the Power Tools panel and PTSettings flyout, and why the old detect-or-create logic was removed.
- [Command registration](architecture.md#command-registration) and [execution model](architecture.md#command-execution-model).
- [`lib/ptAddInUtils`](architecture.md#shared-utility-library--libptaddinutils) — the shared utility library.
- [`config.py`](architecture.md#configuration-module--configpy) — the merged configuration module.
- [Architecture diagrams](architecture.md#architecture-diagrams) — reference renders in `assets/`.

---

## Related documentation

- For the **developer / contributor guide** — local setup, tooling, and how to
  debug in VS Code and Zed — see [`docs/dev/`](../dev/index.md).
- For **end-user and command documentation**, see the [`docs/`](..) folder.
- For **installation and getting started**, see the project [README](../../README.md).

---

*Copyright © 2026 IMA LLC. All rights reserved.*
