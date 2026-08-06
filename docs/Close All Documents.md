# Close All Documents

[Back to PowerTools Assembly](../README.md)

The Close All Documents command closes every open document in one pass. Documents with nothing to save close immediately, and a single dialog covers all the documents that still have unsaved changes. Use this command to clear a crowded set of tabs at the end of a working session, instead of closing documents one at a time and answering a separate save prompt for each.

## What you can do

- Close every open document with one click, including the referenced children Autodesk Fusion opened behind the scenes.
- Answer one Save prompt for all your unsaved work rather than one prompt per document.
- Discard every unsaved change at once when you are abandoning an experiment.
- Back out with **Cancel** and keep every document that still has unsaved changes.

## Prerequisites

- At least one document must be open.
- To save on close, documents must be saved to an Autodesk Hub (cloud project). A document that has never been saved needs a name and folder, so Autodesk Fusion collects those with its own Save dialog.

## How to use Close All Documents

1. On the Quick Access Toolbar, select **File**, then select **Close All Documents**.
2. Every document with nothing to save closes right away.
3. If any documents still have unsaved changes, a dialog lists them and asks what to do:
   - **Yes** — save each document, then close it.
   - **No** — close them and discard the changes.
   - **Cancel** — leave them open.

A successful close reports nothing — the emptied tabs are the confirmation. You are only interrupted if a document could *not* be closed, in which case a dialog names it and says why.

> **Note:** The documents with nothing to save close *before* the dialog appears, so **Cancel** does not bring them back. Nothing is lost — those documents had no unsaved changes — but their tabs are already gone.

> **Note:** For a document that has never been saved, Autodesk Fusion shows its own Save dialog so you can choose a name and folder. Cancelling that dialog keeps the document open.

> **Note:** A document whose save fails or times out is left open rather than closed, so your changes are never lost to a failed upload. The command names it and says why.

## Access

The **Close All Documents** command is located in the **File** dropdown menu on the Autodesk Fusion Quick Access Toolbar, next to **Refresh Active Document**.

> **Developers:** see the [architecture notes](./arch/Close%20All%20Documents.md).

---

[Back to PowerTools Assembly](../README.md)

---

*Copyright © 2026 IMA LLC. All rights reserved.*
