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

The hub entry is written to `hub.json` in the add-in's `cache/` folder in the following format:

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

## Access

**Select Related Data Folder** is in the **Quick Access Toolbar → File menu → PowerTools Settings** flyout.

---

> **Developers:** see the [architecture notes](./arch/Select%20Related%20Data%20Folder.md).

---

[Back to README](../README.md)

*Copyright © 2026 IMA LLC. All rights reserved.*
