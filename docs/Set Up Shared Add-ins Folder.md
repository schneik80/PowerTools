# Set Up Shared Add-ins Folder

[Back to README](../README.md)

## Overview

Set Up Shared Add-ins Folder finds or creates the hub folder that [Team Add-ins](./Team%20Add-ins.md) reads from: `Assets / Shared Addins` in the active hub.

There is nothing to browse for and nothing to save. The location is a fixed convention, so every teammate on the hub reads the same folder automatically and there is no per-machine configuration to keep in step. The command checks that the folder exists, offers to create it, and reports what it found.

## Prerequisites

- You must be signed in to a Fusion Team hub.
- The hub must already have a project named **Assets**. PowerTools does not create projects, because that needs Fusion Team administrator rights.
- To create the folder you need write access to **Assets**. Everyone else only needs read access.

## Where to find it

**File › PowerTools Preferences › Team Add-ins › Shared folder**. The status card there shows the folder's state and a button that reads **Create shared folder…** until the folder exists and **Check folder…** afterwards. The same **Create shared folder…** button appears in the Team Add-ins report palette when the folder is missing.

| State | Meaning |
|---|---|
| **Ready** | The folder exists; the card lists how many packages are in it and how many are installed on this machine |
| **Not created** | The Assets project is there but the folder is not |
| **No hub** | You are not signed in to a Fusion Team hub |
| **Unavailable** | The hub could not be read, or it has no Assets project; the card says which |

## How to use

1. Open **PowerTools Preferences** from the **File** menu and go to the **Team Add-ins** section.
2. Select the button on the **Shared folder** card.
3. If the folder has to be created, a dialog names the project it will be created in and asks you to confirm.
4. A message reports the hub, project, folder and the number of packages found.

The result takes effect immediately. Select **Utilities › Power Tools › Team Add-ins** to check the folder right away.

## Adopting an existing folder

Teams often create this folder by hand before installing PowerTools. Matching ignores case, spaces and punctuation, so an existing folder is adopted rather than duplicated:

| Existing folder name | Adopted |
|---|---|
| `Shared Addins` | Yes (an exact match always wins) |
| `Shared AddIns`, `shared add-ins`, `SharedAddins` | Yes |
| `Shared Data` | No; unrelated folder |

Only root-level folders of **Assets** are searched, and only when nothing matches does the command offer to create `Shared Addins`.

## Troubleshooting

| Message | Cause | What to do |
|---|---|---|
| *No active hub. Sign in to a Fusion Team hub.* | Not signed in | Sign in to the hub that holds your team's Assets project |
| *This hub has no 'Assets' project* | The project does not exist | Ask a Fusion Team administrator to create it |
| *Could not create 'Shared Addins'…* | You have read but not write access to Assets | Ask someone with write access to run the command once |
| The Team Add-ins section has no Shared folder card | The Team Add-ins group is disabled | Tick **Enable Team Add-ins commands** in that section and restart Fusion |

> **Developers:** see the [architecture notes](./arch/Set%20Up%20Shared%20Add-ins%20Folder.md).

---

[Back to README](../README.md)

*Copyright © 2026 IMA LLC. All rights reserved.*
