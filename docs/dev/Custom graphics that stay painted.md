# Custom graphics that stay painted

**Goal:** draw a highlight, marker, or manipulator in the viewport from inside a command
dialog and have it *stay on screen* — not flash and vanish.

If your graphics appear for a frame and disappear, you are almost certainly hitting the
preview transaction. Skip to [The mechanism](#the-mechanism).

Written against Fusion 2603.x, macOS and Windows, Python add-in.

---

## The symptom

You create a `CustomGraphicsGroup`, add curves or bodies to it, call
`activeViewport.refresh()`, and the result is visibly drawn — then gone. Sometimes it
survives long enough to see a flicker; sometimes it only shows up if you drag the dialog.
Nothing throws. `ptutil.log` shows your draw code ran exactly once, successfully.

This has bitten this codebase more than once. It is why
`commands/sketchcirclecenterpoint` shipped in `settings_store.DEFAULT_DISABLED_COMMANDS`.

## The mechanism

From Autodesk's own documentation on the `executePreview` event:

> Whatever you construct in the `executePreview` is all built within a single transaction.
> When the next `executePreview` is fired that transaction is aborted (the equivalent of
> an undo) so you can construct the next preview.

Custom graphics are part of the document, so they are part of that transaction. The
sequence that burns you:

1. Your `inputChanged` (or `mouseMove`) handler runs and creates graphics.
2. Fusion fires a preview cycle immediately afterwards.
3. That cycle **aborts the transaction your graphics were created in** — an undo.
4. Your graphics are gone. Nothing errored, because nothing went wrong.

The graphics were never "unreliable". They were undone, on purpose, by design.

## The rule

> **Create custom graphics only inside `executePreview`. Nowhere else.**

Every other handler should update *state* and then let a preview cycle do the drawing.
Graphics created inside `executePreview` live in the current preview transaction and
survive until the next cycle, which redraws them from that state.

```python
# entry.py — the only place graphics are created
def command_execute_preview(args: adsk.core.CommandEventArgs) -> None:
    _clear_graphics()
    if _markers_wanted:
        _draw_markers()          # customGraphicsGroups.add() lives in here
    adsk.core.Application.get().activeViewport.refresh()


def command_input_changed(args: adsk.core.InputChangedEventArgs) -> None:
    _recompute_state(args.inputs)   # NO drawing here
    # Fusion fires executePreview by itself after an input changes.
```

Deleting graphics outside a preview is harmless — only *creation* is at risk. So a
`_clear_graphics()` on a deselect path or in `command_destroy` is fine.

### Forcing a cycle after a mouse-driven change

Fusion fires `executePreview` on its own after an input changes, but not after a state
change that came from a raw mouse click. Ask for one:

```python
try:
    _active_command.doExecutePreview()
except Exception:
    # Not fatal — an input-driven change gets its own preview anyway.
    ptutil.log(f"{CMD_NAME}: doExecutePreview unavailable here")
```

Guard it. `doExecute()` is documented as unusable from inside a command event handler
(see the `_COMMIT_EVENT_ID` custom-event dance in `commands/sketchcirclecenterpoint`), and
`doExecutePreview()` should be treated with the same suspicion until proven on your build.

## Do not "fix" this with `isValidResult = True`

This is the common cargo-cult repair and it is usually wrong. From the docs:

> If it is set to `True` then the `execute` event is skipped and the last result of the
> `executePreview` is used as the final result.

So setting it True **skips your `execute` handler entirely**. If `execute` is where you
copy a result to the clipboard, write an attribute, or log, that silently stops happening.

Set `isValidResult = True` only when `executePreview` genuinely built the document geometry
you want to keep — which is why `commands/roundsketchdimensions` sets it (it edits real
dimensions in the preview) and why a graphics-only command must not.

## Better still: do not use custom graphics for highlighting

If all you need is to highlight *existing* entities, custom graphics are the wrong tool.
Use a selection input:

```python
# Highlight-only input: limits 0,0 so it never takes focus or blocks OK.
sel = inputs.addSelectionInput("xx_highlight", "Path", "")
sel.addSelectionFilter("Edges")
sel.setSelectionLimits(0, 0)

# later
sel.clearSelection()
for entity in entities:
    sel.addSelection(entity)
```

`ui.activeSelections` does **not** highlight while a command dialog is open, but
`SelectionCommandInput.addSelection()` does. Selection state is not part of the preview
transaction, so it cannot be undone out from under you. This is native Fusion highlighting
— correct colour, correct depth behaviour, zero maintenance.

Prior art: `commands/inferconstraints/entry.py` (the `Highlighted pair` input) and
`commands/measurepath/entry.py` (`_highlight()`).

Reserve custom graphics for things that have no entity to select — markers in empty space,
manipulator handles, dimension leaders.

## Hover feedback: mutate, do not rebuild

Deleting and re-adding graphics on every `mouseMove` is its own flicker source, separate
from the transaction problem, and it is wasteful. Keep references to the entities and set
properties in place:

```python
for key, marker in _sphere_gfx.items():
    marker.color = hover_color if key == _hover_key else base_color
adsk.core.Application.get().activeViewport.refresh()
```

Setting `color`, `isVisible`, or `transform` on a live `CustomGraphicsEntity` touches no
transaction. Wrap it — the reference goes stale after a preview rebuilds the group, in
which case the next cycle repaints with the right colour anyway.

## Housekeeping that is still required

- **Tag the group, never cache it.** Set `group.id = f"{CMD_ID}_gfx"` and find your groups
  by that tag. A cached reference goes stale across preview cycles and edit-state changes.
- **Delete in reverse.** Indices shift as you remove:

  ```python
  groups = design.rootComponent.customGraphicsGroups
  for i in range(groups.count - 1, -1, -1):
      if groups.item(i).id == _GFX_TAG:
          groups.item(i).deleteMe()
  ```

- **Clear in `command_destroy`**, and defensively in `stop()`, or a stale group is left in
  the user's document.
- **`group.isSelectable = False`** if the graphics sit on top of geometry the user still
  needs to pick. There is no `CustomGraphics` selection filter, so an overlay can only get
  in the way of picking, never help it.
- **Do not gate the preview behind `validateInputs`.** If `args.areInputsValid` is `False`,
  the preview may not fire — and your graphics stop being drawn. If you want OK disabled
  while the dialog is in an intermediate state, prefer letting `execute` no-op instead.

## Checklist

1. Is `customGraphicsGroups.add()` reachable from anywhere other than `executePreview`?
   Fix that first — it is the bug.
2. Is `executePreview` actually registered on the command?
3. Are you redrawing from state on *every* preview, rather than assuming last frame
   survived?
4. Did you set `isValidResult = True`? If `execute` still needs to run, that is a bug.
5. Could a selection input do the highlighting instead of graphics at all?
6. Is hover recolouring in place rather than rebuilding?
7. Is the group tagged with an `id`, deleted in reverse, and cleared on destroy?

## Known outstanding: `sketchcirclecenterpoint`

`commands/sketchcirclecenterpoint/entry.py` gets the `executePreview` half right — line 392
redraws from the preview handler, and line 382 correctly leaves `isValidResult = False`.
Its bug is a **redundant direct draw**: `command_mouse_move` writes the live radius into the
`diameter` value input (which by itself triggers a preview that redraws), and *then* calls
`_update_preview(radius, hit)` again at line 299. That second, direct draw happens outside a
preview cycle and is promptly aborted — so the two fight, and the result is the flicker.

Removing the direct `_update_preview` call from `command_mouse_move` is the likely fix, and
would let that command come out of `DEFAULT_DISABLED_COMMANDS`. **Not yet verified in
Fusion** — treat it as a lead, not a finished repair.

---

*See also: [`commands/measurepath/entry.py`](../../commands/measurepath/entry.py) for a
command built to this rule from the start, and
[Measure Path](../Measure%20Path.md) for what it does.*

*Copyright © 2026 IMA LLC. All rights reserved.*
