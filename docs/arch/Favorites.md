# Favorites — Architecture

[← Favorites guide](../Favorites.md)

## Data model

Each hub's favorites are saved in a separate file: `cache/favorites_<sanitised_hub_id>.json`.

```json
{
  "hub_id": "b.abc123def456",
  "favorites": [
    {
      "name": "Document Name",
      "display": "Project > Folder > Subfolder",
      "urn": "urn:adsk.wipprod:dm.lineage:..."
    }
  ]
}
```

- `hub_id`: the Fusion hub ID this file belongs to (informational).
- `name`: document name shown in edit UI.
- `display`: folder lineage shown in the dropdown and edit table.
- `urn`: the `dataFile.id` URN used for reliable navigation.

## Architecture

The Favorites module creates one static dropdown control and a set of dynamic command definitions. The first two static actions are **Favorite This Location** and **Edit Favorites**. Below those actions, each favorite entry is added as a generated command that executes `Dashboard.ShowInLocation` for its saved URN.

### Command IDs

- Dropdown: `PTAT-favorites-dropdown`
- Add action: `PTAT-favorites-add`
- Edit action: `PTAT-favorites-edit`
- Dynamic favorite entries: `PTAT-fav-<index>`

### Execution flow

1. Add-in startup removes any legacy `cache/favorites.json`, resolves the active hub ID, and creates the Favorites dropdown on the QAT.
2. Startup registers static commands for add/edit and loads saved favorites from the active hub's cache file.
3. The menu is rebuilt with dynamic commands for each saved favorite.
4. Application-level `documentActivated` and `documentOpened` handlers monitor for hub changes. When the hub changes, the menu is rebuilt with the new hub's favorites.
5. **Favorite This Location** validates the active document is saved and writes a new favorite record to the active hub's cache file if it is not a duplicate.
6. **Edit Favorites** stages changes in a dialog table and commits deletes only when the user confirms.
7. Selecting any saved favorite executes `Dashboard.ShowInLocation <urn>`.

### Component diagram

```mermaid
C4Component
    title Favorites – Component Architecture

    Person(user, "Designer", "Fusion user managing common locations")
    Component(addin, "PowerTools Add-In", "Python, Fusion API", "Hosts and starts all command modules")
    Component(cmd, "Favorites", "favorites/entry.py", "Builds QAT dropdown, detects hub changes, manages per-hub cache, and handles navigation")
    Component(cache, "cache/favorites_<hub_id>.json", "Local JSON files", "One file per Fusion hub; persists favorites between sessions")
    Component(fusion, "Dashboard.ShowInLocation", "Fusion Internal Command", "Opens the saved location in Data Panel")
    Component(docevt, "documentActivated / documentOpened", "Fusion App Events", "Signal used to detect hub changes")

    Rel(user, addin, "Loads add-in on Fusion start")
    Rel(addin, cmd, "Calls start() and stop()")
    Rel(cmd, cache, "Reads and writes per-hub favorites list")
    Rel(user, cmd, "Uses add/edit actions and selects saved entries")
    Rel(cmd, fusion, "Executes Dashboard.ShowInLocation <urn>")
    Rel(docevt, cmd, "Triggers hub-change check and menu rebuild")
```
