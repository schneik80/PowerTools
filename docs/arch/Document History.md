# Document History — Architecture

[← Document History guide](../Document%20History.md)

## Architecture

A QAT button that opens an HTML palette. The palette draws the active document's version history as a stack of day rows — one row per local calendar day, newest first, split into a track per author, with saves placed on a 00:00–24:00 clock axis and the elapsed time called out between rows.

It replaces the original behaviour, which selected the root component and ran Fusion's built-in `ShowHistoryCmd`. That panel is a single undifferentiated strip: it cannot say who saved what, how a working day was shaped, or how long the design sat untouched, which are the questions this view exists to answer. The presentation is a port of the History timeline in the adjacent FusionOnPremServer web app, so the same history reads the same way in both places.

### Command ID

`PTND_history` — unchanged from the `ShowHistoryCmd` version, deliberately: renaming a `CMD_ID` orphans every user's saved QAT pin (6789216).

### Files

| File | Holds |
|---|---|
| `entry.py` | Fusion contact only: lifecycle, reading the versions, serving the page, the thumbnail pump. |
| `history_model.py` | The bucketing — day rows, author tracks, gaps, the calendar arithmetic behind the elapsed-time labels. `adsk`-free and unit-tested. |
| `resources/html/{index.html,style.css,app.js}` | The drawing, plus the width-dependent geometry. |
| `tests/test_dochistory_history_model.py` | A port of the vitest suite covering the same bucketing in the web app, so the two presentations cannot drift apart in what they claim about a history. |

### Where the layout maths lives, and why it is split

The bucketing is in Python because it is where a plausible wrong number would come from — which day a save belongs to, which track, how many days two rows are apart — and the repo rule is that such logic lives in an `adsk`-free module with tests.

The geometry is in `app.js` because all of it depends on the panel width the browser measures (`ResizeObserver` on the scroll container). Sending a width to Python and a layout back would put a round trip in the middle of a drag. Its port was verified locally against the same vitest cases; CI cannot run it, because CI installs nothing but ruff and pytest.

Constants therefore live on exactly one side: `TRACKS_PER_DAY_CAP` with the bucketing, `DAY_ROWS_CAP` and every pixel value with the drawing.

### Execution flow

1. `start()` registers the command definition and inserts the button before the QAT **Save** control, then registers the custom event that drives the thumbnail pump.
2. `command_created` opens the palette directly. Not from `execute`: this command has no `CommandInputs`, and `execute` only fires when Fusion runs a command through its document-scoped pipeline, so with no document open the button would be live and nothing would happen (f18b911, 11cfc51). It bails out on no document and on an unsaved one (`ptutil.isSaved`).
3. `_gather_history()` reads the versions behind `ui.progressBar.showBusy` and returns the whole page state. This happens **before** the palette is created, and the result is written into `init.js` (generated, git-ignored), so the first paint already has the history.
4. `_show_palette()` pushes fresh history to an already-open palette instead of rebuilding it, so the thread toggle and scroll position survive a re-click. A closed palette is deleted by `_palette_closed`, so an `itemById` miss really means "not open" and never the torn-down husk that makes `isVisible` a silent no-op.
5. The page sends `htmlReady` once loaded, which pushes `setHistory` from `_last_state` — the read that has just happened, not a new one. That exists only to defeat Fusion's embedded browser caching `init.js` by URL across palette recreations on Windows, the trap the Assembly Palette already hit.
6. The page requests a thumbnail only for the version the pointer rests on, and the pump answers it.

### Why the page never waits on Python

This palette first shipped with the read behind the handshake: `init.js` carried only the theme, the page painted a "Reading version history…" banner and asked for the data, and the answer never arrived. The DEBUG log identified it by what was absent — `History Command Created Event` present, no gather line, no traceback — which means the page's message never reached `_palette_incoming` at all.

The fix is the pattern the other three palettes already use, and the reason they were never exposed to it: they seed themselves entirely from `init.js` and treat the handshake as a repaint. `_palette_incoming` now logs every action the page sends, so a future silence says which side went quiet.

### Reading the history

`app.activeDocument.dataFile.versions`, walked once. Per version: `versionNumber`, `dateCreated` (falling back to `dateModified`, which only moves for the few edits that do not create a version), `description`, `isMilestone`, `versionId`, and `lastUpdatedBy` / `createdBy` for the author's display name and Autodesk user id.

Two things are read once for the whole file rather than per version, because both are cloud calls:

- **Milestones and releases** come from `DataFile.milestones`, mapped version number → name. A milestone whose name Fusion generated (`Milestone V7`, `Item Update`) is drawn as a milestone; anything else is a revision the user typed, drawn as a release. `history_model.is_release_name` owns that rule, shared in spirit with `commands/versiondiff`.
- **The public share** comes from `DataFile.sharedLink.isShared`. Fusion exposes the link on the file rather than per version, so the ring marks the current version. Reading it per version would be one round trip per dot.

Every per-version read is guarded individually: one unreadable version costs its own dot, not the whole history.

### Thumbnails

`DataFile.thumbnail` returns a `DataObjectFuture`, and `adsk.core.Future` has no completion event, so a thumbnail can only be collected by polling. Polling inline would hold the UI thread while the palette is on screen, so each poll is one turn of a `threading.Timer` → `app.fireCustomEvent` → handler hop, the same shape `commands/assemblypalette` uses (14f42ca). The timer thread touches nothing but `fireCustomEvent` (266e2c2).

The page asks only for the version the pointer has rested on for 400 ms, so this is a trickle rather than a gallery load. Results are cached on disk through `recents_utils`, keyed by `versionId`; the pump reports `""` for a version with no thumbnail so the hover card can tell "still downloading" from "there is no preview".

### Notes

- The palette docks right at `PALETTE_WIDTH` (300 px), like the other PowerTools palettes. That leaves about 210 px of plot, which is a width `hourTicks()` already thins for: every sixth hour ruled, only noon labelled. Narrower than roughly 260 px overall and the axis drops out altogether rather than colliding with itself — the designed degradation, not a fault. The author gutter is sticky precisely so the thread view stays readable at this width.
- Day buckets are **local** calendar days. A 23:30 save must stay on the day its author saw on their own clock, not the UTC day it lands in east of Greenwich.
- The palette shows a snapshot. There is deliberately no auto-refresh: reading the document model from an application event handler (`documentSaved` above all) can abort Fusion's background saver — see [Assembly Palette](Assembly%20Palette.md), "Attempted and parked".
- The author colour is the one thing in the page not taken from the theme. It has to be a function of *who*, so the same person is the same colour in every row and in every session; the initials on top are solved against it, because HSL lightness is not perceptual.

### Component diagram

```mermaid
C4Component
    title Document History – Component Architecture

    Person(user, "Designer", "Fusion user working on a design")
    Component(addin, "PowerTools Add-In", "Python, Fusion API", "Hosts and registers all PowerTools commands")
    Component(cmd, "Document History", "dochistory/entry.py", "QAT button, palette lifecycle, version read, thumbnail pump")
    Component(model, "History model", "dochistory/history_model.py", "Buckets versions into day rows, author tracks and gaps")
    Component(page, "History palette", "resources/html/app.js", "Measures the panel, computes geometry, draws the SVG")
    Component(dataFile, "DataFile", "Fusion Data API", "versions, milestones, sharedLink, thumbnail")

    Rel(user, addin, "Loads add-in on Fusion start")
    Rel(addin, cmd, "Calls start() – registers the QAT button")
    Rel(user, cmd, "Clicks History on the QAT")
    Rel(cmd, dataFile, "Walks versions; reads milestones and shared link once")
    Rel(cmd, model, "bucket_by_day(records)")
    Rel(cmd, page, "sendInfoToHTML: setHistory, setThumbs")
    Rel(page, cmd, "incomingFromHTML: ready, requestThumbs")
    Rel(user, page, "Toggles the thread view, hovers a save")
```
