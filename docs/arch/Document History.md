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
| `history_model.py` | The bucketing — day rows, author tracks, gaps, the calendar arithmetic — plus the merge of MFGDM's two version views. `adsk`-free and unit-tested. |
| `mfgdm_history.py` | The GraphQL read: one paginated request over `mfgdm://v3`, through the transport `partnumber_shared/mfgdm_props.gql` already owns. |
| `resources/html/{index.html,style.css,app.js}` | The drawing, plus the width-dependent geometry. |
| `tests/test_dochistory_history_model.py` | A port of the vitest suite covering the same bucketing in the web app, so the two presentations cannot drift apart in what they claim about a history. |

### Where the layout maths lives, and why it is split

The bucketing is in Python because it is where a plausible wrong number would come from — which day a save belongs to, which track, how many days two rows are apart — and the repo rule is that such logic lives in an `adsk`-free module with tests.

The geometry is in `app.js` because all of it depends on the panel width the browser measures (`ResizeObserver` on the scroll container). Sending a width to Python and a layout back would put a round trip in the middle of a drag. Its port was verified locally against the same vitest cases; CI cannot run it, because CI installs nothing but ruff and pytest.

Constants therefore live on exactly one side: `TRACKS_PER_DAY_CAP` with the bucketing, `DAY_ROWS_CAP` and every pixel value with the drawing.

### Execution flow

1. `start()` registers the command definition and inserts the button before the QAT **Save** control, then registers the custom event that drives the thumbnail pump.
2. `command_created` opens the palette directly. Not from `execute`: this command has no `CommandInputs`, and `execute` only fires when Fusion runs a command through its document-scoped pipeline, so with no document open the button would be live and nothing would happen (f18b911, 11cfc51). It bails out on no document and on an unsaved one (`ptutil.isSaved`).
3. `command_created` opens nothing. It validates and calls `_schedule_load()` — a `threading.Timer` → `app.fireCustomEvent` hop.
4. `_LoadHistoryHandler` runs on the next main-loop turn: `_gather_history()` reads the history behind `ui.progressBar.showBusy`, then `_open_palette(state)` writes that state into `init.js` and creates the palette from it.
5. The page requests a thumbnail only for the version the pointer rests on, and the pump answers it.

### init.js is the only channel to this page

The page must be able to paint from `init.js` alone, because nothing else has been shown to work.

Two builds proved it. The first opened the palette with a "Reading version history…" banner and waited for the page to ask for the data over `adsk.fusionSendData`; the palette sat on the banner forever. The second read the history on a deferred event and pushed it with `sendInfoToHTML` to an already-open palette; the palette came up empty even though the log recorded a successful 27-version read.

The DEBUG log explains both. `_palette_incoming` logs every action the page sends, and the count of `htmlReady` across every session to date is **zero** — the handshake the page fires at parse time never arrives. `requestThumbs`, sent later from a hover, does. So the page→Python channel only works after the page has been up a while, and the Python→page direction has never been independently demonstrated at all: every time this palette has shown a history, the data came from `init.js`.

Hence the order: read first, write `init.js`, then create the palette. An already-open palette is torn down and rebuilt rather than refreshed, because a live page cannot be made to re-read `init.js`; that costs the thread toggle and scroll position on a re-click. The `htmlReady` → `setHistory` path is still wired and answers from `_last_state` rather than re-reading, so it costs nothing if the handshake ever does start arriving.

### Reading the history

The history comes from **MFGDM over GraphQL**, with the desktop Data API as a fallback. `mfgdm_history.py` owns the query; the merge is pure and tested in `history_model.merge_cloud_history`.

**Why not the desktop API.** It cannot attribute versions. `DataFile` exposes exactly two `User` properties and there is no per-version type; on a 27-version design saved by nine people, `createdBy` returned "Jeremy Lambert" for all 27 and `lastUpdatedBy` returned "Myron Oakley" for all 27 — one file-level name each, and different names from each other. Fusion's own history panel shows all nine. Swapping one property for the other only trades one wrong constant for another, so the source had to change.

**Where the data actually is.** Two halves of one request:

| Field | Carries |
|---|---|
| `model.designItem.versions` → `DesignItemVersion` | `versionNumber`, `createdOn`, `createdBy` — the only per-version author Fusion exposes |
| `model.history` → `ModelWrittenHistoryChange` | the `description` typed at save time; `DesignItemVersion.description` comes back empty |

`ModelWrittenHistoryChange` is the save event — a 27-version design produced exactly 27 of them. (`VersionCreatedHistoryChange` is a *milestone*: its id decodes to `…~milestone`.) The two lists are joined **by position, not timestamp**: MFGDM stamps the same save up to 35 seconds apart in its two views. Position is trusted only when the lengths match; otherwise every version keeps its author and date and loses its comment, because a save wearing someone else's comment is worse than a bare one.

**Cost.** One request, 1.4s, against 21s for the walk it replaces — that walk was ~160 cloud round trips, because every `DataFile` property read is one. Thumbnails stay off the query deliberately: `DesignItemVersion.thumbnail.signedUrl` costs ~1.4s per row, five rows took 8.3s and thirty aborted the transport at 30s.

**Timing.** `rootDataComponent.mfgdmModelId` must not be read from `commandCreated` — doing so and then showing a modal crashed Fusion (234b043). The read runs from a timer-fired custom event instead, which also means the palette appears immediately and fills in, rather than freezing Fusion before it is on screen.

**Still on the desktop API**, because each is one read for the whole file rather than one per version: milestones (`DataFile.milestones`), the public share (`DataFile.sharedLink`), and the version `DataFile` behind a hover thumbnail — resolved lazily by version number, index guess verified rather than trusted.

Two things are read once for the whole file rather than per version, because both are cloud calls:

- **Milestones and releases** come from `DataFile.milestones`, mapped version number → name. A milestone whose name Fusion generated (`Milestone V7`, `Item Update`) is drawn as a milestone; anything else is a revision the user typed, drawn as a release. `history_model.is_release_name` owns that rule, shared in spirit with `commands/versiondiff`.
- **The public share** comes from `DataFile.sharedLink.isShared`. Fusion exposes the link on the file rather than per version, so the ring marks the current version. Reading it per version would be one round trip per dot.

Every per-version read is guarded individually: one unreadable version costs its own dot, not the whole history.

### Thumbnails

`DataFile.thumbnail` returns a `DataObjectFuture`, and `adsk.core.Future` has no completion event, so a thumbnail can only be collected by polling. Polling inline would hold the UI thread while the palette is on screen, so each poll is one turn of a `threading.Timer` → `app.fireCustomEvent` → handler hop, the same shape `commands/assemblypalette` uses (14f42ca). The timer thread touches nothing but `fireCustomEvent` (266e2c2).

The page asks only for the version the pointer has rested on for 400 ms, so this is a trickle rather than a gallery load. Results are cached on disk through `recents_utils`, keyed by `versionId`; the pump reports `""` for a version with no thumbnail so the hover card can tell "still downloading" from "there is no preview".

### Notes

- The palette docks right at `PALETTE_WIDTH` (400 px), like the other PowerTools palettes. That leaves about 310 px of plot, just over `hourTicks()`'s 260 px threshold, so the axis is three-hourly with midnight/noon/midnight labelled. Drag the dock narrower and it thins to six-hourly with noon alone, then drops out entirely below ~200 px of plot — the designed degradation, not a fault. The author gutter is sticky precisely so the thread view stays readable at any of those widths.
- Marker vocabulary: the accent ring means "marked", and filling that ring in means "released". A milestone is therefore a save's grey dot with an accent ring; a release is the same ring with an accent fill. One step to learn rather than two hues, and a release still reads as the heavier mark.
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
