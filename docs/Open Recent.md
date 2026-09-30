# Open Recent

[Back to README](../README.md)

## Overview

Open Recent adds a flyout to the File menu that lists your recently used documents, with the document's location and thumbnail on hover, and opens one on click.

SolidWorks has **File › Open Recent** and the **R** key; Inventor has the Recent Documents panel on its home screen. Fusion keeps its recents on the home tab and in the Data Panel, both of which mean leaving the design you are in. Open Recent puts the list where every other application keeps it: on the **File** menu, one click from anywhere, with a tooltip that tells you which folder the document lives in before you open it.

```text
File ▾
├─ New
├─ Open…
├─ Open Recent            ▸   1.5 TC Sample Valve
├─ Recover Documents…         Wort Pump ASSY
├─ Save                        Mash Tun ASSY
├─ Save As…                    MIP Large T Handle
│  …                           …  (hover: location and thumbnail)
└─ PowerTools Preferences
```

## Prerequisites

- Listed documents must be saved to a hub; the list is keyed by each document's cloud identity.
- To open a listed document you must be signed in to the hub it belongs to.

## Where to find it

**File › Open Recent** on the Quick Access Toolbar, directly after **Open**. If Fusion's Open entry cannot be found, the flyout is placed after **New**, or before **PowerTools Preferences**.

## How to use

1. Open the **File** menu and hover **Open Recent**.
2. Hover an entry to see its folder location (`Project › Folder › Subfolder`) and a thumbnail.
3. Select an entry to open it. If it has been moved or deleted, a message says it could not be opened.

## How the list is built

- The entries and their order come from the recents history Fusion already keeps for your account on the active hub, so the list is full from the first launch, includes every document type Fusion recorded (drawings included), and switches when you switch hubs.
- PowerTools keeps a small cache of its own (`cache/recent_docs.json`) that records every saved part, hybrid or assembly document you activate, with its thumbnail and location. It supplies what Fusion's history does not carry, the thumbnail and the design intent, and becomes the whole list when Fusion's history cannot be read (for example when you are signed out). In that fallback, drawings are not listed.
- Thumbnails are cached on disk in `cache/thumbs`, so they show even after the document is closed. The cache is shared with the [Assembly Palette](./Assembly%20Palette.md), whose galleries download thumbnails from the cloud, so browsing there fills in thumbnails here.
- The active document is omitted; it reappears once you switch away from it.
- The flyout shows up to 15 documents. With none, it shows a disabled *No recent documents* entry.

## Limitations

- Enabling or disabling the command under **File › PowerTools Preferences › Document Tools** applies after a Fusion restart.

> **Developers:** see the [architecture notes](./arch/Open%20Recent.md).

---

[Back to README](../README.md)

*Copyright © 2026 IMA LLC. All rights reserved.*
