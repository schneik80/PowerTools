# Open Recent

[Back to README](../README.md)

## Overview

**Open Recent** adds a flyout submenu to Fusion's **File** menu, directly after **Open**, that lists your recently-used documents. Each entry shows the document's name; hovering over it reveals a tooltip with the document's Data Panel location and a thumbnail preview. Selecting an entry opens that document in Fusion.

The list comes from the recents history Fusion already keeps for your signed-in account on the active hub, so it is populated from the first launch rather than having to be built up by using PowerTools. It is the same list that powers the **Recent** gallery in the [Assembly Palette](./Assembly%20Palette.md) quick-start palette. Open Recent simply surfaces it where you expect it: on the File menu, one click from anywhere in Fusion. Unlike that gallery — whose cards insert a component, so it lists designs only — this flyout lists every kind of document Fusion recorded, drawings included.

```text
File ▾
├─ New
├─ Open…
├─ Open Recent            ▸   1.5 TC Sample Valve
├─ Recover Documents…         Wort Pump ASSY
├─ Save                        Mash Tun ASSY
├─ Save As…                    MIP Large T Handle
│  …                           …  (hover → location + thumbnail)
└─ PowerTools Preferences
```

## What you can do

- **Reopen a recent document fast** — the File **▸ Open Recent** flyout lists your most recently used Part/Hybrid/Assembly documents, newest first. Click one to open it — no Data Panel browsing required.
- **See where it lives before you open it** — hover any entry to see a tooltip with the document's full folder location (`Project > Folder > Sub`) and a thumbnail rendered from the document itself.
- **Always current** — the list refreshes as you open and switch between documents, so the most relevant files are always at the top.

## How it works

- The entries and their order come from Fusion's own recents history for the signed-in account on the active hub, which Fusion rewrites as you open documents. Switching hubs switches the list.
- PowerTools keeps a small cache of its own (`cache/recent_docs.json`) alongside it. Every time you activate a **saved** Part, Hybrid, or Assembly document, it is recorded there together with its thumbnail and location. That cache supplies the two things Fusion's history does not carry — the thumbnail, and the design intent for documents Fusion recorded none for — and it becomes the whole list if Fusion's history cannot be read (for example when you are signed out).
- Thumbnails are cached on disk, so they appear in the tooltip even after the document is closed. The cache is shared with the Assembly Palette, which downloads thumbnails from the cloud as you browse its galleries — so opening that palette also fills in tool-clips here. A document with no thumbnail from either route shows a name-and-location tooltip.
- The currently-active document is omitted from the list (you already have it open); it reappears once you switch away from it.
- The flyout shows up to the 15 most recent documents.

## Prerequisites

- Recent documents must be **saved** to an Autodesk Hub — the list is keyed by each document's cloud `DataFile`. Unsaved documents are never listed.
- To open a listed document you must be signed in to the hub it belongs to. If a document has been moved or deleted, Open Recent reports that it could not be found instead of failing silently.

## Access

| Method | Location |
|---|---|
| Menu | **File** menu ▸ **Open Recent** (directly after **Open**) |

Open Recent is enabled by default. You can turn it off (or back on) in **File ▸ PowerTools Preferences**, under **Document Tools**. Changes apply on the next Fusion restart.

> **Note:** Open Recent shares its list with **Assembly Palette**. The two are recorded together, so a document you use in one shows up in the other. Open Recent works independently, though — it keeps the list up to date on its own even if the Assembly commands are disabled.

> **Developers:** see the [architecture notes](./arch/Open%20Recent.md).

[Back to README](../README.md)

*Copyright © 2026 IMA LLC. All rights reserved.*
