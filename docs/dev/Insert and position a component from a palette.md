# Inserting a component from an HTML palette, and landing in a position command

**Goal:** a palette (or any HTML command input) inserts a referenced component, and the
user ends up exactly where Fusion's own **Insert Component** leaves them — new occurrence
selected, view framed, position command open and ready to drag.

Tested on Fusion 2603.x, macOS and Windows, Python add-in.

---

## What Fusion's own insert actually does

**Insert Component** is not one command. Watch the Text Commands window while you insert
from the ASSEMBLY > INSERT panel and you see a chain:

```
FusionImportCommand → CommitCommand → SelectCommand → FitCommand → FusionMoveCommand
```

`Occurrences.addByInsert` is only the first two — the import and the commit. That is why
an API insert lands the component unselected at the origin: the last three steps are UI
steps, and nothing does them for you.

So you add them yourself. The step that matters:

| Final step | Command id | What the user gets |
| --- | --- | --- |
| Move/Copy | `FusionMoveCommand` | A **new Move feature** in the timeline, on top of the insert |
| Edit Initial Position | `FusionDcEditInitialPositionCommand` | Edits the placement **the insert itself recorded** — no extra feature |

Edit Initial Position is usually what you want for an insert. Note it works on a
freshly inserted occurrence even though `isGroundToParent` is `False` — Fusion's tips
text implies otherwise, ignore it.

---

## The one thing that will waste your afternoon

**You cannot start a command from inside an HTML event handler.** Not "it fails" — worse.
The command starts, appears on screen, and is then torn down when the HTML event finishes
and the palette repaints. You see a dialog flash up and vanish, taking the selection with
it.

A `customEvent` is the documented way to get off an event handler — but **firing it
inline is not enough deferral**. Fusion dispatches the handler within the same event turn,
so you are right back where you started.

What works: fire the custom event from a **short `threading.Timer`**. The worker thread's
only job is `fireCustomEvent`, which is the one `Application` call documented as safe off
the main thread. The handler still runs on the main thread — just on a turn where the HTML
event and any palette refresh are long finished.

```python
import threading
import adsk.core

app = adsk.core.Application.get()
ui = app.userInterface

FINISH_EVENT_ID = "MyAddIn_finishInsert"
FINISH_DELAY_SECONDS = 0.35

_finish_event_handler = None   # keep the handler alive for the add-in's lifetime
_pending_occurrence = None     # state handed from the HTML event to the handler


def start():
    global _finish_event_handler
    # unregister-then-register survives an add-in reload without a Fusion restart
    try:
        app.unregisterCustomEvent(FINISH_EVENT_ID)
    except Exception:
        pass
    event = app.registerCustomEvent(FINISH_EVENT_ID)
    _finish_event_handler = FinishInsertHandler()
    event.add(_finish_event_handler)


def stop():
    global _finish_event_handler
    try:
        app.unregisterCustomEvent(FINISH_EVENT_ID)
    except Exception:
        pass
    _finish_event_handler = None


class FinishInsertHandler(adsk.core.CustomEventHandler):
    def notify(self, args):
        global _pending_occurrence
        occurrence = _pending_occurrence
        _pending_occurrence = None
        if occurrence is None:
            return
        finish_insert(occurrence)


def schedule_finish(occurrence):
    """Call this from the HTML event. Do NOT start the command here."""
    global _pending_occurrence
    _pending_occurrence = occurrence
    timer = threading.Timer(FINISH_DELAY_SECONDS, _fire_finish_event)
    timer.daemon = True          # never hold Fusion open on a pending insert
    timer.start()


def _fire_finish_event():
    """Runs on the worker thread. fireCustomEvent ONLY — no other API calls.

    In particular, no logging helper that calls Application.log.
    """
    try:
        app.fireCustomEvent(FINISH_EVENT_ID)
    except Exception:
        pass
```

### `fireCustomEvent` lies about its return value

It is documented to return `True` on success. It returns **`False` while firing the event
anyway**. If you treat `False` as "never fired" and clean up your pending state, the
handler arrives a moment later to an empty slot and silently does nothing — which looks
exactly like the event never firing. Ignore the return value; only a raised exception
means it did not go out.

---

## The insert itself

Two traps, both silent:

```python
transform = adsk.core.Matrix3D.create()
occurrence = design.rootComponent.occurrences.addByInsert(data_file, transform, True)

# addByInsert returns None rather than raising when the insert fails — most often
# because the DataFile lives in a different project than the host document.
if occurrence is None:
    ui.messageBox(
        "Fusion could not insert this document.\n\n"
        "A referenced insert requires the document to be in the same project."
    )
    return

schedule_finish(occurrence)   # everything else happens on the timer's turn
```

And `Selections.add` **returns a bool** as well as being able to raise, so a selection can
fail without raising and leave every command downstream reading nothing:

```python
def select_only(entity) -> bool:
    try:
        ui.activeSelections.clear()
        added = ui.activeSelections.add(entity)   # <- check this
    except Exception as e:
        app.log(f"could not select: {e}")
        return False
    return bool(added)
```

---

## Starting the command, and knowing whether it started

Three separate things you cannot trust here:

**1. `controlDefinition.isEnabled` is meaningless for marking-menu-only commands.**
`FusionDcEditInitialPositionCommand` reports `isEnabled == False` while starting
perfectly well. These commands live only in the marking menus, and Fusion resolves that
kind of command's availability while it *builds the menu* — the standing
`ControlDefinition` is never brought up to date. (For a real ribbon button such as
`FusionFastenersCommand`, `isEnabled` **is** meaningful and worth gating on. Know which
kind you have.)

**2. `execute()` returns `True` whether or not the command appears.**

**3. `ui.activeCommand` does not update in the turn the command starts.** Read it after a
single `adsk.doEvents()` and you get `'SelectCommand'` — Fusion's idle answer — for a
command that is visibly coming up. Pump events for a few hundred ms first.

Put together:

```python
IDLE_CMD_IDS = ("", "SelectCommand")        # Fusion reports idle as the Select command
COMMAND_START_WAIT_SECONDS = 0.4

EDIT_POSITION_CMD_IDS = (
    "FusionDcEditInitialPositionCommand",   # the one that responds to a palette insert
    "FusionEditInitialPositionCommand",     # same command, kept as a build fallback
)


def finish_insert(occurrence):
    """Runs on the main thread, on a clean turn. Every step degrades on its own —
    the component is already in the assembly, so nothing here is fatal."""
    select_only(occurrence)

    try:
        app.activeViewport.fit()             # before the dialog, so it opens over a framed view
    except Exception as e:
        app.log(f"could not fit: {e}")

    # Fusion refuses the edit for some occurrences (patterned ones, for example).
    # Note the spelling — isVaild is the typo the API itself ships with.
    if getattr(occurrence, "isVaildForEditInitialPosition", None) is False:
        return

    for cmd_id in EDIT_POSITION_CMD_IDS:
        if try_start_command(cmd_id):
            break


def try_start_command(cmd_id: str) -> bool:
    """Execute cmd_id and report whether a command actually came up."""
    cmd_def = ui.commandDefinitions.itemById(cmd_id)
    if cmd_def is None:
        return False
    try:
        started = cmd_def.execute()          # operates on the current selection
    except Exception as e:
        app.log(f"{cmd_id} execute raised: {e}")
        return False

    # Give the command time to become active before believing an idle answer.
    adsk.doEvents()                          # or a pump loop for COMMAND_START_WAIT_SECONDS
    try:
        active = ui.activeCommand
    except Exception:
        return bool(started)                 # nothing to observe; trust execute()
    return active not in IDLE_CMD_IDS
```

A pump loop, if you want the full wait without freezing the UI (a bare `time.sleep`
freezes Fusion and starves its async pipelines):

```python
import time

def pump_events_for(seconds: float, tick: float = 0.03) -> None:
    end = time.monotonic() + seconds
    while True:
        adsk.doEvents()
        if time.monotonic() >= end:
            return
        time.sleep(min(tick, seconds))
```

---

## Housekeeping this creates

**A palette stays clickable while a command is open.** Ribbon buttons end the active
command for you; a palette does not. If your insert now leaves a dialog open, a second
card click would call `addByInsert` from inside that command. End it first — discarding an
uncommitted position edit is exactly what pressing Escape would do, and the click was a
deliberate move away from the dialog:

```python
def end_active_command():
    try:
        active = ui.activeCommand
    except Exception:
        return                               # older builds; let Fusion arbitrate
    if not active or active in IDLE_CMD_IDS:
        return
    try:
        ui.terminateActiveCommand()
    except Exception as e:
        app.log(f"could not end '{active}': {e}")
```

**Order your palette refresh before the command.** If you refresh the palette after
handling the message (regenerating an init script, `sendInfoToHTML`, repainting), that has
to complete *before* the command starts. The delayed fire is what keeps them apart — but
don't defeat it by refreshing on a timer of your own.

**Budget the latency.** 0.35s to defer plus 0.4s to observe is ~0.75s between the click
and the dialog. Both are tunable; 0.35 was simply the first value that worked.

---

## Checklist

1. `addByInsert` → check for `None` (silent failure = wrong project).
2. Hand the occurrence to a module-level slot; **don't** act in the HTML event.
3. `threading.Timer` → `fireCustomEvent` → your `CustomEventHandler`. Ignore the fire's
   return value. Nothing but `fireCustomEvent` on the worker thread.
4. In the handler: `activeSelections.clear()` + `add()` (**check the bool**) →
   `activeViewport.fit()` → `commandDefinition.execute()`.
5. Don't gate on `isEnabled` for marking-menu commands; observe `ui.activeCommand` after
   pumping events instead.
6. Terminate the open command when your palette starts another insert.

## Command ids worth knowing

Fusion's own definitions, greppable in
`Autodesk Fusion.app/Contents/Libraries/Applications/Fusion/Fusion/UI/FusionUI/Resources/CommandDefinitions/CommandDefinitions.xml`
(and the marking menus in `.../Resources/MarkingMenus/MarkingMenus.xml`, labels in
`Contents/Libraries/Neutron/StringTable/en-US/NaFusionUI10.xml`):

| Command | Id |
| --- | --- |
| Edit Initial Position (double-click / edit path) | `FusionDcEditInitialPositionCommand` |
| Edit Initial Position | `FusionEditInitialPositionCommand` |
| Move/Copy | `FusionMoveCommand` |
| Fasteners | `FusionFastenersCommand` |
| Import / Commit (what `addByInsert` covers) | `FusionImportCommand`, `CommitCommand` |

Those XML files are the fastest way to find any command id you need — grep the string
table for the label the user sees, then grep the command definitions for the id.

---

*Written up from the Assembly Palette command in Power Tools
(`commands/assemblypalette/entry.py`); the design notes and the dead ends behind it are in
[docs/arch/Assembly Palette.md](../arch/Assembly%20Palette.md).*

*Copyright © 2026 IMA LLC. All rights reserved.*
