# Favorites

[Back to README](../README.md)

## Overview

The **Favorites** command adds a dropdown to the Fusion Quick Access Toolbar (QAT) so you can save and revisit frequently used document locations in Fusion Team Hub. It includes actions to add the current document location and edit the saved list.

Favorites are stored locally **per Fusion hub**. Each hub gets its own cache file named `cache/favorites_<hub_id>.json`. When you switch to a document from a different hub the dropdown automatically reloads and shows only the favorites that belong to that hub.

## Capabilities

| Capability | Details |
|---|---|
| Save active location | Adds the current saved document location using its `dataFile.id` URN |
| Quick navigation | Creates one-click menu items that run `Dashboard.ShowInLocation <urn>` |
| Duplicate prevention | Skips adding entries when the same URN is already saved for the active hub |
| Per-hub storage | Each Fusion hub has its own cache file (`cache/favorites_<hub_id>.json`) |
| Automatic hub switching | Detects hub changes on `documentActivated` / `documentOpened` and reloads the menu |
| Edit favorites | Opens an edit dialog where one or more favorites can be selected and deleted |
| Persistent cache | Restores the active hub's favorites on add-in startup |

## Prerequisites

- A Fusion document must be open.
- The document must be saved to Fusion cloud data.

## Notes

- Favorites are stored per hub in `cache/favorites_<hub_id>.json`.
- The hub ID is read from `app.data.activeHub.id` (e.g. `b.abc123`) and sanitised for use in a filename.
- The dropdown is automatically rebuilt whenever the active hub changes.
- Favorites are resolved and rebuilt into command entries each time the add-in starts.
- Saved entries use `dataFile.id` URNs, which is the same format that `Dashboard.ShowInLocation` expects.

## Access

Select **Favorites** from the **Quick Access Toolbar (QAT)**.

Inside the dropdown:

- **Favorite This Location** saves the active document location.
- **Edit Favorites** opens a dialog to remove selected entries.
- Each saved location appears as a command that navigates directly to that location in the Data Panel.

> **Developers:** see the [architecture notes](./Arch/Favorites.md).

[Back to README](../README.md)

*Copyright © 2026 IMA LLC. All rights reserved.*
