# Show In Location

[Back to README](../README.md)

## Overview

By default in Fusion, the Data Panel does not always track the document currently in focus. The **Show In Location** automation runs Fusion's built-in **Show In Location** text command whenever a document opens or when you switch to a different open document tab.

This keeps the Data Panel synchronized with the active document without any manual action.

## Capabilities

| Capability | Details |
|---|---|
| Automatic document tracking | Runs in the background whenever the add-in is loaded |
| Open-event sync | Triggers after each `documentOpened` event |
| Tab-switch sync | Triggers after each `documentActivated` event |
| Safe fallback behavior | Skips unsaved documents and logs errors without interrupting workflow |
| Enable / Disable toggle | A toggle command in the **PowerTools Settings** dropdown lets you turn the automation on or off without unloading the add-in |
| Persistent toggle state | The enabled/disabled state is saved to `cache/settings.json` and restored on next startup |

## Prerequisites

- The add-in must be loaded.
- The active document must be saved to Fusion cloud data to provide a valid `dataFile.id` URN.

## Notes

- Unsaved documents are skipped because they do not expose a valid cloud `dataFile` reference.
- The toggle label updates dynamically: it reads **Disable Show In Location** when the feature is active and **Enable Show In Location** when it is inactive.
- The enabled/disabled state persists between Fusion sessions via `cache/settings.json`.

## Access

This feature runs automatically in the background whenever the add-in is loaded.

To enable or disable the automation, select **Disable Show In Location** (or **Enable Show In Location**) from the **PowerTools Settings** sub-menu in the **File** dropdown on the **Quick Access Toolbar (QAT)**.

> **Developers:** see the [architecture notes](./Arch/Show%20In%20Location.md).

[Back to README](../README.md)

*Copyright © 2026 IMA LLC. All rights reserved.*
