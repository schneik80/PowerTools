# Document Information

[Back to README](../README.md)

## Overview

Document Information shows the hub, project, folder and version identifiers of the active document, and warns when saving it would migrate it to the running Fusion build.

When a reference will not resolve, a teammate cannot see a file, or support asks "which document exactly?", the answer is an identifier the Fusion UI never shows. This command puts them all in one dialog: hub, project, folder and document IDs, the full folder path, the version you have open and the latest version on the hub. It also compares the Fusion build that last saved the document with the one you are running, so you know before you save that the file will move to a new schema and that collaborators on an older client will no longer be able to open it.

## Prerequisites

- A design document must be open and saved to a hub. An unsaved document has no identifiers, and the command asks you to save first.

## Where to find it

**Utilities** tab › **Power Tools** panel › **Document Information**, in the Design workspace.

![Document Information on the Power Tools panel](./assets/docinfo_002.png)

## How to use

1. Select **Document Information**.
2. Read the dialog. Select **OK** to close it.

![Document Information dialog](./assets/docinfo_001.png)

## What it shows

| Field | Meaning |
|---|---|
| Hub name and ID | The hub active in the Data Panel |
| Project name and ID | The project that holds the document |
| Folder name and ID | The document's parent folder, or the project root |
| Path | Folder path from the project root to the document |
| Document name and ID | The document's cloud identifier |
| Version | `Version X of Y`: the version you have open and the latest on the hub |
| Version comment | The comment typed at the last save |
| Fusion build | The build that saved this version |

If that build differs from the one you are running, the dialog title changes to say the document will migrate on save, the icon becomes a warning, and a line at the end explains it.

## Limitations

- The hub shown is the one active in the Data Panel, which is normally, but not necessarily, the document's own hub.
- The command reads a design document; it is not available for drawings.

> **Developers:** see the [architecture notes](./arch/Document%20Information.md).

---

[Back to README](../README.md)

*Copyright © 2026 IMA LLC. All rights reserved.*
