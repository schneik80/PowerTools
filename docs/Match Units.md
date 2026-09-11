# Match Units

[Back to README](../README.md)

## Overview

Fusion stamps a new design with the default units set in **Preferences › Design › Default Units**, but a document keeps whatever units it was created with. Anything that arrives from somewhere else — a colleague's design, a document copied from another hub, an insert, a file created before you changed your preference — carries its own. Fusion will happily leave a millimetre design open in an inch workflow and never mention it.

**Match Units** makes that difference visible and fixes it in one click.

It has two faces:

- A **button on the Inspect panel** whose icon reports the state of the active document: a plain ruler when its units agree with your default, and a ruler with an exclamation mark when they do not. Clicking it changes the document to match.
- An optional **prompt when a document opens**, asking yes or no whether to change it.

Both compare **length and mass** — the same pair Fusion's own Default Units preference holds. A design in inches and grams does not match a default of inches and ounces, and Match Units says so.

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

## Expected results

- The document's length and mass units become the ones in **Preferences › Design › Default Units**.
- Where your default is one of Fusion's named combinations — millimetre/gram, centimetre/gram, metre/kilogram, inch/ounce, foot/pound — the document's unit system is set to that combination, which is what **Document Settings** in the browser then shows. For any other pair the two units are set individually and the unit system reads *Custom*, exactly as it would if you had set them by hand.
- Only the halves that actually differ are written.
- Existing geometry, parameters and dimensions are unchanged. Units control how values are **displayed and entered**; nothing is rescaled, and a 25.4 mm hole is still a 1 in hole.

## Limitations

- Changing units is a document setting, not a timeline feature, so it is not undone by **Undo**. Run the command again, or change the units back in **Document Settings**, to reverse it.
- The prompt fires on document **open**, not on tab switch. Switching to an already-open document refreshes the icon but asks nothing.
- Only length and mass are compared, because those are the only two Fusion's default-units preference holds. Angular and time units are not part of it.
- Preferences changes apply on the next Fusion restart for enabling or disabling the command itself; the **Ask to match units** toggle takes effect immediately.

> **Developers:** see the [architecture notes](./arch/Match%20Units.md).

---

[Back to README](../README.md)

*Copyright © 2026 IMA LLC. All rights reserved.*
