# Document History

[Back to README](../README.md)

## Overview

The **Document History** command adds a **History** button directly to the Fusion Quick Access Toolbar (QAT). Selecting it opens the timeline history panel for the active design document. Without this command, accessing document history requires right-clicking the root component in the browser panel—a non-obvious interaction that is easy to overlook. The QAT button makes history access immediate and consistent.

## Capabilities

| Capability | Details |
|---|---|
| Open document history | Displays the version and timeline history panel for the active design |
| Quick access from the QAT | History button is always present on the Quick Access Toolbar |
| Automatic workspace activation | Switches to the Design workspace if another workspace is active |
| Root component selection | Automatically selects the root component before opening history |

## Prerequisites

- A Fusion design document must be open.
- The active document must be saved to Fusion's cloud data (unsaved documents are not supported).

## Notes

- If the active document has not been saved, the command displays a message asking you to save first.
- If a non-Design workspace is active, the command automatically activates the Design workspace before opening history.

## Access

Select **History** from the **Quick Access Toolbar (QAT)**.

![access](./assets/dochistory.PNG)

> **Developers:** see the [architecture notes](./Arch/Document%20History.md).

[Back to README](../README.md)

*Copyright © 2026 IMA LLC. All rights reserved.*