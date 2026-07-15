# New Assembly — Architecture
[← New Assembly guide](../New%20Assembly.md)

## Architecture

New Assembly bridges an HTML/JS palette (running in Fusion's QT WebEngine) and the Fusion Python API. The palette hosts the three quick-start sections; the Python backend watches for new empty Assembly documents, enumerates open and recent documents, renders thumbnails, and performs component creation and insertion.

```mermaid
C4Context
  title New Assembly – System Context

  Person(user, "Design Engineer", "Autodesk Fusion user starting a new assembly")
  System(addin, "PowerTools Assembly", "Autodesk Fusion add-in")
  System_Ext(fusion, "Autodesk Fusion", "Host application and Python API (adsk.core / adsk.fusion)")
  System_Ext(hub, "Autodesk Hub", "Cloud documents inserted by reference and created in place")

  Rel(user, addin, "Creates a new empty Assembly; creates/inserts components from the palette")
  Rel(addin, fusion, "Watches documentActivated; creates and inserts components; renders thumbnails")
  Rel(fusion, hub, "Resolves DataFiles for insertion; stores created external components")
```

```mermaid
C4Container
  title New Assembly – Container View

  Person(user, "Design Engineer")

  Container_Boundary(cmd, "New Assembly command") {
    Container(python, "Python Backend", "commands/assemblyintent/entry.py", "Trigger gate, open/recent enumeration, thumbnails, target-project resolution, create + insert")
    Container(palette, "HTML Palette", "resources/html/index.html", "Create form, no-project banner, Open/Recent tabbed galleries, theme")
    ContainerDb(init, "init.js", "Generated sidecar", "window.__ptInit: theme, doc name, open + recent docs, target project")
    ContainerDb(recent, "recent_docs.json", "Local cache (recents_utils)", "Recently-touched part/hybrid/assembly DataFile ids; shared with Open Recent")
    ContainerDb(thumbs, "Thumbnail cache", "OS temp PNGs (recents_utils)", "Per-DataFile thumbnails keyed by md5(id); shared with Open Recent")
  }

  System_Ext(fusion, "Fusion API", "adsk.core, adsk.fusion")

  Rel(user, palette, "Fills create form; clicks document cards; toggles Show referenced children")
  Rel(palette, python, "fusionSendData('createComponent' / 'insertDoc' / 'setShowChildren' / 'refresh')")
  Rel(python, palette, "sendInfoToHTML('setOpenDocs' / 'setRecentDocs' / 'setTheme')")
  Rel(python, init, "Writes state before palette open")
  Rel(python, recent, "Reads / appends recent entries")
  Rel(python, thumbs, "Renders + reads cached thumbnails")
  Rel(python, fusion, "addNewExternalComponent, addByInsert, createThumbnail")
```

```mermaid
C4Component
  title New Assembly – Python Backend

  Container_Boundary(python, "Python Backend") {
    Component(trigger, "documentActivated gate", "Trigger", "Pops palette once per new empty Assembly-intent doc; _palette_was_open_for dedup")
    Component(launch, "Launch button", "Toolbar", "PTAT_newAssembly control in Assembly > Insert; opens palette on demand")
    Component(state, "Palette state", "_gather_palette_state", "Theme, doc name, open docs, recent docs, target project")
    Component(open, "Open enumerator", "_list_open_docs", "Top-level filter (documentReferences), dedup by id, excludes active/unsaved/inserted")
    Component(recent, "Recent enumerator", "_list_recent_docs", "Cache filtered to not-open + not-inserted; newest-first; dedup")
    Component(thumbs, "Thumbnail engine", "_thumbnail_for_open_doc", "Component.createThumbnail -> PNG cache -> data URL")
    Component(project, "Target-project resolver", "cache.resolve_target_folder", "Saved doc's folder -> activeProject.rootFolder; None -> no-project banner + Create disabled")
    Component(actions, "Action router", "_palette_incoming", "createComponent / insertDoc / setShowChildren / launch handoffs / refresh / recheckProject")
  }

  System_Ext(fusion, "Fusion API")

  Rel(trigger, state, "Builds state, shows palette")
  Rel(launch, state, "Builds state, shows palette")
  Rel(state, open, "Lists open documents")
  Rel(state, recent, "Lists recent documents")
  Rel(state, project, "Resolves target folder + label")
  Rel(open, thumbs, "Renders thumbnails for open docs")
  Rel(actions, project, "recheckProject re-resolves (no Fusion event)")
  Rel(actions, fusion, "addNewExternalComponent / addByInsert")
  Rel(project, fusion, "activeDocument.dataFile / activeHub / activeProject.rootFolder")
  Rel(open, fusion, "documentReferences (top-level test)")
```

### User flow

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant Fusion
    participant Trigger as documentActivated gate
    participant Python as Python Backend
    participant Palette as HTML Palette

    User->>Fusion: File > New Design (Assembly intent)
    Fusion->>Trigger: documentActivated
    Trigger->>Trigger: Empty + unsaved + Assembly? not already shown?
    Trigger->>Python: _show_palette()
    Python->>Python: _gather_palette_state() (open + recent docs, thumbnails, target project)
    Python->>Palette: write init.js + palettes.add()

    opt No target project (activeProject raises id.size())
        Palette->>Palette: Show "no target project" banner + disable New Component
        User->>Palette: Select project in Data Panel; return to palette (focus) or click Re-check
        Palette->>Python: fusionSendData('recheckProject')
        Python->>Palette: sendInfoToHTML('setTargetProject') (clears banner, enables Create)
    end

    alt Create a component
        User->>Palette: Name + intent + New Component
        Palette->>Python: fusionSendData('createComponent')
        Python->>Python: cache.resolve_target_folder()
        Python->>Fusion: addNewExternalComponent + designIntent
    else Insert an open / recent document
        opt Show referenced children
            User->>Palette: Toggle checkbox
            Palette->>Python: fusionSendData('setShowChildren')
            Python->>Palette: sendInfoToHTML('setOpenDocs')
        end
        User->>Palette: Click document card
        Palette->>Python: fusionSendData('insertDoc', dataFileId)
        Python->>Fusion: occurrences.addByInsert(dataFile)
    else Hand off
        User->>Palette: Assembly Builder… / Global Parameters…
        Palette->>Python: fusionSendData('launch…')
        Python->>Fusion: commandDefinition.execute()
    end

    Python->>Palette: sendInfoToHTML refresh (open + recent)
```

## Design decisions

### Why `documentActivated` instead of `documentOpened`?
`documentOpened` is not reliably emitted for **File > New** across Fusion builds (notably on macOS), while `documentActivated` fires consistently. It also fires on every tab switch, so a `_palette_was_open_for` gate (compared by Python object identity, not `id()`) suppresses re-popping the palette for a document it already handled. `documentOpened` is attached as a harmless backup when the running build exposes it.

### How are top-level documents told apart from referenced children?
Fusion answers this directly and instantly: `Document.documentReferences` raises *"Cannot get documentReferences of a non-top-level document"* for a reference-loaded child and returns the reference collection for a top-level document. The Open tab uses that in-memory check (no cloud round-trip) to show only the documents you opened directly. **Show referenced children** simply skips the filter.

### Why a generated `init.js` instead of a message handshake?
As with Assembly Builder, the palette loads asynchronously and `palettes.add()` rejects a query string on the URL. Writing `resources/html/init.js` (theme, document name, open docs, recent docs) **before** creating the palette lets the page read `window.__ptInit` synchronously and apply the correct theme before the first paint. A reopened palette is refreshed via `sendInfoToHTML` instead.

### Why render thumbnails with `Component.createThumbnail`?
The DataFile-backed cloud thumbnail did not resolve reliably in the target build. Rendering the live root component is dependable while a document is open, so thumbnails are generated for open documents and cached on disk (keyed by `md5(dataFileId)` in the OS temp folder). The Recent gallery — whose documents are closed and cannot be rendered — reuses whatever PNG was cached while the document was last open, falling back to a placeholder.

### Why is the recents cache shared with Open Recent?
The recents cache (`cache/recent_docs.json`) and the per-document thumbnail store were originally private to this command. The [Open Recent](./Open%20Recent.md) File-menu flyout surfaces the same list, so the data layer — cache format/location, thumbnail key scheme and rendering, and the `read`/`write`/`touch`/`list`/`remember` helpers — was extracted into `lib/ptAddInUtils/recents_utils` (mirroring how `cache_utils` owns the Global Parameters cache formats). New Assembly now delegates its recents helpers to that module, keeping one source of truth so the palette gallery and the File-menu flyout can never drift.

### Why a "no target project" banner (and manual re-check)?
A new external component needs a target `DataFolder` for its eventual save. The backend resolves one via `cache.resolve_target_folder()` — the active document's own folder when it is already saved, otherwise `app.data.activeProject.rootFolder`. That `activeProject` access raises `InternalValidationError('id.size()')` when the Data Panel has no project in context. Because a raise inside the palette's `incomingFromHTML` handler is swallowed by the `DEBUG`-gated `handle_error()`, this previously read to the user as **nothing happening** on *New Component*. The palette now surfaces an unresolved project as a banner and disables *New Component* until one is available. Fusion exposes **no active-project-changed event** (`Data.activeProject` is a plain property with no event), so the palette can't observe the user picking a project: it re-checks on demand instead — via a **Re-check** button on the banner and automatically when the palette page regains focus (a lightweight `recheckProject` message that re-resolves only the target folder). The same resolver and banner back the Assembly Builder's *Create Assembly* gate.

### Why a per-session "inserted" filter?
A document inserted from the palette is not "open in a tab," so the next refresh would re-list it under Recent and a second click would silently add a duplicate occurrence. Inserted DataFile ids are tracked for the current palette session and hidden from both galleries; the set is cleared each time the palette is opened so deliberate re-insertion is still possible in a fresh session.
