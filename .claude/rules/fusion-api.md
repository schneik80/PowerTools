---
paths:
  - "commands/**"
  - "lib/**"
  - "config.py"
  - "PowerTools.py"
---

# Fusion API rules (learned the hard way)

Each rule was paid for by a fix in this repo; the hash is the commit that
explains it. Full write-ups: `docs/dev/lessons.md`.

## Command lifecycle

- **`execute` never fires with no document open.** Fusion's command pipeline is
  document-scoped: `commandCreated` fires, `execute` does not, nothing raises.
  A command with no `CommandInputs` (QAT File-menu launchers, toggles) does
  its work in `commandCreated`. See `closealldocuments`, `datatoggle`,
  `scriptsmanager`, `preferences` (f18b911, 11cfc51).
- **Never call `args.command.doExecute()` from `commandCreated`.** It runs
  inside `CommandDefinition::createCommand`; either argument re-enters the
  command manager on a half-built command and segfaults Fusion. Bail out with
  `_command_abort.abort_before_dialog()`, add no inputs, return; then
  `consume_abort()` in `execute` and `clear_abort()` in `destroy`. An AST test
  fails CI otherwise (14871d7, a90be46, 5bae0e3).
  - **Do not over-apply this.** The ban is scoped to that one callback;
    `doExecute` is still correct from `inputChanged` and from deferred custom
    events. Three sites are deliberate and must survive a cleanup pass:
    `changecyclecolor._enter_custom_color_flow` (dismiss the swatch dialog
    after the native picker), `refrences.on_input_changed`
    (`parentCommand.doExecute(False)`), and
    `sketchcirclecenterpoint.custom_event_commit` (deferred out of the
    mouse-event stack, which raises `RuntimeError` if called inline). The AST
    guard only inspects `command_created` handlers, so it permits these.
  - **After an abort, `execute` still fires** — Fusion auto-executes an
    input-less command. Module-level state outlives the invocation, so an
    unguarded execute acts on the *previous* run's data; that is what
    `consume_abort`/`clear_abort` exist for (5bae0e3).
- **Never close a document inside a command event** -- do it from
  `commandCreated` after the command terminates, and pump events after each
  close (11cfc51).
- **QAT controls placed in `start()` can silently fail** when Fusion starts
  with no document. Make placement idempotent and retry from
  `documentActivated` (`preferences._ensure_control`, 2afdbe1).
- **`start()`/`stop()` must be idempotent** and sweep stale controls; register
  a control into one tab only (3b92f3f).
- **Never delete a built-in Fusion tab or panel**; only remove your own
  controls (`config.py`, `measurepath`, `animationnamedview`).

## Events, threads, crashes

- **Never loop `adsk.doEvents()` inside a command handler** -- re-entrancy
  crash vector (ce4e768). One `doEvents()` to repaint a busy indicator during a
  read-only scan is the most that is safe (76b9523).
- **Never `time.sleep()` on the UI thread.** Use `ptutil.pump_events_for(seconds)`
  so the UI and Fusion's upload pipeline keep moving (f0ff1af).
- **Handles held across a pumped wait can be invalidated by background
  data-model work and fault natively (0xC0000005), not raise.** Re-acquire
  `app.activeDocument`/the `Design` after any pumped wait; check
  `Document.isValid` before every close; suspend autosave for long save/close
  runs (`bottomupupdate._suspend_autosave`, a1d22e1, 0a228c8, 20c0976).
- **The Fusion Data API is main-thread only.** A `threading.Timer` worker may
  call exactly one thing: `app.fireCustomEvent(...)`. Not `ptutil.log`, not
  the API (266e2c2, c440ad3).
- **Do not read the document model from an application event handler** --
  `Document.documentReferences` / `Document.dataFile` on `documentActivated`,
  `documentSaved` and friends can walk the document graph while Fusion's
  background saver serialises it, aborting the saver thread
  (`Ns::_AutoSaveTask` -> `SegmentSaver::save` -> `doSave` ->
  `std::terminate`). `documentSaved` is the worst case: it fires during a save.
  Defer the work through `fireCustomEvent` + `threading.Timer`. This parked the
  Assembly Palette gallery auto-refresh -- see
  `docs/arch/Assembly Palette.md`, "Attempted and parked".
- **Starting a Fusion command from a palette `incomingFromHTML` handler needs
  a later main-loop turn**: `threading.Timer` -> `fireCustomEvent` -> handler.
  Firing the custom event inline is not enough (c440ad3,
  `docs/dev/Insert and position a component from a palette.md`).
- **`fireCustomEvent` returns `False` even on success** -- only a raise means
  it failed. **`controlDefinition.isEnabled` is meaningless for marking-menu
  commands.** **`ui.activeCommand` does not update in the turn a command
  starts** -- pump first (c440ad3).
- **`adsk.core.Future` has no completion event.** Poll from a timer-fired
  custom event, few resolutions per tick, with a timeout and a negative cache
  (`assemblypalette` thumbnails, 14f42ca). Never poll inline in a palette.

## Dialogs, selections, graphics

- **`SelectionCommandInput` is not reliably readable from `execute`.** Capture
  with `ptutil.capture_selections()` in `inputChanged`/`validateInputs` and
  read `ptutil.picked()` later (a91da41).
- **Custom graphics survive only when created in `executePreview`.** Built in
  `inputChanged` or a mouse handler they flash and vanish with no error. Do not
  "fix" it with `isValidResult = True` (that skips `execute`). Read
  `docs/dev/Custom graphics that stay painted.md` before drawing (b3bed5f).
- **A stale number on screen is worse than an error.** If a rebuild fails,
  clear the previous result and say so (c8c0382).
- **Collections may be `None`, not empty** (`SketchPoint.connectedEntities`,
  `BRepVertex.edges`). Iterate through a guard (c8c0382).
- **`SketchPoint.worldGeometry` returns the origin for some point types** --
  use `sketch.sketchToModelSpace()` (`measurepath`, `sketchcirclecenterpoint`).
- **`addByInsert` returns `None` on failure instead of raising** (6772f31).

## Data, cloud, IDs

- **`app.data.activeProject` raises `InternalValidationError('id.size()')`**
  when the Data Panel has no project in context. Go through
  `cache_utils.get_active_project()` / `resolve_target_folder()`. Exceptions
  inside `incomingFromHTML` are swallowed by DEBUG-gated `handle_error`, so an
  unguarded call reads as "nothing happens" (7535954).
- **MFGDM GraphQL needs `component.hub.id` (`urn:adsk...`)**, never
  `app.data.activeHub.id`; and model-id access must not run from
  `commandCreated` (`partnumber_shared/mfgdm_props.py`, 234b043).
- **Fusion IDs use underscores, never hyphens** (hyphens log "invalid
  characters" on every launch). Renaming a `CMD_ID` orphans users' QAT pins
  (6789216).
- **Never hardcode Autodesk paths or unpublished workspace IDs.** Probe
  candidates, log what was found under DEBUG. Animation is internally
  `Publisher3DEnvironment` (af05499, `fusion_recents._root_candidates`).
- **`os.access` lies on Windows network shares** -- probe by writing (14f42ca).
- **Fusion never backfills an empty `docstruct`** -- treat `""` as final.

## Logging and imports

- **`ptutil.log` is a no-op without the `.debug` marker**, and `handle_error`
  logs through it. Absence of a traceback is not evidence a handler ran
  (f18b911). Say in the commit when a change is "not yet exercised in Fusion".
- **`lib/ptAddInUtils/__init__.py` import order is load-bearing**
  (`general_utils` first; `# ruff: noqa: I001`) (0b179cd).
- **`config.py` imports ptutil before it defines `DEBUG`/`CACHE_PATH`.** Never
  read `config` flags at import time in a ptutil module; resolve lazily
  (`general_utils._refresh_flags`, 018f0c7).
- **Use `except Exception:`**, never bare `except:` (1feb976). Keep
  intentional no-op property touches explicit with `_ = ...` (B018, 79ca8e3).
