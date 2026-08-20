# Assembly Palette

[Back to PowerTools Assembly](../README.md)

The Assembly Palette command opens a docked quick-start palette that helps you populate a brand-new assembly. It appears automatically when you create a new, empty design with **Assembly** design intent, and can also be opened on demand from a toolbar button. From a single panel you can create external Part, Hybrid, or Assembly components in place, hand off to the Assembly Builder or Global Parameters commands, and insert components from a gallery of your currently-open or recently-used documents.

## What you can do

- **Create a component in place** — type a name, pick **Part**, **Hybrid**, or **Assembly** intent, and generate an external component in the active design with `addNewExternalComponent`. The chosen design intent is applied to the new component automatically.
- **Hand off to related commands** — open **Assembly Builder** to design a multi-level hierarchy, or **Global Parameters** to define a shared parameter set, without hunting for them on the toolbar. The palette hides while the handed-off command runs.
- **Insert an open document** — the **Open** tab shows a thumbnail gallery of your currently-open Part/Hybrid/Assembly documents. Click a card to insert that document into the active design as a referenced component (`addByInsert`).
- **Show only what you opened** — by default the Open tab lists only **top-level documents** (the ones you opened directly). Tick **Show referenced children** to also list the sub-assemblies and parts that Fusion loaded as references of an open assembly.
- **Insert a recent document** — the **Recent** tab shows a gallery of your recently-used Part/Hybrid/Assembly documents, drawn from the recents list Fusion itself keeps for your account. It is populated from the first launch, including documents you opened before installing PowerTools, and it is the same list the [Open Recent](./Open%20Recent.md) File-menu flyout shows. The newest 40 are shown as cards; type in the filter box to reach the rest by name.
- **Insert a fastener** — the **Fasteners ↗** link below the galleries hands off to Fusion's own Fasteners dialog, so bolts and screws come from the Fusion fastener library rather than the document galleries.
- **Thumbnail previews everywhere** — each card shows the document's thumbnail. Cards load their previews as they scroll into view: an open document is rendered locally, and a closed one is fetched from the thumbnail Fusion already stores in the cloud, so the Recent gallery fills in even for documents you have never opened on this machine. Results are cached on disk and reused instantly next time. When a document has no thumbnail at all, the card shows its design-intent icon instead.
- **Design intent at a glance** — every card is marked with the Part, Hybrid, or Assembly icon beside the document name. Hover the icon to see the intent by name.
- Palette theme follows the Fusion UI theme — light, dark, or **match OS device theme** — and is correct on first paint.

## Prerequisites

- An Autodesk Fusion 3D Design must be active.
- **Automatic launch** requires the active document to be **new (unsaved)**, **empty** (no timeline features, bodies, sketches, or child components), and to have **Assembly** design intent.
- **Insert from Open / Recent** requires the source document to be **saved** to an Autodesk Hub — `addByInsert` needs a cloud `DataFile`. Unsaved documents are not listed.
- **Creating a component** requires an **active project** in the Data Panel — that project's folder is where the new external component is stored. If no project is in context, the palette shows a *No target project* banner and disables **New Component** until you select one.

## How to use Assembly Palette

1. In Autodesk Fusion, create a new design with **File > New Design** and confirm the design intent is **Assembly**. The palette opens automatically docked to the right.
   - To open it manually at any time, select **Assembly Palette** in the **Assembly** tab's **Insert** panel (directly below **Insert STEP File**).
2. **To create a component:** enter a component name, choose **Part**, **Hybrid**, or **Assembly** from the dropdown, and select **New Component**. The external component is created in the active project's root folder and added to the active design.
   - If **New Component** is greyed out and a *No target project* banner is shown, there is no active project to store the component in. Open the **Data Panel**, click into the project you want to work in, then press **Re-check** on the banner (or simply click back into the palette — it re-checks automatically when it regains focus).
3. **To insert an open document:** switch to the **Open** tab and click a thumbnail card. The document is inserted as a referenced component at the origin.
   - Tick **Show referenced children** if you also want to see (and insert) the sub-assemblies and parts loaded as references of an open assembly.
4. **To insert a recent document:** switch to the **Recent** tab and click a card. Documents are listed newest-first, with the count on the tab. Only the newest 40 are drawn at once — type part of a name in the filter box to find anything further down the list.
   - A card shows a Part, Hybrid, or Assembly icon beside its name. Some documents have no design intent recorded on Fusion's side; those show no icon rather than a guessed one.
5. **To insert a fastener:** select the **Fasteners ↗** link at the bottom of the insert card. The palette hides and Fusion's Fasteners dialog opens. The trailing **↗** marks a link that opens another dialog.
6. **To design a hierarchy or manage parameters:** select **Assembly Builder…** or **Global Parameters…**. The palette hides and the chosen command opens.

> **Note:** A document you insert during a palette session is removed from both galleries on the next refresh, so a second click cannot silently create a duplicate occurrence. Use the **↻** refresh button to re-scan open and recent documents at any time.

> **Note:** Fusion itself disables Fasteners for part-intent and direct-modeling designs, in the Form environment, for library and AnyCAD-derived components, and when the document is not on a Fusion hub. When that is the case the link reports why instead of hiding the palette on a click that would do nothing.

> **Note:** `addNewExternalComponent` requires an Autodesk Hub folder, so the active project's root folder is used as the destination for new components. You can move the generated documents afterward in the Data Panel.

## Access

| Method | Location |
|---|---|
| Automatic | Opens docked to the right when a **new, empty, Assembly-intent** design becomes active. |
| Manual | **Assembly** tab > **Insert** panel > **Assembly Palette** (below **Insert STEP File**). |

The palette docks to the right edge of the Fusion window. Closing it does not disable the automatic trigger — creating another new empty Assembly design opens it again.

> **Developers:** see the [architecture notes](./arch/Assembly%20Palette.md).

---

[Back to PowerTools Assembly](../README.md)

---

*Copyright © 2026 IMA LLC. All rights reserved.*
