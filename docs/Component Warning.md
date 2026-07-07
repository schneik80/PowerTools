# Component Warning

[Back to PowerTools Assembly](../README.md)

The Component Warning command is a passive guard that warns you before a new feature is created in the wrong place in an assembly. When enabled, it watches for feature-creation commands (sketches, solids, work geometry, patterns, and surfaces) and prompts you when the feature would be created directly in the root component, in a non-leaf component, or while a selection references a different component than the one you are editing. This helps keep assembly designs organized by ensuring features are authored inside the component they belong to.

The command is a toggle: turn it on to monitor placement, turn it off to work without prompts.

## What you can do

- Catch features that would be created directly in the root component, outside of any component.
- Catch features that reference a component other than the one currently being edited.
- Optionally catch features created in a non-leaf component (a component that still has child occurrences).
- Choose, per warning, to create the feature anyway, cancel the command, or silence the warning for the active document.
- Enable or disable the guard from **PowerTools Settings** in the QAT File menu.

## Prerequisites

- An Autodesk Fusion 3D Design must be active.
- The guard is active only in the **Design** (Solid) workspace; it automatically detaches in other workspaces.
- The active design must use **Assembly** or **Hybrid** design intent. Designs with **Part** intent are skipped, because features there are meant to be built directly in the root component.

## How to use Component Warning

1. Open the **QAT File menu** (the file icon at the top-left of Fusion) and expand **PowerTools Settings**.
2. Click **Enable Component Warning**. The menu item changes to **Disable Component Warning** while the guard is active.
3. Continue modeling as usual. If you start a feature-creation command while editing the root component (or referencing another component), a warning dialog appears.
4. In the warning dialog, choose one of the following:
   - **Yes** — create the feature anyway. To avoid a duplicate prompt, the guard pauses briefly after this choice.
   - **No** — stop warning for the active document for the rest of the session.
   - **Cancel** — cancel the command so no feature is created.
5. To turn the guard off entirely, open **PowerTools Settings** again and click **Disable Component Warning**.

> **Note:** Documents silenced with **No** are remembered only for the current Fusion session. Reopening the document restores warnings.

## Access

**Component Warning** is accessed from the **QAT File menu › PowerTools Settings**. The menu item label reflects the current state: **Enable Component Warning** when the guard is off, **Disable Component Warning** when it is on. The PowerTools Settings submenu is shared with other PowerTools add-ins and is created automatically on first use.

> **Developers:** see the [architecture notes](./arch/Component%20Warning.md).

---

[Back to PowerTools Assembly](../README.md)

---

*Copyright © 2026 IMA LLC. All rights reserved.*
