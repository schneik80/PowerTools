# Select Related Data Folder

[Back to README](../README.md)

## Overview

**Select Related Data Folder** is a setup command that registers the cloud folder where your start parts and templates are located. It records the selected folder — along with its owning Autodesk Fusion Team Hub and project — with the Power Tools add-in. After the folder is selected, the **Create Related Data** command can read templates from that hub automatically.

The folder must be configured **once for each Team Hub**, on each machine. The command opens Fusion's cloud folder picker so you can browse to your templates folder directly. The hub and project that own the selected folder are resolved automatically. No manual ID lookup or JSON editing is required.

---

## When to run Select Related Data Folder

Run **Select Related Data Folder** in the following situations:

- The **first time** you install the add-in on a machine.
- When you **connect to a new hub** that has not been configured on that machine yet — the folder must be selected once per hub.
- When you want to **re-point an existing hub entry** to a different templates folder (for example, after a team administrator moves or renames the folder).

If the active hub is already configured, the command shows the current location and lets you cancel out or pick a new folder to overwrite the existing entry.

---

## Prerequisites

Before running **Select Related Data Folder**, ensure the following are in place in your Team Hub:

1. A **project** accessible to all team members — recommended name: **Templates**.
2. A **folder** inside that project containing your `.f3d` template documents — recommended name: **Related Data** or **Start Parts**. This is the folder you will select, and it is where all start parts and templates must be located.

See [Create Related Data — Step 1](./Related%20Data.md#step-1--create-the-templates-project-and-folder-in-fusion-team) for instructions on creating the templates project and folder.

> This setup step is best performed by a Fusion Team administrator, but any team member can run it.

---

## How to select the related data folder

1. **Run Select Related Data Folder.** Select **Select Related Data Folder** from the **Quick Access Toolbar → File menu → PowerTools Settings** flyout.

2. **Acknowledge the prompt.** A short message tells you to browse to the cloud folder that contains your start parts or templates. Click **OK**.

3. **Pick the templates folder.** Fusion's cloud folder picker opens. Navigate to the folder that contains your template `.f3d` files and confirm the selection. If a saved document is currently open, the picker starts in that document's parent folder as a convenience.

4. **Confirm the result.** A success message confirms the hub was added (or updated) and lists the resolved hub name, project, and folder.

If the active hub is already in `hub.json`, you are asked first whether to keep the existing entry or pick a new folder. Choosing a new folder overwrites the entry in place.

The hub entry is written to `hub.json` at the add-in root in the following format:

```json
{
  "hubs": [
    {
      "id": "a.XXXXXXXXXXXXXXXX",
      "name": "Your Hub Name",
      "project_id": "a.XXXXXXXXXXXXXXXX",
      "project_name": "Templates",
      "folder_id": "urn:adsk.wipprod:fs.folder:co.XXXXXXXXXXXXXXXX",
      "folder_name": "Related Data"
    }
  ]
}
```

Multiple hubs are supported. Run **Select Related Data Folder** once per hub. Re-running on a hub that is already configured upserts the entry — the existing record is replaced in place rather than duplicated.

To remove a hub, open `hub.json` and delete the corresponding entry from the `hubs` array.

---

## Troubleshooting

| Message | Cause | Resolution |
|---|---|---|
| *Hub Already Configured* | The active hub already has an entry in `hub.json` | Click **Cancel** to keep the existing configuration, or **OK** to pick a new folder and overwrite the entry |
| *Hub Not Found* | The selected folder could not be matched to a hub the user has access to | Confirm you are signed in to the correct Autodesk account and that the folder lives in a project you can read; then re-run the command |

---

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
  SystemDb(hubJson, "hub.json", "Local file at the add-in root — stores registered hub IDs, project IDs, and folder IDs")

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

  SystemDb(hubJson, "hub.json", "Local JSON configuration file at the add-in root")
  System_Ext(fusionApi, "Fusion API (adsk.core)", "Provides createCloudFolderDialog(), DataFolder.parentProject, app.data.dataHubs, and DataProjects.itemById()")

  Rel(user, cmdCreated, "Runs the command and picks the templates folder")
  Rel(cmdCreated, fusionApi, "Opens cloud folder picker; reads parentProject of the selection")
  Rel(cmdCreated, resolveHub, "Calls _resolve_hub_for_folder(folder)")
  Rel(resolveHub, fusionApi, "Iterates dataHubs and matches by project id")
  Rel(cmdCreated, hubJson, "Upserts the hubs array on success")
  Rel(cmdCreated, configModule, "Calls reload_hub_config()")
  Rel(configModule, hubJson, "Reads hub entries on load or reload")
```

---

## Access

**Select Related Data Folder** is in the **Quick Access Toolbar → File menu → PowerTools Settings** flyout.

---

[Back to README](../README.md)

*Copyright © 2026 IMA LLC. All rights reserved.*
