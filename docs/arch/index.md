# Power Tools — Architecture Documentation

Developer-oriented architecture notes for the **Power Tools** add-in for
Autodesk Fusion. Start with [`architecture.md`](architecture.md); every
registered command then has one note here whose filename is the registry's
`doc` entry, the same filename as its user guide in [`../`](..).
`tests/test_command_contract.py` asserts that every registered command has a
note and a row in this index.

---

## Architecture

| Document | Read it for |
|---|---|
| [Architecture](architecture.md) | The entry point and lifecycle, the command-module pattern, the patterns commands share (deferral, palettes, abort, pumped waits, the pure-logic split), the reference for every shared module, UI access points, state on disk |

Section index:

- [System context](architecture.md#system-context) and [Layout](architecture.md#layout)
- [Add-in lifecycle](architecture.md#add-in-lifecycle) — `run`/`stop` → bootstrap → `preferences` → gated registry loop
- [The command module](architecture.md#the-command-module) — `start`/`stop`, the handler table, [acting from `commandCreated` with no inputs](architecture.md#acting-from-commandcreated-when-there-are-no-inputs)
- [Patterns commands share](architecture.md#patterns-commands-share) — [Timer → custom event](architecture.md#deferring-work-to-a-later-main-loop-turn), [palette RPC](architecture.md#palette-to-python-rpc), [abort before the dialog](architecture.md#aborting-a-command-before-its-dialog), [waiting without freezing Fusion](architecture.md#waiting-without-freezing-fusion), [the pure-logic split](architecture.md#the-pure-logic-split)
- [Shared modules](architecture.md#shared-modules) — `command_registry`, `settings_store`, `config`, `commands/__init__`, `_ui_bootstrap`, `_command_abort`, `_inspect_panels`, `partnumber_shared`, and every `lib/ptAddInUtils` module
- [UI access points](architecture.md#ui-access-points) and [State on disk](architecture.md#state-on-disk)

## Per-command notes

Each note follows one template: Purpose, How it is wired (events, handlers,
shared helpers), Data and state, design sections, a diagram where it earns
its place, Tests, and an optional Learnings section at the end.

**Assembly** (`assembly`)

- [Assembly Builder](Assembly%20Builder.md)
- [Insert Step](Insert%20Step.md)
- [Assembly Palette](Assembly%20Palette.md)
- [Assembly Statistics](Assembly%20Statistics.md)
- [Get and Update](Get%20and%20Update.md)
- [Bottom-Up Update](Bottom-Up%20Update.md)
  - [Bottom-Up Update — Dependency Ordering (DAG)](Bottom-Up%20Update%20Dependency%20Ordering.md)
- [Component Warning](Component%20Warning.md)
- [Change Cycle Color](Change%20Cycle%20Color.md)
- [Externalize](Externalize.md)
- [Global Parameters](Global%20Parameters.md)
- [Infer Constraints](Infer%20Constraints.md)
- [Link Global Parameters](Link%20Global%20Parameters.md)
- [Reference Manager](Reference%20Manager.md)
- [Refresh Global Parameters Cache](Refresh%20Global%20Parameters%20Cache.md)
- [Document References](Document%20References.md)
- [Document Refresh](Document%20Refresh.md)

**Document Tools** (`document`)

- [Assign Drawing Number](Assign%20Drawing%20Number.md)
- [Assign Part Numbers](Assign%20Part%20Numbers.md)
- [Sync Item to Part Number](Sync%20Item%20to%20Part%20Number.md)
- [Recovery Save](Recovery%20Save.md)
- [Close All Documents](Close%20All%20Documents.md)
- [Toggle Data Pane](Toggle%20Data%20Pane.md)
- [Default Folders](Default%20Folders.md)
- [Document History](Document%20History.md)
- [Document Information](Document%20Information.md)
- [Show In Location](Show%20In%20Location.md)
- [Favorites](Favorites.md)
- [Match Units](Match%20Units.md)
- [Open Recent](Open%20Recent.md)
- [Version Diff](Version%20Diff.md)

**Exports** (`exports`)

- [Export BOM](Export%20BOM.md)
- [Export Mermaid](Export%20Mermaid.md)
- [Export SysML](Export%20SysML.md)

**Part Modeling** (`partmodeling`)

- [SketchFix](SketchFix.md)
- [Round Sketch Dimensions](Round%20Sketch%20Dimensions.md)
- [SketchUnder](SketchUnder.md)
- [RadialHoleCircle](RadialHoleCircle.md)
- [Timeline Compute Times](Timeline%20Compute%20Times.md)
- [Measure Path](Measure%20Path.md)
- [MirrorDerive](MirrorDerive.md)
- [HideObjects](HideObjects.md)
- [Flatten Surface](Flatten%20Surface.md)

**Animation** (`animation`)

- [Animation Named View](Animation%20Named%20View.md)

**Related Data** (`related`)

- [Select Related Data Folder](Select%20Related%20Data%20Folder.md)
- [Related Data](Related%20Data.md)

**Team Add-ins** (`teamaddins`)

- [Set Up Shared Add-ins Folder](Set%20Up%20Shared%20Add-ins%20Folder.md)
- [Team Add-ins](Team%20Add-ins.md)

**Tools** (`tools`)

- [Scripts and Add-ins](Scripts%20and%20Add-ins.md)

**Share Document** (`share`)

- [Get a Share Link](Get%20a%20Share%20Link.md)
- [Change Share Settings](Change%20Share%20Settings.md)
- [Get Open on Desktop Link](Get%20Open%20on%20Desktop%20Link.md)
- [Get Open in Team Link](Get%20Open%20in%20Team%20Link.md)
- [Invite to Project](Invite%20to%20Project.md)
- [Document Project Members](Document%20Project%20Members.md)

The Preferences command (`commands/preferences/`) is infrastructure rather
than a registered command; it is described in
[Palette to Python RPC](architecture.md#palette-to-python-rpc) and in the
[`.claude/rules/palettes-html.md`](../../.claude/rules/palettes-html.md)
checklist.

---

## Related documentation

- Developer guide (setup, tooling, testing, `.debug`, debugging):
  [`../dev/index.md`](../dev/index.md)
- Where things live: [`../dev/codebase-map.md`](../dev/codebase-map.md)
- The mistakes ledger: [`../dev/lessons.md`](../dev/lessons.md)
- End-user command guides: [`../`](..); installation: the project
  [README](../../README.md)

---

*Copyright © 2026 IMA LLC. All rights reserved.*
