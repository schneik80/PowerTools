# New Assembly

[Back to PowerTools Assembly](../README.md)

The New Assembly command opens a docked quick-start palette that helps you populate a brand-new assembly. It appears automatically when you create a new, empty design with **Assembly** design intent, and can also be opened on demand from a toolbar button. From a single panel you can create external Part, Hybrid, or Assembly components in place, hand off to the Assembly Builder or Global Parameters commands, and insert components from a gallery of your currently-open or recently-used documents.

## What you can do

- **Create a component in place** — type a name, pick **Part**, **Hybrid**, or **Assembly** intent, and generate an external component in the active design with `addNewExternalComponent`. The chosen design intent is applied to the new component automatically.
- **Hand off to related commands** — open **Assembly Builder** to design a multi-level hierarchy, or **Global Parameters** to define a shared parameter set, without hunting for them on the toolbar. The palette hides while the handed-off command runs.
- **Insert an open document** — the **Open** tab shows a thumbnail gallery of your currently-open Part/Hybrid/Assembly documents. Click a card to insert that document into the active design as a referenced component (`addByInsert`).
- **Show only what you opened** — by default the Open tab lists only **top-level documents** (the ones you opened directly). Tick **Show referenced children** to also list the sub-assemblies and parts that Fusion loaded as references of an open assembly.
- **Insert a recent document** — the **Recent** tab shows a gallery of recently-touched Part/Hybrid/Assembly documents that are **not** currently open, backed by a small local cache that grows as you work.
- **Thumbnail previews everywhere** — each card renders the component's thumbnail. Thumbnails are cached on disk so the Recent gallery can show them even when the document is closed.
- Palette theme follows the Fusion UI theme — light, dark, or **match OS device theme** — and is correct on first paint.

## Prerequisites

- An Autodesk Fusion 3D Design must be active.
- **Automatic launch** requires the active document to be **new (unsaved)**, **empty** (no timeline features, bodies, sketches, or child components), and to have **Assembly** design intent.
- **Insert from Open / Recent** requires the source document to be **saved** to an Autodesk Hub — `addByInsert` needs a cloud `DataFile`. Unsaved documents are not listed.

## How to use New Assembly

1. In Autodesk Fusion, create a new design with **File > New Design** and confirm the design intent is **Assembly**. The palette opens automatically docked to the right.
   - To open it manually at any time, select **New Assembly** in the **Assembly** tab's **Insert** panel (directly below **Insert STEP File**).
2. **To create a component:** enter a component name, choose **Part**, **Hybrid**, or **Assembly** from the dropdown, and select **New Component**. The external component is created in the active project's root folder and added to the active design.
3. **To insert an open document:** switch to the **Open** tab and click a thumbnail card. The document is inserted as a referenced component at the origin.
   - Tick **Show referenced children** if you also want to see (and insert) the sub-assemblies and parts loaded as references of an open assembly.
4. **To insert a recent document:** switch to the **Recent** tab and click a card. Recently-used documents that are not currently open are listed newest-first.
5. **To design a hierarchy or manage parameters:** select **Assembly Builder…** or **Global Parameters…**. The palette hides and the chosen command opens.

> **Note:** A document you insert during a palette session is removed from both galleries on the next refresh, so a second click cannot silently create a duplicate occurrence. Use the **↻** refresh button to re-scan open and recent documents at any time.

> **Note:** `addNewExternalComponent` requires an Autodesk Hub folder, so the active project's root folder is used as the destination for new components. You can move the generated documents afterward in the Data Panel.

## Access

| Method | Location |
|---|---|
| Automatic | Opens docked to the right when a **new, empty, Assembly-intent** design becomes active. |
| Manual | **Assembly** tab > **Insert** panel > **New Assembly** (below **Insert STEP File**). |

The palette docks to the right edge of the Fusion window. Closing it does not disable the automatic trigger — creating another new empty Assembly design opens it again.

> **Developers:** see the [architecture notes](./arch/New%20Assembly.md).

---

[Back to PowerTools Assembly](../README.md)

---

*Copyright © 2026 IMA LLC. All rights reserved.*
