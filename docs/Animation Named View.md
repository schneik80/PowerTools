# Save Named View

[Back to README](../README.md)

## Overview

Save Named View saves the current Animation viewport camera as a named view on the design, named from the active storyboard.

Named views belong to the design, not to the animation, so a view saved here is available everywhere the design is, including the Design workspace browser and drawing views. Fusion has no way to save one from inside Animation; you would have to switch workspaces, reframe, and hope to match the storyboard camera. This command captures the framing where you are, which is what you want after composing an exploded view in Animation.

## Prerequisites

- A design document must be open.
- Your Fusion build must have the Animation workspace. Where it does not, the command skips its UI and the rest of PowerTools starts normally.

## Where to find it

**Animation** workspace › **Animation** tab › **Power Tools** panel › **Save Named View**. The panel is placed directly after Fusion's **View** panel.

## How to use

1. Orbit the viewport to the framing you want to keep.
2. Select **Save Named View**.
3. Leave **Auto-name from storyboard** ticked, or untick it and type a **Name**.
4. Select **Save View**. The save is silent; you are interrupted only if something went wrong.
5. Switch to the Design workspace and find the view under **Named Views** in the browser.
6. Save the document; named views persist only with it.

## Options

| Option | Default | Effect |
|---|---|---|
| **Auto-name from storyboard** | On | Names the view from the active storyboard and playhead, for example `Storyboard2 @ 3.50s`, or `@ scratch` when the playhead is parked in the scratch zone |
| **Name** | — | Enabled when auto-naming is off; your own name for the view. Left empty, the auto name is used |

## Naming

- With auto-naming, running the command again at the same storyboard and playhead updates the existing view in place rather than adding a second one; the name encodes the point in the storyboard, so a collision means the same view. Reframe, run again, and the view follows. Move the playhead, or type a name, to get a separate view.
- A name you typed is never overwritten: if it is in use, a `-2`, `-3` suffix is added.
- Fusion does not expose a storyboard's name to add-ins. The command works it out from the storyboard's position: an unrenamed storyboard is named as Fusion names it (`Storyboard2`); a renamed one gets a positional label with a space (`Storyboard 2`), so the two cases can be told apart. With no active storyboard the label is `Animation`.
- The standard view names (`TOP`, `FRONT`, `RIGHT`, `HOME`) are treated as taken and get a suffix.

## Verification

After saving, the command reads the camera back off the new view and compares it with the viewport camera it submitted. If they differ, it warns you and suggests switching to an orthographic view; this guards against a Fusion defect in which saving a perspective camera can store a view whose eye position is far from the original.

## Troubleshooting

| Problem | Cause and fix |
|---|---|
| The command does not appear | Your build has no Animation workspace, or the Animation group is disabled in PowerTools Preferences |
| The panel is at the end of the tab, not after **View** | Your build names the View panel differently; the command still works |
| The name is `Storyboard 2`, not `Storyboard2` | The storyboard was renamed; the positional fallback was used |
| Nothing seems to happen on save | Expected; a successful save is silent. Check **Named Views** in the Design workspace |
| A second run replaced my view | Expected with auto-naming at the same storyboard and playhead. Move the playhead or type a name |
| A typed name came out with a `-2` suffix | That name was in use; typed names are suffixed rather than overwritten |
| A warning that the saved camera differs | Switch the viewport to an orthographic view and save again |
| Named views vanish after closing | Save the document |

> **Developers:** see the [architecture notes](./arch/Animation%20Named%20View.md).

---

[Back to README](../README.md)

*Copyright © 2026 IMA LLC. All rights reserved.*
