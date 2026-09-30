# Assembly Palette

[Back to README](../README.md)

## Overview

Assembly Palette is a docked quick-start palette for populating a new assembly: it opens automatically for a new, empty design with Assembly intent, or on demand from the toolbar, and lets you create external Part, Hybrid or Assembly components in place, insert from a thumbnail gallery of your open or recent documents, and hand off to Assembly Builder or Global Parameters.

SolidWorks' Begin Assembly panel offers your open documents for insertion the moment a new assembly opens; Onshape's insert dialog shows recent documents with thumbnails. Fusion's new assembly is an empty browser and a Data Panel to browse. Assembly Palette gives Fusion the same first five minutes: name a component and create it, or click a thumbnail of something you already have open or used recently and it is inserted, with Fusion's position editor started for you.

## Prerequisites

- A design document must be active.
- **Automatic launch** needs a new (unsaved), empty design with Assembly intent.
- **Inserting** from the galleries needs the source document saved to a hub, in the same project as the assembly.
- **Creating a component** needs a project active in the Data Panel. Without one the palette shows a *No target project* banner and disables **New Component**.

## Where to find it

| Method | Location |
|---|---|
| Automatic | Opens docked on the left, beside the browser, when a new, empty, Assembly-intent design becomes active |
| Manual | **Assembly** tab › **Insert** panel › **Assembly Palette** (after **Insert STEP File**), and **Solid** tab › **Assemble** panel › **Assembly Palette** (after **New Component**), wherever those panels exist |

The button toggles the palette: select it to show, select it again to close. Closing it does not stop the automatic launch for the next new assembly.

## How to use

1. **Create a component.** Type a name, choose **Part**, **Hybrid** or **Assembly** (Part is the default) and select **New Component** or press **Enter**. An external component of that intent is created in the active document's folder when it is saved, or the project root when it is not, and added to the design.
2. **Insert an open document.** On the **Open** tab, select a card. By default only top-level documents (the ones you opened yourself) are listed; tick **Show referenced children** to include the sub-assemblies and parts Fusion loaded as references. The document you are in is never listed.
3. **Insert a recent document.** On the **Recent** tab, select a card. The list is the recents Fusion keeps for your account, newest first, with the count on the tab; the newest 40 are drawn and the filter box searches the rest.
4. After an insert, Fusion selects the new occurrence, fits the view, and starts **Edit Initial Position** so you can place it. Selecting another card ends that first.
5. **Insert a fastener.** Select **Fasteners ↗** below the galleries. The palette hides and Fusion's Fasteners dialog opens. Where Fusion disables fasteners (part intent, direct modeling, the Form environment, library or AnyCAD components, a document not on a hub) the link reports why instead.
6. **Hand off.** **Assembly Builder…** and **Global Parameters…** hide the palette and open that command. **Assembly Builder…** is available only while the document is new and unsaved.

Every card shows the document's thumbnail and a Part, Hybrid or Assembly icon; hover the icon for the intent by name. A document with no thumbnail shows its intent icon instead; one with no recorded intent shows none. Thumbnails load as cards scroll into view: an open document is rendered locally and a closed one fetched from the cloud, then cached on disk (`cache/thumbs`) and shared with [Open Recent](./Open%20Recent.md).

The galleries repaint after every create or insert and when you select **↻**, so a document you just inserted disappears from the cards and cannot be inserted twice by accident.

## Limitations

- Inserting a document from a different project is refused with a message; Fusion requires referenced inserts to stay within one project.
- Unsaved documents are never listed.
- The Recent tab lists every design in your recents regardless of intent, including ones Fusion recorded no intent for.
- The filter reaches at most the 300 most recent documents.
- A thumbnail download is abandoned after 20 seconds; the card keeps its intent icon.

> **Developers:** see the [architecture notes](./arch/Assembly%20Palette.md).

---

[Back to README](../README.md)

*Copyright © 2026 IMA LLC. All rights reserved.*
