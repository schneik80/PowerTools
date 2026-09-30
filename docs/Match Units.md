# Match Units

[Back to README](../README.md)

## Overview

Match Units compares the active document's units with your Fusion default units and changes the document to match in one click.

Fusion stamps a new design with the default units from **Preferences › Design › Default Units**, but a document keeps whatever units it was created with. Anything that arrives from somewhere else, a colleague's design, an insert, a file created before you changed your preference, carries its own, and Fusion will leave a millimetre design open in an inch workflow without a word. SolidWorks shows the document's units in the status bar; Fusion shows nothing. Match Units puts the state on a toolbar icon and fixes it in one click.

It has three parts:

- A button on the **Inspect** panel whose icon reports the active document: a plain ruler when its units agree with your default, a ruler with an exclamation mark when they do not. Selecting it changes the document.
- An optional prompt when a document opens.
- An optional prompt when you switch to the Manufacture workspace, which keeps a *separate* unit system from the design, so feeds and speeds can be in inches under a millimetre design with nothing on screen to say so.

The first two compare length and mass, the same pair Fusion's default-units preference holds. The Manufacture check compares length only, by family (metric or imperial), because that is all Manufacture has.

## Prerequisites

- A design document, saved or unsaved. Drawings and other document types are ignored.

## Where to find it

The **Inspect** panel of the design tabs (Solid, Surface, Mesh, Sheet Metal, Plastic), alongside Fusion's **Measure**.

| Icon | Meaning |
|---|---|
| Ruler | Length and mass units both match your Fusion default |
| Ruler with an exclamation mark | At least one does not |

Hover the button for the specifics: *Document is in in, oz; your Fusion default is mm, g. Click to change the document to match.* The icon refreshes when a document opens, when you switch tabs, and when you switch workspaces. It is neutral rather than alarmed when there is nothing to compare.

## How to use

### Change the active document

1. Select **Match Units** on the **Inspect** panel.
2. A dialog confirms what changed, for example *Document units changed from in, oz to mm, g.* A document that already matches is reported and left alone.

### Be asked when a document opens

Off by default, because it puts a dialog on top of opening a file. Turn on **Ask to match units when a document is opened** (see Preferences). Opening a design whose units differ from your default then asks:

> *"Bracket v12" is in inches and ounces. Your Fusion default units are millimeters and grams. Change this document to match your default units?*

**Yes** changes the document. **No** leaves it alone and remembers nothing, so the same document asks again next time. The question is asked a moment after the document has finished opening.

### Be asked when you switch to Manufacture

Off by default. Turn on **Ask to match units when switching to the Manufacture workspace**. Switching into Manufacture then asks:

> *"Bracket v12" is in millimeters in the Design workspace, but the Manufacture workspace is set to inches. Feeds, speeds and toolpath dimensions are entered and shown in inches. Change the Manufacture workspace to millimeters to match the design?*

**Yes** switches Manufacture to match. **No** is remembered for that document and that Manufacture setting for the rest of the session, so moving in and out of Manufacture does not nag. The check runs only once the Manufacture data exists; on the very first entry into Manufacture for a document Fusion is still creating it, so the check catches it the next time.

## Preferences

Under **File › PowerTools Preferences › Document Tools › Match Units**:

| Setting | Default | Effect |
|---|---|---|
| **Ask to match units when a document is opened** | Off | The open-time prompt |
| **Ask to match units when switching to the Manufacture workspace** | Off | The Manufacture prompt |

Both take effect immediately. Enabling or disabling the command itself applies after a Fusion restart.

## Results

- The document's length and mass units become the ones in **Preferences › Design › Default Units**. Where your default is one of Fusion's named combinations (mm/g, cm/g, m/kg, in/oz, ft/lb) the document's unit system is set to that combination, which is what **Document Settings** then shows; any other pair is set unit by unit and reads *Custom*.
- Geometry, parameters and dimensions are unchanged. Units control how values are displayed and entered; nothing is rescaled, and a 25.4 mm hole is still a 1 in hole.

## Limitations

- Changing units is a document setting, not a timeline feature, so **Undo** does not reverse it. Run the command again or change **Document Settings**.
- The open prompt fires on document open, not on tab switch; switching to an already-open document refreshes the icon but asks nothing.
- Only length and mass are compared. Angle and time units are not part of Fusion's default-units preference.
- The button changes only the design units. Manufacture units are changed only through the Manufacture prompt, and only through Fusion afterwards.
- The two checks point in opposite directions: the document check moves the *document* towards your default; the Manufacture check moves *Manufacture* towards the document. If your default is millimetres but the open design is inches, answering Yes in Manufacture sets Manufacture to inches, while the Inspect icon still reports the design as disagreeing with your default. That is intended: the Manufacture check keeps the two halves of one document consistent, not your default enforced.
- The Manufacture check is silently off on a Fusion build without the Manufacture workspace.

> **Developers:** see the [architecture notes](./arch/Match%20Units.md).

---

[Back to README](../README.md)

*Copyright © 2026 IMA LLC. All rights reserved.*
