# Match Units

[Back to README](../README.md)

## Overview

Fusion stamps a new design with the default units set in **Preferences › Design › Default Units**, but a document keeps whatever units it was created with. Anything that arrives from somewhere else — a colleague's design, a document copied from another hub, an insert, a file created before you changed your preference — carries its own. Fusion will happily leave a millimetre design open in an inch workflow and never mention it.

**Match Units** makes that difference visible and fixes it in one click.

It has three faces:

- A **button on the Inspect panel** whose icon reports the state of the active document: a plain ruler when its units agree with your default, and a ruler with an exclamation mark when they do not. Clicking it changes the document to match.
- An optional **prompt when a document opens**, asking yes or no whether to change it.
- An optional **prompt when you switch to the Manufacture workspace**, covering a different and less visible problem: Fusion keeps a *separate* active unit system for Manufacture, so a millimetre design can be inches in Manufacture with nothing on screen to say so.

The first two compare **length and mass** — the same pair Fusion's own Default Units preference holds. A design in inches and grams does not match a default of inches and ounces, and Match Units says so. The Manufacture check compares **length only**, because that is all Manufacture has.

## Prerequisites

- A 3D design document — part, assembly, or hybrid, saved or unsaved — must be open.
- Nothing needs to be selected.

Drawings, manufacturing setups and other non-design documents are ignored: they have no design units to compare.

## Access

The command sits on the **Inspect** panel of every design workspace — Solid, Surface, Mesh, Sheet Metal and Plastic — alongside Fusion's own Measure.

## Reading the icon

| Icon | Meaning |
|---|---|
| Ruler | The document's length and mass units both match your Fusion default. |
| Ruler with an exclamation mark | At least one of them does not. |

Hover the button for the specifics — the tooltip names both sides, for example *"Document is in in, oz; your Fusion default is mm, g. Click to change the document to match."*

The icon refreshes when you switch document tabs and when a document opens. It is deliberately neutral rather than alarmed when there is nothing to compare — no design open, or units that could not be read.

## How to use

### Changing the active document

1. Open the design.
2. On the **Inspect** panel, click **Match Units**.
3. A dialog confirms what changed, for example *"Document units changed from in, oz to mm, g."*

Clicking it on a document that already matches reports that and changes nothing.

### Being asked when a document opens

Off by default, because it puts a dialog on top of opening a file.

1. Open **PowerTools Preferences** from the **File** menu on the Quick Access Toolbar.
2. In the **Commands** list, find **Match Units** under **Document Tools**.
3. Tick **Ask to match units when a document is opened**.

From then on, opening a design whose units differ from your default asks:

> *"Bracket v12" is in inches and ounces.*
> *Your Fusion default units are millimeters and grams.*
>
> *Change this document to match your default units?*

**Yes** changes the document. **No** leaves it alone; nothing is remembered, so the same document asks again next time it is opened.

The question is asked a moment after the document finishes opening, not during it, so the open itself is never blocked.

### Being asked when you switch to Manufacture

Off by default. Turn on **Ask to match units when switching to the Manufacture workspace** in the same Preferences section as the open-time prompt.

Fusion keeps the Manufacture workspace's units separate from the design's, and never mentions the difference. The symptom is that feeds, speeds and toolpath dimensions are entered and displayed in the *other* unit — so a design you built in millimetres hands you inch-based feedrates, and everything still looks plausible. Autodesk's own support notes describe it as *"the dimensions appear correct, but when switched to Manufacture they change"*.

With the preference on, switching into Manufacture asks:

> *"Bracket v12" is in millimeters in the Design workspace, but the Manufacture workspace is set to inches.*
>
> *Feeds, speeds and toolpath dimensions are entered and shown in inches.*
>
> *Change the Manufacture workspace to millimeters to match the design?*

**Yes** switches Manufacture to match. **No** is remembered for the rest of the session for that document, so moving in and out of Manufacture does not nag — but it is not written to disk, so the question returns next time you open the file.

The question is asked a moment after the switch, not during it, and only when the Manufacture data actually exists. The first time you ever enter Manufacture on a document, Fusion is still creating that data, so the check quietly skips and catches it the next time you switch in.

Manufacture offers **metric or imperial**, where Design offers eleven length units. So the comparison is by family: a design in centimetres, metres or microns is all "metric" and is satisfied by Manufacture being in millimetres. Only a genuine metric-versus-imperial split is worth interrupting you for.

## Expected results

- The document's length and mass units become the ones in **Preferences › Design › Default Units**.
- Where your default is one of Fusion's named combinations — millimetre/gram, centimetre/gram, metre/kilogram, inch/ounce, foot/pound — the document's unit system is set to that combination, which is what **Document Settings** in the browser then shows. For any other pair the two units are set individually and the unit system reads *Custom*, exactly as it would if you had set them by hand.
- Only the halves that actually differ are written.
- Existing geometry, parameters and dimensions are unchanged. Units control how values are **displayed and entered**; nothing is rescaled, and a 25.4 mm hole is still a 1 in hole.

## Limitations

- Changing units is a document setting, not a timeline feature, so it is not undone by **Undo**. Run the command again, or change the units back in **Document Settings**, to reverse it.
- The prompt fires on document **open**, not on tab switch. Switching to an already-open document refreshes the icon but asks nothing.
- Only length and mass are compared, because those are the only two Fusion's default-units preference holds. Angular and time units are not part of it.
- Preferences changes apply on the next Fusion restart for enabling or disabling the command itself; both **Ask to match units** toggles take effect immediately.
- **The two checks point in opposite directions.** The document check moves the *document* towards your application default; the Manufacture check moves *Manufacture* towards the document. If your default is millimetres but the open design is in inches, answering Yes in Manufacture sets Manufacture to inches — matching the design, while the Inspect button still reports the design as disagreeing with your default. That is intended: the Manufacture check exists to stop the two halves of one document disagreeing, not to enforce your default.
- Changing the Manufacture units is not undoable through **Undo**, for the same reason as the design units. Run the command again, or change it back in Fusion.
- The Manufacture check needs the Manufacture workspace to exist on your Fusion build. Where it does not, that check is silently off and the rest of the command is unaffected.

> **Developers:** see the [architecture notes](./arch/Match%20Units.md).

---

[Back to README](../README.md)

*Copyright © 2026 IMA LLC. All rights reserved.*
