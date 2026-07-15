# Select Related Data Folder — Architecture

[← Select Related Data Folder guide](../Select%20Related%20Data%20Folder.md)

## Architecture

### How the command works

When you run **Select Related Data Folder**, the add-in follows this sequence:

1. Loads the current `hub.json` and looks up the active hub. If an entry already exists, an OK / Cancel prompt shows the current project and folder so you can either keep the configuration or proceed and overwrite it.
2. Displays an informational prompt instructing you to browse to the cloud folder that contains your start parts or templates.
3. Opens Fusion's cloud folder picker. If a saved document is open, the picker starts in that document's parent folder.
4. Reads the selected folder's parent project, then iterates through the available data hubs to find the one that owns that project.
5. Builds a hub entry containing the hub, project, and folder IDs and names, and upserts it into the `hubs` array in `hub.json` (replacing any previous entry with the same hub ID).
6. Reloads the in-memory configuration so all commands immediately see the new hub, then displays a success message that says whether the entry was added or updated.

### System context

```mermaid
C4Context
  title System Context — Select Related Data Folder

  Person(user, "Fusion User", "Runs Select Related Data Folder once per hub, per machine")

  System_Boundary(addin, "PowerTools Add-in") {
    System(configHub, "Select Related Data Folder Command", "Opens a cloud folder picker, resolves the owning hub and project, and writes hub configuration to disk")
  }

  System_Ext(fusionTeam, "Autodesk Fusion Team", "Hosts the hub, projects, folders, and template .f3d files")
  SystemDb(hubJson, "hub.json", "Local file in the add-in cache/ folder — stores registered hub IDs, project IDs, and folder IDs")

  Rel(user, configHub, "Runs the command and selects the templates folder")
  Rel(configHub, fusionTeam, "Browses cloud folders; resolves the owning hub and project via Fusion API")
  Rel(configHub, hubJson, "Upserts the hub entry by hub id")
```

### Container detail

```mermaid
C4Container
  title Container Diagram — Select Related Data Folder

  Person(user, "Fusion User")

  Container_Boundary(addin, "PowerTools Add-in") {
    Container(cmdCreated, "command_created handler", "Python / Fusion API", "Prompts for confirmation if the hub is already configured; opens the cloud folder picker; resolves the owning hub via _resolve_hub_for_folder(); upserts hub.json")
    Container(resolveHub, "_resolve_hub_for_folder()", "Python / Fusion API", "Walks app.data.dataHubs and returns the DataHub whose dataProjects include the selected folder's parent project")
    Container(configModule, "config.py", "Python", "Loads and exposes COMPANY_HUB and COMPANY_HUB_CONFIGS in memory from hub.json")
  }

  SystemDb(hubJson, "hub.json", "Local JSON configuration file in the add-in cache/ folder")
  System_Ext(fusionApi, "Fusion API (adsk.core)", "Provides createCloudFolderDialog(), DataFolder.parentProject, app.data.dataHubs, and DataProjects.itemById()")

  Rel(user, cmdCreated, "Runs the command and picks the templates folder")
  Rel(cmdCreated, fusionApi, "Opens cloud folder picker; reads parentProject of the selection")
  Rel(cmdCreated, resolveHub, "Calls _resolve_hub_for_folder(folder)")
  Rel(resolveHub, fusionApi, "Iterates dataHubs and matches by project id")
  Rel(cmdCreated, hubJson, "Upserts the hubs array on success")
  Rel(cmdCreated, configModule, "Calls reload_hub_config()")
  Rel(configModule, hubJson, "Reads hub entries on load or reload")
```
