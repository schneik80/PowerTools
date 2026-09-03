# Symptom index

Fusion fails in ways that do not name their cause: no traceback, a silently
skipped callback, graphics that flash and vanish, a hard segfault. Every row
below is a symptom this repo has already diagnosed once. Start here, then read
the linked rule or `docs/dev/lessons.md` section for the reasoning.

This is an index, not the explanation — the hashes are `git show`-able.

## Nothing happens

| Symptom | Cause | Do this |
|---|---|---|
| `execute` never fires; `commandCreated` did | **No document is open.** Fusion's command pipeline is document-scoped and nothing raises | Do the work in `commandCreated` for commands with no inputs (`f18b911`, `11cfc51`) |
| A palette button does nothing, no error | A raise inside `incomingFromHTML` is **swallowed** by DEBUG-gated `handle_error` | Guard every Fusion call in the handler and post an explicit error back to the page (`7535954`) |
| No traceback, so "the handler never ran" | `ptutil.log()` is a **no-op without the `.debug` marker** | Create `.debug` in the repo root and retry before concluding anything (`f18b911`) |
| A Fusion command started from a palette never appears | Fired inline from the HTML event; the command is torn down when that event finishes | `threading.Timer` → `app.fireCustomEvent` → handler, so it lands on a later main-loop turn (`c440ad3`) |
| A QAT/ribbon control is missing after launch | Fusion started with **no document**; placement in `start()` silently failed | Make placement idempotent and retry from `documentActivated` (`2afdbe1`) |
| A user's enable/disable state for a command reset itself | The command or folder was renamed without a migration | Add `old: new` to `settings_store.RENAMED_COMMANDS` (`7dee722`) |
| A user's QAT pin vanished | `CMD_ID` changed — pins are keyed on it | Avoid renaming `CMD_ID`; note it in the commit if unavoidable (`6789216`) |
| Command tooltip/description is blank | `CMD_DESCRIPTION` (all caps) is silently ignored | Use exactly `CMD_Description`, ASCII, text taken from `docs/` (`aa6802e`) |
| The whole add-in fails to load | A command folder was nested instead of top-level under `commands/`, breaking relative imports | Keep every command folder directly under `commands/` (`14abc78`) |

## Fusion crashes

A native fault means **no Python exception**. Read the CER stack
([`environment.md`](environment.md#reading-a-crash)) before theorising.

| Symptom | Cause | Do this |
|---|---|---|
| Segfault on dismissing a command; stack shows `doOnCreateCommand` under `createCommand` | `args.command.doExecute()` called from `command_created` — re-enters the command manager on a half-built command | Build **no inputs** and return; `Command.isAutoExecute` ends it. Use `commands/_command_abort.py`. See [the doExecute rule](#the-doexecute-rule-read-before-touching-it) (`14871d7`, `a90be46`, `5bae0e3`) |
| Crash or freeze inside a handler | `adsk.doEvents()` looped inside a command handler — re-entrancy vector | Use `ptutil.pump_events_for(seconds)`; one bare `doEvents()` to repaint a busy indicator is the most that is safe (`ce4e768`, `76b9523`) |
| UI frozen during a long run | `time.sleep()` on the UI thread | `ptutil.pump_events_for()` so the UI and the upload pipeline keep moving (`f0ff1af`) |
| Fault (`0xC0000005`) after a save/close loop | A `Document`/`Design` handle held **across a pumped wait** was invalidated by background data-model work | Re-acquire handles after every pumped wait, check `Document.isValid` before each close, suspend autosave for long runs (`a1d22e1`, `0a228c8`, `20c0976`) |
| Crash when a background thread touches Fusion | The Data API is **main-thread only** | From a `threading.Timer`, call *only* `app.fireCustomEvent(...)` — not `ptutil.log`, not the API (`266e2c2`, `c440ad3`) |
| Crash closing a document | A document was closed inside a command event | Close from `commandCreated` after the command terminates, pumping events after each close (`11cfc51`) |
| `RuntimeError` from `doExecute` in a mouse handler | `doExecute` is not legal from the mouse-event stack | Defer it through a custom event (`sketchcirclecenterpoint/entry.py`) |

## Wrong or missing output

| Symptom | Cause | Do this |
|---|---|---|
| Custom graphics flash for a frame and vanish | Built outside `executePreview` | Create them **only** in `executePreview`. Do **not** "fix" it with `isValidResult = True` — that skips `execute`. Read [Custom graphics that stay painted](../docs/dev/Custom%20graphics%20that%20stay%20painted.md) first (`b3bed5f`) |
| Selections read as empty in `execute` | `SelectionCommandInput` is not reliably readable there | `ptutil.capture_selections()` in `inputChanged`/`validateInputs`, then `ptutil.picked()` (`a91da41`) |
| `TypeError: NoneType is not iterable` over a collection | Fusion collections may be `None`, not empty (`SketchPoint.connectedEntities`, `BRepVertex.edges`) | Iterate through a guard (`c8c0382`) |
| A sketch point's coordinates are the origin | `SketchPoint.worldGeometry` returns the origin for some point types | `sketch.sketchToModelSpace()` (`measurepath`, `sketchcirclecenterpoint`) |
| An insert silently did nothing | `addByInsert` returns `None` on failure instead of raising | Check the return value (`6772f31`) |
| A stale number stays on screen after a failed rebuild | Result not cleared on the failure path | Clear it and say so — a plausible wrong number is worse than an error (`c8c0382`) |
| A command acts on the *previous* run's data | Module-level state outlived the invocation; an aborted `command_created` still auto-executes | Scrub state on abort — `abort_before_dialog` / `consume_abort` / `clear_abort` (`5bae0e3`) |
| Palette thumbnails blank or never load | Galleries ship metadata, not images; `adsk.core.Future` has **no completion event** | Lazy-request (IntersectionObserver + batches) and poll from a timer-fired custom event with a timeout and a negative cache — never inline in the palette (`14f42ca`) |
| Palette scrollbars unstyled | `scrollbar-width`/`scrollbar-color` make Chromium ignore the `-webkit-` pseudo-elements | Use `-webkit-` pseudo-elements only (`f104dcc`) |

## Data, cloud, identity

| Symptom | Cause | Do this |
|---|---|---|
| `InternalValidationError('id.size()')` | `app.data.activeProject` raises when the Data Panel has no project in context | Go through `cache_utils.get_active_project()` / `resolve_target_folder()` (`7535954`) |
| MFGDM GraphQL returns nothing / wrong hub | Used `app.data.activeHub.id` | Use `component.hub.id` (`urn:adsk...`); model-id access must not run from `commandCreated` (`234b043`) |
| "Invalid characters" logged on every launch | A Fusion ID contains a hyphen | Fusion IDs use `_` only (`6789216`) |
| A workspace lookup by ID fails | The ID is unpublished or guessed | Probe candidates and log what resolved. Animation is internally `Publisher3DEnvironment` (`af05499`) |
| A write fails on a Windows network share after a successful check | `os.access` **lies** on Windows shares | Probe by writing (`14f42ca`) |
| Case comparison works on macOS, fails on Linux CI | `os.path.normcase` only folds case on Windows | `.casefold()` explicitly (`4cb4901`) |

## CI is red

| Symptom | Cause | Do this |
|---|---|---|
| `ruff format --check` fails but the code looks fine | Local ruff version ≠ the `ci.yml` pin | Match the pin — see [`environment.md`](environment.md#two-invocation-traps-on-mac-air-m4) (`ef424c6`, `ef14b11`) |
| `test_no_command_created_calls_do_execute` fails | You added a `doExecute` call inside a `command_created` handler | Use `commands/_command_abort.py` instead (`a90be46`) |
| `test_readme_pdf_build` or the PDF gate fails | `README.md` changed without rebuilding `README.pdf` | `python3 tools/pandoc/build_readme_pdf.py`, stage both. Never `--skip-audit` (`48722db`, `28188f7`) |
| `test_release_build` fails | Ship/strip list changed without the test | Update `tools/release/build_release.py` and `tests/test_release_build.py` in the same commit (`1cb6d3e`) |
| `No module named pytest` | On `mac-air-m4`, pytest is only in the project venv — `python`/`python3` do not have it | `.venv/bin/python -m pytest -q` ([roster](environment.md#device-roster)) |

## The doExecute rule, read before touching it

The rule is narrow and easy to over-apply. **`doExecute` is banned from exactly
one callback — `command_created`** — because that callback runs inside
`CommandDefinition::createCommand`, so either argument re-enters the command
manager on a half-constructed command and segfaults Fusion.

It remains the correct mechanism from contexts *outside* `createCommand`, and
**three call sites are deliberate — do not remove them in a cleanup pass**:

| Site | Context |
|---|---|
| `commands/changecyclecolor/entry.py` `_enter_custom_color_flow` | Dismisses the swatch dialog after the native picker returns |
| `commands/refrences/entry.py` `on_input_changed` | `parentCommand.doExecute(False)` from `inputChanged` |
| `commands/sketchcirclecenterpoint/entry.py` `custom_event_commit` | Deferred through a custom event to escape the mouse-event stack |

`tests/test_command_abort.py` is an AST guard scoped to `command_created`
handlers only, so it permits these three. The 13 sites fixed in `14871d7` /
`a90be46` / `5bae0e3` were all the *abort* shape — precondition fails →
`messageBox` → `doExecute` → immediate `return` with zero inputs built. If you
find a `doExecute` that is genuinely trampolining into an execute transaction
from outside `createCommand`, leave it alone.

---
*Copyright © 2026 IMA LLC. All rights reserved.*
