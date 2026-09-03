# Lessons ledger

Mistakes this codebase has already paid for, distilled from the commit history
so they are not paid for twice. Each entry is **the rule**, then the symptom,
the cause, the fix, and the commit(s) that carry the full story
(`git show <hash>` is the primary source). AI agents read the short form in
[`AGENTS.md`](../../AGENTS.md) and the path-scoped `.claude/rules/*.md`; this
file is the long form both link to.

**How to add an entry.** One entry per corrected mistake, in the theme it
belongs to. Lead with a rule that stands on its own, cite the commit, and keep
the symptom concrete (what it looked like from the outside). If the rule
changes how commands are written, also add it to
[`architecture.md`](../arch/architecture.md).

---

## Contents

- [Command lifecycle](#command-lifecycle)
- [Events, threads, native crashes](#events-threads-native-crashes)
- [Dialogs, selections, custom graphics](#dialogs-selections-custom-graphics)
- [Data, cloud, identifiers](#data-cloud-identifiers)
- [UI placement](#ui-placement)
- [Preferences palette](#preferences-palette)
- [Python and portability](#python-and-portability)
- [Tooling, CI, docs, release](#tooling-ci-docs-release)
- [Security hardening already in place](#security-hardening-already-in-place)
- [Process lessons](#process-lessons)

---

## Command lifecycle

**A command with no `CommandInputs` does its work in `commandCreated`, because
`execute` never fires when no document is open.** Symptom: the Preferences
entry in the File menu was present and enabled on the start screen, clicking it
did nothing, and 858 KB of DEBUG log held no trace -- nothing raised, so
`handle_error` had nothing to log. Cause: Fusion runs commands through a
document-scoped pipeline; `commandCreated` fires, the command terminates before
`execute`. Fix: act from `commandCreated` like `closealldocuments`,
`datatoggle`, `scriptsmanager` already did; documented under *Command execution
model* in `architecture.md`. Open Recent's flyout items had the same bug and
were moved to `commandCreated` in `8a676af`, leaving no known `execute`-handler
command reachable without a document. -- `f18b911`, `11cfc51`, `8a676af`

**Never call `args.command.doExecute()` from `commandCreated`.** It runs inside
`CommandDefinition::createCommand`, so `doExecute(True)` *or* `doExecute(False)`
re-enters the command manager on a half-constructed command and segfaults
Fusion (CER stack in `Xl::APICommandDefinitionImpl::doOnCreateCommand`; the
debug log stops at "Command Created Event"). Seven commands did this on their
unhappy paths -- Version Diff on an unsaved document, Round Sketch Dimensions
with no sketch, Change Cycle Color with nothing selected. To bail out before a
dialog: `commands/_command_abort.abort_before_dialog()`, add no inputs, return;
`Command.isAutoExecute` (default true) ends the command. Because Fusion then
auto-executes the input-less command, `command_execute` still fires, so
`consume_abort()` first -- and `clear_abort()` in `command_destroy` so the flag
lives exactly one invocation (a flag left set silently disables the next
legitimate run). Defer the explanation dialog to destroy; no modal inside the
create callback. Module globals that outlive an invocation must be scrubbed on
abort too. `tests/test_command_abort.py::test_no_command_created_calls_do_execute`
is an AST guard over the whole `commands/` tree. -- `14871d7`, `a90be46`,
`5bae0e3`

**Never close a document inside a command-related event.** The API does not
support it; the command must finish before a transaction opens. Close All
Documents therefore runs entirely from `commandCreated`, re-checks
`Document.isValid` before each close and pumps events for 0.25 s after it.
Never-saved documents are closed with `close(True)` so Fusion can collect a
name; `doc.save()` cannot write them. -- `11cfc51`

**A control placed in `start()` may silently not exist; retry from
`documentActivated`.** Symptom: Preferences unreachable for a whole session when
Fusion started with no document (QAT not resolvable at load) -- a soft lockout,
since the palette is the only way to re-enable a disabled command. Fix:
idempotent `_ensure_control()` plus a `documentActivated` handler that retries
and short-circuits on a flag (unhooking a handler from inside its own dispatch
is not worth the risk). This is a *different* failure from the `execute` one
above; tell them apart with the DEBUG dump `Open Recent: File dropdown control
IDs = [...]`. -- `2afdbe1`

**`start()`/`stop()` are idempotent and a control lives in one tab.** Related
Data appeared twice in the ribbon: registered into SOLID and ASSEMBLE, and stale
controls from an unclean reload accumulated. -- `3b92f3f`

**Import commands lazily so one broken module cannot take the add-in down.**
`commands/__init__.py` used to eager-import every command; now
`load_command(key)` imports on demand, gated by the registry and preferences.
-- `1feb976`

**Command folders live directly under `commands/`.** `inferconstraints` was
nested under `commands/globalParameters/`, `from .inferconstraints import entry`
failed, and the whole add-in did not load. -- `14abc78`

**Constants are read by exact name: `CMD_Description`, not `CMD_DESCRIPTION`.**
Two commands' descriptions "existed" but never appeared anywhere. Two others had
no constant at all, one carried a sibling's text verbatim. Descriptions come
from the user docs and stay ASCII (they are also tooltips). -- `aa6802e`

---

## Events, threads, native crashes

**Never call `adsk.doEvents()` in a loop from inside a command event
handler.** It is a re-entrancy crash vector; the Infer Constraints progress
heartbeat did exactly that and Fusion crashed. A deferred `design.computeAll()`
health sweep also let over-constrained joints pile up and crashed the solver.
The stable pattern is incremental apply with a health check per relationship
and never a forced recompute. One `doEvents()` to repaint a busy indicator
before a read-only scan is the most that is safe. -- `ce4e768`, `76b9523`

**Never `time.sleep()` on the UI thread; use `ptutil.pump_events_for()`.**
Every poll loop pumped once then slept 0.5 s, freezing Fusion for the full
duration, repeatedly, and starving the upload pipeline of the events it needs
to progress. `pump_events_for(seconds)` pumps on a ~30 ms tick for the same
total time. Tested with a fake clock in `tests/test_pump_events.py`. -- `f0ff1af`

**A handle held across a pumped wait can be invalidated by background
data-model work and fault natively (no Python exception).** CER analysis:
`0xC0000005` in `NsDataModel10.dll`, `PLM360SaveCommand_Spawned`, dirty
document with *Needs Autosave: 1*. Mitigations in Bottom-Up Update: suspend
`isAutomaticVersioningEnabled` / `isAutomaticSaveOnCloseEnabled` for the run
and restore in every exit path; re-acquire `app.activeDocument` after the
pumped upload wait and close only if `dataFile.id` matches; pump ~0.25 s so
the close drains before the next open; re-acquire the `Design` after a pumped
`computeAll`. Property names were verified against the API reference, not
guessed. -- `a1d22e1`

**Configured designs crash Fusion's own PIM data model on open; skip them and
drain events before each open.** Root cause pinned to `NsBaseCore10.dll`
during `PLM360OpenAttachmentCommand`, which Python cannot catch.
`DataFile.isConfiguration` / `isConfiguredDesign` classify before the open
(default: skip). -- `0a228c8`

**Fusion opens documents implicitly; snapshot what was open and sweep strays.**
Configuration members opened by `updateAllReferences` were never closed and
accumulated. `Documents.count` includes invisible documents (verified against
the reference). -- `20c0976`

**The Fusion Data API is main-thread only. A worker thread may call exactly
one thing: `app.fireCustomEvent`.** Team Add-ins defers its launch check with a
daemon `threading.Timer` whose body is one `fireCustomEvent`; `ptutil.log`
calls `Application.log` and is not thread-safe. -- `266e2c2`, `c440ad3`

**Starting a Fusion command from a palette HTML event needs a later
main-loop turn; firing a custom event inline is not enough.** Fusion
dispatches an inline custom event in the same turn, and the command that
starts is torn down when the HTML event finishes and the palette repaints. Use
`threading.Timer` -> `fireCustomEvent`. Three signals along the way cannot be
trusted: `controlDefinition.isEnabled` reads `False` for marking-menu commands
that start fine; `execute()` returns `True` whether or not the command appears;
`ui.activeCommand` does not update in the turn a command starts (pump first).
`fireCustomEvent` itself returns `False` on success. Written up in
[Insert and position a component from a palette](Insert%20and%20position%20a%20component%20from%20a%20palette.md).
-- `c440ad3`, `921e708`

**Futures have no completion event; poll from a timer-fired custom event, a
few per tick, with timeout and negative cache.** `adsk.core.Future` exposes
only `state`. Reference Manager polls inline behind a modal progress bar,
which is fine; a palette being scrolled cannot. Assembly Palette resolves
thumbnails through `DataFile.thumbnail` this way, and the page requests them
lazily via `IntersectionObserver` so payloads scale with what is visible.
`FailedFutureState` is the documented "no thumbnail" answer, not a broken
mechanism -- the earlier belief that the cloud thumbnail "did not resolve
reliably" was wrong (`commands/refrences` had used it successfully all along).
-- `14f42ca`

---

## Dialogs, selections, custom graphics

**Custom graphics are created only in `executePreview`.** Fusion aborts the
preview transaction when the next preview fires, so graphics built from
`inputChanged` or a mouse handler flash and vanish with no error. Do not "fix"
it with `isValidResult = True` (that skips `execute`, where e.g. the clipboard
copy happens). For highlighting, prefer a limits-0,0 `SelectionCommandInput`;
for hover feedback, mutate colours in place instead of rebuilding.
`sketchcirclecenterpoint` shipped disabled for what looks like this same
reason. Full recipe: [Custom graphics that stay painted](Custom%20graphics%20that%20stay%20painted.md).
-- `b3bed5f`, `e6b3b39`

**`SelectionCommandInput` contents are not reliably readable from `execute`.**
`selection(i)` raised `RuntimeError: 3 : invalid argument index` although
`selectionCount` reported entries; Externalize was most exposed because it
defers work into a `CustomEvent` after the dialog closes. Capture with
`ptutil.capture_selections()` during `inputChanged`/`validateInputs`; the
entities (proxies included) stay valid, only the input's list does not.
-- `a91da41`

**Collections can be `None` instead of empty, and a stale result on screen is
worse than an error.** `SketchPoint.connectedEntities` returned `None` for some
points; the frontier expansion raised and the graph was never built -- but the
*previous* selection's length stayed on screen next to the new picks and read
as their answer. `_iter_collection()` absorbs `None` and raising accessors; a
failed rebuild now clears the dialog and says the geometry could not be read.
-- `c8c0382`

**`SketchPoint.worldGeometry` returns the origin for some point types.** Go
through `sketch.sketchToModelSpace()` (see `measurepath/entry.py`,
`sketchcirclecenterpoint/entry.py`).

**Preview-driven edits must be idempotent.** Round Sketch Dimensions applies in
`executePreview`, reverts on Cancel and commits on OK; skips angular,
formula-driven and driven dimensions to preserve parametric intent. -- `e6b80ba`

**Do not stack heuristics on logic that has not been verified in Fusion.**
Infer Constraints accumulated a Revolute default, a three-mode redundancy
dropdown and timeline apply-ordering; all drifted from the known-good
behaviour and were reverted to the byte-identical pre-change logic, keeping
only the performance work. One "Smart" guard could structurally never fire
because upstream dedup removed the case it checked. -- `237e903`, `02dbaf5`,
`8984b8c`

**Real geometry processing lives in an `adsk`-free solver that takes and
returns plain tuples.** Flatten Surface's `flatten.py` (~2 000 lines: outline
cutting, curve fitting, crack stitching, strain reporting) imports no `adsk`;
`entry.py` converts to and from Fusion objects. That is what let the solver be
developed and tested (`tests/test_flattensurface_*.py`) without launching
Fusion. Worked example: [Flatten Surface solver](Flatten%20Surface%20solver.md)
and its [method background](Flatten%20Surface%20research.md). -- `b5946ea` ..
`490366e`

**Make the bug you fixed impossible by construction and brute-force the
invariant in tests.** Measure Path's three plausible-wrong-number bugs
(dropped end-segment length, Dijkstra trying one end only, kind-restricted walk
with a wrong-kind seed) are pinned by tests that check *Length == sum of the
Segments rows* over every combination. -- `b3bed5f`

---

## Data, cloud, identifiers

**`app.data.activeProject` raises `InternalValidationError('id.size()')` when
the Data Panel has no project in context.** Because a raise inside a palette's
`incomingFromHTML` handler is swallowed by DEBUG-gated `handle_error`, this
surfaced as "nothing happens". Resolve through
`cache_utils.get_active_project()` / `resolve_target_folder()`; the assembly
palettes show a *no target project* banner with a Re-check button (Fusion has
no active-project-changed event). -- `7535954`, `architecture.md`

**Prefer Fusion's own on-disk recents over a home-grown cache, and never
assume an Autodesk path.** `<options root>/<userId>/<hubPrefix>_RecentsWithoutSearch_1.json`
is discovered, not assumed: several user directories coexist, stale ones look
identical, `Application.userId` can match a stale directory, so recency
outranks a user-id match. Validate a candidate by an 8 KB head read of
`qontextServer`. About 25 % of designs have an empty `docstruct` that Fusion
never backfills -- treat `""` as final. -- `6772f31`

**`addByInsert` returns `None` on failure rather than raising** -- most often
when the DataFile lives in another project. It used to read as success and hid
the document from both galleries. -- `6772f31`

**Two handlers writing one cache race on every tab switch; write atomically.**
`ptutil.write_json_atomic` (temp file + fsync + `os.replace`) is the rule for
all user-authored state. -- `6772f31`, `c557733`

**Check the Hub version before reloading a document.** Refresh closed and
reopened unconditionally, discarding unsaved edits even when already current.
The comparison lives in an `adsk`-free `logic.py`; a version Fusion will not
report reads as unknown and falls back to reloading. -- `df37588`

**MFGDM GraphQL: anchor on `rootDataComponent.mfgdmModelId` and pass
`component.hub.id` (an `urn:adsk...`), never `app.data.activeHub.id`.** The
shared-part-number rule is `isPresent && isModeled && (len(results) > 1 ||
!isAllReadableByUser || pagination.cursor)`. Model-id access must not run from
`commandCreated`. -- `234b043`, `commands/partnumber_shared/`

**Fusion IDs use underscores.** Hyphenated IDs log `Component name contains
invalid characters` on every launch (benign but floods crash logs). The
`PT-globparm` parameter-comment sentinel is *data inside users' documents* and
was deliberately kept. Renaming `CMD_ID`s orphans users' QAT/toolbar pins --
say so in the commit. -- `6789216`

**The registry key is the settings key; renames go through
`settings_store.RENAMED_COMMANDS`.** Otherwise every user's enable state for
the command silently resets and a dead key lingers in `preferences.json`.
-- `7dee722`

**`os.access` lies on Windows network shares; probe by writing.** The thumbnail
cache picks `cache/thumbs` vs. the temp dir by attempting a write. -- `14f42ca`

---

## UI placement

**Unpublished workspace IDs are pinned with a display-name fallback and
logged.** The Animation environment is internally *Publisher*:
`Publisher3DEnvironment`, tab `Animation`, anchor panel `PublisherViewPanel`.
Guessing `FusionAnimationEnvironment` never hit and the name scan logged all
38 workspaces on every load. -- `af05499`

**Placement relative to a native control is probed and self-corrected.** Open
Recent adds its flyout, verifies its index relative to the native Open control,
and recreates it on the other side if a given build interprets `isBefore`
differently; it probes several candidate IDs because Fusion has renamed the
control across releases, and dumps the File dropdown's control IDs under DEBUG.
-- `8a84eab`

**Dead `positionID`s fail silently.** Two anchors pointed at IDs that never
resolved (`PTAT_GetandUpdate` casing; a control in a different panel). Check
that an anchor lives in the same container. -- `6789216`

**Placement is discovered where the set of tabs varies.** Measure Path adds
itself to every Inspect panel of every design-product workspace because which
tabs exist depends on version and entitlement. -- `b3bed5f`

---

## Preferences palette

**Ship the defaults a new install should start with; `load()` merges stored
values over defaults, so existing users keep their choices.** Six commands ship
disabled via `DEFAULT_DISABLED_COMMANDS`; folder sets are editable and kept
across updates. -- `112d08d`, `dc89a63`

**Nav = General + one entry per group; anything a group owns renders inside
its section.** The per-group split reintroduced duplicate nav entries that a
`CMD_SECTIONS` comment had warned about. Structural fix (`groupExtras()`),
verified headlessly against the real registry: 10 nav entries, 10 sections,
no duplicate labels. Subsections are `<div>`s because the scroll-spy tracks
every `<section>`. -- `522923b`, `00302fd`

**Settings that belong to a command render nested under its row
(`d5bfc76`); commands that are only usable together are one checkbox, enforced
in the settings layer, not painted on in the UI.** The nested-children
presentation from `039bcc2` modelled the wrong thing -- Link / Refresh Global
Parameters mean nothing without Global Parameters and vice versa -- so
`settings_store.COMMAND_SETS` declares the set, `SET_LEAD` maps member to lead,
and both `commands._should_start` and `is_command_enabled` read the lead's
flag. A member's own stored flag is deliberately inert (not migrated), so an
old selectively-disabled state heals itself. The Preferences payload drops
member rows and annotates the lead with what the checkbox covers. Registry
traps in `tests/test_settings_command_sets.py`: every set key is registered and
members share the lead's group. -- `6c554d5`, `5215862`

**Unrelated controls get their own titled blocks, and copy says what a button
does.** Beta mode vs. the settings file; "Import" replaces every preference and
applies after restart. -- `6f06624`

**No native `title` tooltips; theme scrollbars with `-webkit-` pseudo-elements
only.** `scrollbar-width`/`scrollbar-color` make Chromium drop the
pseudo-elements. -- `d5bfc76`, `f104dcc`

---

## Python and portability

**`lib/ptAddInUtils/__init__.py` import order is load-bearing.** isort moved
`attributes_utils` ahead of `general_utils` and raised `cannot import name
'app' (partially initialized module)`. Pinned with `# ruff: noqa: I001` and a
per-file ignore. -- `0b179cd`

**`config.py` imports ptutil before it defines `DEBUG` and `CACHE_PATH`.**
Import-time `getattr(config, ...)` in `general_utils` latched `DEBUG=False`
for the life of the session -- no log output ever, even with `.debug` present,
probably since the merge. `log()` now re-resolves flags lazily. Regression test
covers the partial-import capture. -- `018f0c7`

**`os.path.normcase` folds case only on Windows.** A Windows-casing assertion
failed on the Linux CI runner. Fusion only runs on case-insensitive
filesystems, so `.casefold()` explicitly everywhere. -- `4cb4901`

**Platform-specific path resolvers need tests that run the other platform's
branch.** Change Cycle Color's `fusion_install.py` had macOS-only shapes for the
Fusion interpreter and lighting-environment paths that survived because nothing
exercised the Windows branches; the helpers now take the platform as an
argument so both run from any host. -- `25d5f48`, `93c6b36`

**OR permission bits, never assign them.** `stat.S_IWRITE` assigned over the
mode left POSIX entries at `0o200`, so a directory lost its traverse bit and
`rmtree` could no longer descend. -- `19ac0f7`

**Bare `except:` is banned; intentional no-op property touches are written
`_ = obj.prop` so B018 does not flag them and readers see the intent.**
`doc.documentReferences.count` is touched on purpose to force a raise for
non-top-level documents. -- `1feb976`, `79ca8e3`

**Stdlib only, everywhere.** Fusion's embedded Python has no Pillow, no pip;
the add-in has no runtime dependencies and the dev tools shell out (`git`,
`pandoc`, `xelatex`) rather than import. Icons are rendered with
`zlib`/`struct`. -- `e263d4e`, `a99202d`

---

## Tooling, CI, docs, release

**Run `ruff format .` before every commit; the check is a hard gate.** Two
feature commits landed unformatted and every CI run failed at the formatting
step until a follow-up reformat. Mechanical reformats are isolated commits and
are listed in `.git-blame-ignore-revs` so they do not mask authorship.
-- `ef424c6`, `0de55c8`, `972c448`, `5603e14`

**The ruff pin in `ci.yml` equals the version that formatted the tree.** CI ran
0.15.12 while the dev venv ran 0.15.20; the version that formats was not the
version that gates. -- `ef14b11`

**Ignore generated palette files by glob, not one path per palette.** A
palette added on a branch had no ignore rule on other branches and left a
folder holding only its generated `init.js`. -- `20efeea`

**`settings/preferences.json` is git-ignored and machine-local.** Its status
flip-flopped (tracked in `c031be8`, untracked in `270047d`); the final state is
ignored, generated from registry defaults on first run, and *forbidden* in the
release build. -- `270047d`, `1cb6d3e`

**The release zip is `git ls-files` minus explicit exclusions, and the
exclusion list is pinned by tests.** Anything newly tracked ships unless
excluded in `tools/release/build_release.py`; update
`tests/test_release_build.py` in the same commit. `.debug`, `.env` and
`settings/preferences.json` abort the build if ever tracked. -- `1cb6d3e`

**`README.pdf` is regenerated in the same commit as `README.md`, and the gate
is now mechanical.** The build audits overfull boxes and undefined references
and fails on either; `---` in the README is a print page break; pipe-table
widths come from a Lua filter that pools tables sharing a header. After the PDF
went stale once more (`b5946ea` -> `f93ec75`), every build stamps
`readme-sha256:<hash of README.md>` into the PDF's Subject metadata;
`build_readme_pdf.py --check` compares it with no pandoc needed and runs as a
CI gate and as a pytest case (`tests/test_readme_pdf_build.py`), and
`build_release.py` runs `--if-stale` before zipping and aborts if it cannot
rebuild. -- `48722db`, `a99202d`, `28188f7`

**Icons are generated and pinned.** Five commands shipped byte-identical
copies of another command's icon. `tests/test_command_icons.py` checks
presence, 8-bit RGBA, size-matches-filename and no duplicate art. Redraw the
16 px variant instead of scaling. -- `e263d4e`

**The `.debug` marker drives `DEBUG`, the debugpy server and all logging; it
is git-ignored so a distribution is always in ship mode.** When DEBUG is on,
`ptutil.log` also appends to `cache/powertools-debug.log` (5 MB cap) -- before
that there was literally no add-in log file to collect. -- `fe5efcb`, `f388ad9`,
`16be595`

**Debugging setup traps (macOS/Zed)** are in [debugging.md](debugging.md):
Fusion's Python has no pip; `in_process_debug_adapter=True` or a second Fusion
launches; Zed wants `connect`, not `tcp_connection`; the VS Code Debug button
pre-empts `listen()`; Zed downloads its own debugpy unless `dap.Debugpy.binary`
is set. -- `2315139`, `16be595`

---

## Security hardening already in place

Do not regress these (`a06e049`, `266e2c2`):

- Clipboard/URL/log-viewer sinks are de-shelled (`subprocess` argument lists,
  no `shell=True`); PowerShell path interpolation is escaped; URLs are
  scheme-guarded to http(s).
- Export filenames are sanitised; BOM CSV cells are neutralised against
  formula injection (`tests/test_csv_injection.py`).
- Document names are HTML-escaped in share dialogs.
- `settings_store.validate()` rejects unknown top-level keys on import.
- Team Add-ins extracts with a zip-slip guard, refuses to overwrite PowerTools
  itself (`installer.is_self`), never uninstalls, and verifies re-uploads by
  sha256 so identical content never restarts a working add-in.

---

## Process lessons

- **Verify API property names against the official reference, not memory**
  (`a1d22e1`, `0a228c8`, `20c0976` all say so explicitly).
- **Say what was not verified.** "Not yet exercised in Fusion" appears in the
  commits where it was true; pure-logic tests prove logic, not Fusion
  behaviour.
- **Read the log before theorising.** Several fixes cite the exact DEBUG log
  line or CER stack that pinned the cause; two "Preferences needs a document"
  reports had different root causes.
- **Descriptions and doc text come from `docs/`, not invented** (`aa6802e`).
- **A commit message explains why**, cites prior hashes it corrects or builds
  on, and closes the issue (`Closes #N`).
- **No pull requests.** Branch, commit, merge to `main`, push, delete the
  branch locally and on `origin`. This had to be corrected more than once, so
  it is the standing default, not a per-task question. Long form:
  [`.agent/workflow.md`](../../.agent/workflow.md).
- **Scope a ban to the callback that earned it.** The `doExecute` fix
  (`14871d7`, `a90be46`, `5bae0e3`) removed 13 calls from `command_created`,
  and the immediate follow-up question was whether the legitimate uses had
  been broken too. They had not — three sites outside `createCommand` are
  deliberate — but the rule as first written did not say so, which is how a
  correct fix becomes a future regression. When writing down a prohibition,
  record the surviving exceptions and why they are safe.
- **State the mechanism, not just the outcome.** "Removed the doExecute calls"
  was not a usable answer; "the ban is `command_created` only, because it runs
  inside `createCommand`; here are the three remaining sites" was.
- **A tool invocation that fails on the dev machine costs every session.**
  `AGENTS.md` told agents to run `python -m pytest -q`, which has never worked
  here (pytest is only in `.venv`). Verify the commands you document by
  running them.

---

*Copyright © 2026 IMA LLC. All rights reserved.*
