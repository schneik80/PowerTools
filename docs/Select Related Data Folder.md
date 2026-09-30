# Select Related Data Folder

[Back to README](../README.md)

## Overview

Select Related Data Folder records the cloud folder where your related-data templates are kept, so [Create Related Data](./Related%20Data.md) knows where to copy them from.

The folder is chosen once per hub, per machine, in Fusion's own cloud folder picker. The hub and project that own the selected folder are resolved automatically; there is no ID to look up and no file to edit.

## Prerequisites

- A project in the hub that every team member can read (recommended name **Templates**), with a folder directly under the project root holding your `.f3d` templates (recommended name **Related Data** or **Start Parts**). See [Create Related Data](./Related%20Data.md#setting-up-templates).
- You must be signed in to the hub.

## Where to find it

**File › PowerTools Preferences › Related Data › Hub Settings › Select Related Data Folder…**. The Hub Settings card shows the active hub and whether it is configured, and the project and folder when it is.

## How to use

1. Open **PowerTools Preferences** from the **File** menu and go to **Related Data › Hub Settings**.
2. Select **Select Related Data Folder…**. If the active hub is already configured, a **Hub Already Configured** dialog shows the current location: **Cancel** keeps it, **OK** picks a new folder.
3. Read the prompt and select **OK**. Fusion's cloud folder picker opens, titled **Select Templates Folder**, starting at the active document's folder if that document is saved.
4. Browse to the templates folder and confirm.
5. A **Hub Configured** message confirms the hub was added or updated.

The entry takes effect immediately; no restart is needed.

## What it stores

The hub entry is written to `cache/hub.json` in the add-in folder:

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

Several hubs can be configured; run the command once on each. Re-running on a configured hub replaces its entry. To remove a hub, delete its entry from the `hubs` array.

## Limitations

- The templates folder must sit directly under the project root. A deeper folder, or the project root itself, makes Create Related Data report **Folder Not Found**.
- Create Related Data caches the template list per hub in `cache/<hub id>.json`. After re-pointing a hub to a different folder, delete that file so the list is rebuilt.
- The "already configured" check looks at the active hub, while the entry written belongs to the hub that owns the folder you picked. Pick a folder in the hub you are signed in to.

## Troubleshooting

| Message | Cause | What to do |
|---|---|---|
| **Hub Already Configured** | The active hub has an entry | **Cancel** to keep it, **OK** to pick a new folder |
| **Hub Not Found** | The selected folder could not be matched to a hub you can access | Sign in to the right account, check the folder is in a project you can read, and try again |

> **Developers:** see the [architecture notes](./arch/Select%20Related%20Data%20Folder.md).

---

[Back to README](../README.md)

*Copyright © 2026 IMA LLC. All rights reserved.*
