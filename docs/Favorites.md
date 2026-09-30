# Favorites

[Back to README](../README.md)

## Overview

Favorites adds a Quick Access Toolbar dropdown of saved Fusion Team locations, so the folders you work in most are one click away instead of a walk through the Data Panel.

Fusion's Data Panel remembers nothing between sessions except which project you last opened. Favorites keeps a list of locations per hub, saved from whatever document you have open, and each entry navigates the Data Panel straight to that folder. Switch hubs and the list switches with you.

## Prerequisites

- To save a favorite, the active document must be saved to a hub.
- To navigate, a document must be open.

## Where to find it

**Favorites** on the Quick Access Toolbar, immediately before the **File** menu.

The dropdown holds two actions and then one entry per saved location:

- **Favorite This Location** saves the active document's folder.
- **Edit Favorites** opens a dialog to remove entries.
- Each saved entry is labelled with its folder path (`Project › Folder › Subfolder`) and takes the Data Panel there.

## How to use

1. Open a document that lives in the folder you want to keep.
2. Select **Favorites › Favorite This Location**. A location already in the list is not added twice.
3. Later, select the entry from the **Favorites** dropdown. The Data Panel opens at that folder.

To remove entries, select **Edit Favorites**, tick the rows to remove, select **Delete Selected**, then **OK**. Deletions are applied only when you confirm with **OK**.

## What it stores

- Favorites are kept per hub in `cache/favorites_<hub_id>.json` inside the add-in folder, and reloaded when PowerTools starts.
- The list reloads when a document is opened or activated under a different hub.

## Limitations

- Entries are keyed by the document you saved them from, so two documents in the same folder produce two entries with the same label.
- A location that has been moved or deleted reports that it could not be found.
- Switching hubs in the Data Panel alone does not reload the list until the next document is opened or activated.

> **Developers:** see the [architecture notes](./arch/Favorites.md).

---

[Back to README](../README.md)

*Copyright © 2026 IMA LLC. All rights reserved.*
