# Close All Documents

[Back to README](../README.md)

## Overview

Close All Documents closes every open document, saving or discarding unsaved changes as a group.

SolidWorks (**Window › Close All**) and Inventor (**Close All** on the document tabs) both offer this; Fusion does not, so a long session ends with one tab closed at a time and one save prompt per tab. Close All Documents closes everything that has nothing to save immediately, including the referenced children Fusion opened behind the scenes, and asks one question about the documents that still have unsaved changes.

## Prerequisites

- At least one document must be open.
- To save on close, a document must belong to a hub project. A document that has never been saved needs a name and folder, so Fusion shows its own Save dialog for it.

## Where to find it

**File › Close All Documents** on the Quick Access Toolbar, after **Export**.

## How to use

1. Open the **File** menu and select **Close All Documents**.
2. Every document with nothing to save closes right away.
3. If any documents still have unsaved changes, one dialog lists them and asks what to do:
   - **Yes** saves each one, then closes it.
   - **No** closes them and discards the changes.
   - **Cancel** leaves them open.

A successful close reports nothing; the emptied tabs are the confirmation. You are interrupted only if a document could not be closed, in which case a dialog names it and says why.

## What it produces

- Saves made through **Yes** carry the version comment `Saved by PowerTools Close All Documents`.
- A document whose save fails or whose upload does not finish within 300 seconds is left open rather than closed, so no change is lost to a failed upload.

## Limitations

- Documents with nothing to save close *before* the dialog appears, so **Cancel** does not bring them back. Nothing is lost; they had no unsaved changes.
- For a never-saved document Fusion shows its own Save dialog. Cancelling it keeps that document open, and the hidden referenced children are then left open as well.
- With no documents open the command reports that there is nothing to close.

> **Developers:** see the [architecture notes](./arch/Close%20All%20Documents.md).

---

[Back to README](../README.md)

*Copyright © 2026 IMA LLC. All rights reserved.*
