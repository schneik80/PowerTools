# Scripts and Add-ins

[Back to README](../README.md)

## Overview

The **Scripts and Add-ins** command adds a single entry to the Fusion **File**
menu (on the Quick Access Toolbar), placed directly above **PowerTools
Preferences**. Selecting it opens Fusion's built-in **Scripts and Add-Ins**
manager — the same dialog reached with **Shift+S** or **Utilities › Add-Ins** —
without leaving the File menu. It exists to put a frequently used tool one click
away in a predictable location.

## Capabilities

| Capability | Details |
|---|---|
| Open the Scripts and Add-Ins manager | Launches the built-in Fusion `ScriptsManagerCommand` |
| Convenient placement | Lives in the QAT File menu, immediately above PowerTools Preferences |
| Enable / disable | Can be turned on or off from the **Tools** section of PowerTools Preferences |

## Prerequisites

- The PowerTools add-in must be active.

## Notes

- This command is a launcher: it presents no dialog of its own and immediately
  invokes the built-in manager.
- If the command is disabled in Preferences, the menu item is not added on the
  next Fusion restart.

## Access

Select **File ▸ Scripts and Add-ins** from the Quick Access Toolbar, directly
above **PowerTools Preferences**.

> **Developers:** see the [architecture notes](./arch/Scripts%20and%20Add-ins.md).

[Back to README](../README.md)

*Copyright © 2026 IMA LLC. All rights reserved.*
