# Show In Location

[Back to README](../README.md)

## Overview

Show In Location reveals the active document's location in the Data Panel automatically when a document is opened or activated.

Fusion's Data Panel does not follow the document you are working in: open a design from a search result or a link, or switch tabs, and the panel stays wherever you last left it. Show In Location runs Fusion's own **Show In Location** action for you at those two moments, so the folder that holds the active document is always the one on screen. It is the same "reveal in folder" convenience every desktop file browser offers, applied to Fusion's cloud data.

There is no button. The automation ships turned off and is controlled entirely from **PowerTools Preferences**.

## Prerequisites

- The active document must be saved to a hub. An unsaved document has no location to reveal and is skipped silently.

## Where to find it

Show In Location has no toolbar entry. Turn it on under **File › PowerTools Preferences › Document Tools › Show In Location**.

## How to use

1. Open **PowerTools Preferences** from the **File** menu on the Quick Access Toolbar.
2. In the **Document Tools** group, tick **Show In Location** to enable the command, then tick one or both triggers beneath it.
3. Restart Fusion. Enabling or disabling a command takes effect on the next start; the two trigger checkboxes take effect immediately once the command is enabled.

From then on the Data Panel moves to the active document's folder at the moments you selected.

## Preferences

| Setting | Default | Effect |
|---|---|---|
| **Show In Location** (Commands list) | Off | Loads the automation at all. Applies on the next Fusion restart. |
| **Reveal location when a document is opened** | Off | Reveal after each document open. |
| **Reveal location when a document is activated** | Off | Reveal each time you switch to a different open document tab. |

With the command enabled but both triggers off, nothing happens.

## Limitations

- Unsaved documents are skipped; they have no cloud location.
- The Data Panel must be visible for the reveal to be seen. Use [Toggle Data Pane](./Toggle%20Data%20Pane.md) to open it.
- Errors are logged and never interrupt opening or switching documents.

> **Developers:** see the [architecture notes](./arch/Show%20In%20Location.md).

---

[Back to README](../README.md)

*Copyright © 2026 IMA LLC. All rights reserved.*
