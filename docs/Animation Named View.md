# Animation Named View

[Back to README](../README.md)

## Overview

The **Save Named View** command saves the current Animation viewport camera as a **named view on the design**, naming it from the active animation storyboard.

Named views belong to the design, not to the animation, so a view saved here is available everywhere the design is — including the Design workspace browser and drawing views. This command exists so you can capture a framing while you are working in Animation, without switching workspaces to do it.

## Prerequisites

- A design document must be open in Autodesk Fusion.
- The **Animation** workspace must be available on your Fusion build.

## Access

1. Open a design document in Autodesk Fusion.
2. Switch to the **Animation** workspace.
3. On the **Animation** tab, find the **Power Tools** panel — it sits directly after the **View** panel, before **Publish**.
4. Select **Save Named View**.

The command adds its own panel to Fusion's existing Animation tab; it does not add a tab of its own. If your Fusion build has no Animation environment, the command silently skips its UI and the rest of PowerTools starts normally.

## How to use

1. Orbit the viewport to the framing you want to keep.
2. Run **Save Named View** from the **Power Tools** panel.
3. Choose the name:

   | Option | Effect |
   | --- | --- |
   | **Auto-name from storyboard** (default) | Names the view from the active storyboard and playhead, e.g. `Storyboard2 @ 3.50s` |
   | Unticked | Enables the **Name** field so you can type your own name |

4. Select **Save View**. The save is silent — there is no confirmation dialog. You are only interrupted if something went wrong.
5. Switch to the **Design** workspace and find the view under **Named Views** in the browser.
6. **Save the document** — named views persist only with the document.

### Re-saving the same view

With auto-naming on, running the command again at the **same storyboard and playhead** **updates the existing named view in place** rather than creating a second one. The name encodes the storyboard and the playhead, so a collision means the same point in the same storyboard — that is the same view, and re-saving it should move it.

This makes the command usable as a "nudge and re-save" tool: reframe the viewport, run it again, and the view at that playhead follows.

A name you typed yourself is **not** treated this way. It gets a numbered suffix instead, so a view you named deliberately is never silently overwritten.

## Naming behaviour

Fusion's API has a gap here: a `Storyboard` object has **no readable name**. Names exist (the collection can look one up by name) but cannot be read back off a storyboard.

The command works around this:

1. It finds the active storyboard's position in the collection.
2. It asks the collection for Fusion's default name for that slot (`Storyboard2`) and confirms the storyboard that comes back is the active one. If so, that is the real name.
3. If you have **renamed** the storyboard, step 2 correctly fails and the command falls back to a positional label with a space — `Storyboard 2` — so you can tell the two cases apart.
4. The playhead is appended (`@ 3.50s`, or `@ scratch` when parked in the scratch zone), since a storyboard is normally sampled at several points.
5. An auto-generated name that already exists **updates that view** (see above). A hand-typed name that already exists is de-duplicated with a `-2`, `-3` suffix. The four standard views (`TOP`, `FRONT`, `RIGHT`, `HOME`) are rejected as names, because Fusion hides them from name lookups and would otherwise fail the save.

> **Note on collision detection:** `NamedViews.itemByName` is documented to return null for a name that is not in use, but it does not reliably do so. A lookup that fails, or that answers with something other than a view of the requested name, is therefore treated as *free*, and `add()` is left to reject a genuine duplicate. Treating an unusable answer as "taken" instead made every candidate look taken and produced names suffixed `-999`.

## Verification of the saved view

After saving, the command reads the camera back off the new named view and compares it against the viewport camera it submitted. If they differ, it warns you and suggests switching to an orthographic view.

This guards against a [reported Fusion defect](https://forums.autodesk.com/t5/fusion-api-and-scripts/bug-impossible-to-save-named-view-with-perspective-camera/td-p/13076099) where saving a **perspective** camera can store a view whose eye position is far from the original. It did not reproduce on Fusion 2704.1.36, but it is cheap to check and a silently wrong view is worse than a warning.

## Implementation note

While the Animation workspace is active, `app.activeProduct` is **not** the design — `adsk.fusion.Design.cast(app.activeProduct)` returns `None` there. The design has to be looked up on the document's product list instead:

```python
design = adsk.fusion.Design.cast(
    app.activeDocument.products.itemByProductType("DesignProductType")
)
design.namedViews.add(app.activeViewport.camera, name)
```

This was established by probing the live API across five approaches on Fusion 2704.1.36. Four worked with exact camera fidelity; only the `activeProduct` path failed. Switching to the Design workspace to save and switching back also worked, but is unnecessary.

Note also that `NamedViews` and `NamedView` live in **`adsk.core`**, not `adsk.fusion`, and that `add()` takes the **camera first** and the name second.

## Troubleshooting

| Problem | Cause and fix |
| --- | --- |
| The command does not appear | Your build may have no Animation workspace, or the Animation group is disabled in PowerTools Preferences. |
| The panel is at the end of the tab, not after **View** | Your build names the View panel differently, so no anchor was matched. The resolved tab and panel IDs are in the debug log; the names matched against are `config.animation_after_panel_names`. |
| `No design was found for the active document` | Open a design document before running the command. |
| The name is `Animation View` | No active storyboard could be read. The view is still saved. |
| The name is `Storyboard 2`, not `Storyboard2` | The storyboard has been renamed; the API cannot read the new name, so the positional fallback was used. |
| Nothing appears to happen when I save | Expected — a successful save is silent. Check **Named Views** in the Design workspace browser, or `cache/powertools-debug.log`. |
| A second run replaced my view instead of adding one | Expected with auto-naming at the same storyboard and playhead — that is the same view, so it is updated. Move the playhead, or untick **Auto-name** and type a name, to get a separate view. |
| A hand-typed name came out with a `-2` suffix | That name was already in use. Typed names are suffixed rather than overwritten, so an existing view is never lost. |
| A warning about the saved camera differing | The Fusion perspective-camera defect. Switch the viewport to an orthographic view and save again. |
| Named views vanish after closing | Named views are stored in the document — save it. |

## Diagnostics

Detailed logging is written to `cache/powertools-debug.log` when debug logging is enabled (a `.debug` marker file in the add-in root).

Fusion publishes none of the Animation workspace's UI IDs — not the workspace, not its tab, not its panels. They are absent from the API documentation and from the shipped binaries, so all three are resolved at runtime: the workspace by ID candidates then by name, and the tab and anchor panel by display name. The log records every workspace, tab, and panel it saw along with the IDs it settled on, so the real values can be read off rather than guessed at.
