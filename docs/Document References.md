# Document References

[Back to PowerTools Assembly](../README.md)

The Document References command displays a dialog that lists all documents related to the active Autodesk Fusion design, organized by relationship type. Use this command to understand how the active document fits into a larger project — for example, to identify which top-level root assemblies ultimately contain the active part, which assemblies directly use it, which drawings reference it, or which related discipline documents are linked to it.

## What you can do

- **Find root assemblies** — recursively walk the full parent chain to identify every top-level assembly that has no further parents, across any depth of nesting.
- View all immediate parent documents that reference the active document (where-used relationships).
- View all child documents that the active document references (uses relationships).
- View all drawings associated with the active document.
- View all standard component (fastener) references used by the active document.
- View all related data documents created with the PowerTools Related Data workflow, separated from structural assembly references.
- Open any listed document directly in Autodesk Fusion by selecting the open button next to the document name.
- Open any listed document in the Autodesk Fusion web browser by selecting the web button next to the document name.
- See thumbnail previews of each referenced document.

## Prerequisites

- An Autodesk Fusion 3D Design must be active.
- The active document must be saved to an Autodesk Hub.
- An internet connection is required. The command displays a message if you are offline.

## How to use Document References

1. Open the Autodesk Fusion Design workspace with an active saved design.
2. On the **Utilities** tab, in the **Power Tools** panel, select **Document References**.
3. The dialog opens and organizes references into the following groups:

   | Group | Description |
   |---|---|
   | **Roots** | Top-level assemblies that have no further parents, found by recursively walking the full parent chain. Drawings and Related Data documents are excluded from the chain. The active document itself is never listed here. |
   | **Used In (Parents)** | Assemblies or other documents that directly reference (use) the active document |
   | **Uses (Children)** | Documents that the active document references as components or links |
   | **Drawings** | Drawing documents (`.f2d`) associated with the active document |
   | **Fasteners** | Standard Components library references used in the active document |
   | **Related Data** | Documents linked through the PowerTools related data relationship (identified by the `‹+›` name marker) |

4. Each row in the dialog shows:
   - A thumbnail preview of the document.
   - The document name.
   - An **Open in Fusion** button (folder icon) to open the document in a new tab.
   - An **Open in browser** button (web icon) to open the document in Autodesk Fusion web.
5. Select **Close** to dismiss the dialog.

> **Note:** Each group heading shows the total count of documents in that group. If a group has no entries, it is shown collapsed and empty.

## Access

The **Document References** command is located on the **Utilities** tab, in the **Power Tools** panel of the Autodesk Fusion Design workspace.

![Toolbar access](./assets/docrefs_002.png)

![Document References dialog](./assets/docrefs_001.png)

> **Developers:** see the [architecture notes](./arch/Document%20References.md).

---

[Back to PowerTools Assembly](../README.md)

---

*Copyright © 2026 IMA LLC. All rights reserved.*
