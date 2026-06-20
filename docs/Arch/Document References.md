# Document References — Architecture
[← Document References guide](../Document%20References.md)

## Roots — recursive parent walk

The Roots section is computed by a depth-first recursive walk of the parent graph:

1. Starting from each immediate parent of the active document, the command calls `parentReferences` on that file.
2. For each parent it encounters it checks:
   - **Skip if already visited** — prevents infinite loops in cyclic or diamond-shaped reference graphs.
   - **Skip drawings** — files with extension `.f2d` are excluded from the walk and are not treated as roots.
   - **Skip Related Data** — files whose name contains the ` ‹+› ` marker are excluded.
3. If a file has **no remaining real parents** after filtering, it is a root and is added to the list (once — duplicates are suppressed by file ID).
4. The active document itself is always excluded from the Roots list even if it has no parents.

### Diagnostics

The root walk emits detailed trace entries to the Fusion **Text Commands** panel (`View → Text Commands`). Each line is prefixed with `[Roots]` and indented by recursion depth:

```
[Roots] Visiting: 'Sub-Assembly A'  id=urn:adsk...
[Roots]   'Sub-Assembly A' raw parents (2): ['Top Assembly', 'Drawing v1']
[Roots]   SKIP parent (drawing): 'Drawing v1'
[Roots]   KEEP parent: 'Top Assembly'
[Roots]   'Sub-Assembly A' has 1 real parent(s) — recursing
[Roots]     Visiting: 'Top Assembly'  id=urn:adsk...
[Roots]     'Top Assembly' raw parents (0): []
[Roots]     ROOT FOUND: 'Top Assembly'
```

Use these traces to verify that drawings and Related Data documents are being excluded correctly and that the active document is not appearing as a root.

## Architecture

The following diagrams show how the Document References command fits into the Autodesk Fusion ecosystem and how its internal components interact.

```mermaid
C4Context
  title Document References – System Context

  Person(user, "Design Engineer", "Autodesk Fusion user reviewing document relationships")
  System(addin, "PowerTools Assembly", "Autodesk Fusion add-in")
  System_Ext(fusion, "Autodesk Fusion", "Host application and Python API (adsk.core / adsk.fusion)")
  System_Ext(hub, "Autodesk Hub", "Cloud document graph, thumbnail data, and web URLs")

  Rel(user, addin, "Runs Document References")
  Rel(addin, fusion, "Reads parentReferences and childReferences from active DataFile; walks full parent chain recursively for root detection; fetches thumbnails")
  Rel(fusion, hub, "Resolves document graph at each recursion level and retrieves thumbnail futures")
  Rel(addin, user, "Renders tabular dialog: Roots, Used In, Uses, Drawings, Fasteners, Related Data")
```

```mermaid
C4Component
  title Document References – Component View

  Person(user, "Design Engineer")
  Component(cmd, "refrences/entry.py", "PowerTools Command", "Registers the Power Tools panel button; builds the multi-group table dialog with thumbnails and action buttons")
  Component(api_doc, "adsk.core.Document / DataFile", "Fusion API", "Provides parentReferences and childReferences collections at each level of the graph")
  Component(roots, "_collect_roots()", "Internal Function", "Recursive depth-first walk of parentReferences; filters drawings and Related Data; deduplicates by file ID; emits [Roots] trace log at every decision point")
  Component(thumb, "Thumbnail Resolver", "Internal Logic", "Tries component.createThumbnail then DataFile.thumbnail future; caches results in temp directory")
  Component(dialog, "CommandInputs Table", "Fusion UI", "Six expandable group tables: Roots, Used In, Uses, Drawings, Fasteners, Related Data")
  System_Ext(hub, "Autodesk Hub", "Document metadata, web URLs, and thumbnail binary data")
  System_Ext(browser, "System Web Browser", "Opens Fusion web URL on demand")

  Rel(user, cmd, "Clicks Document References button")
  Rel(cmd, api_doc, "Reads parentReferences and childReferences")
  Rel(cmd, roots, "Walks full parent graph for each immediate parent to find roots")
  Rel(roots, api_doc, "Calls parentReferences at every level of the recursion")
  Rel(cmd, thumb, "Resolves thumbnail for each listed document including roots")
  Rel(thumb, hub, "Fetches thumbnail via DataFile.thumbnail future")
  Rel(cmd, dialog, "Builds and displays grouped table dialog")
  Rel(user, dialog, "Selects open-in-Fusion or open-in-browser buttons")
  Rel(dialog, browser, "Launches browser with fusionWebURL on web button press")
```

### User flow

```mermaid
sequenceDiagram
  autonumber
  actor User
  participant Panel as Power Tools panel
  participant Cmd as Document References
  participant Roots as _collect_roots()
  participant API as Fusion API / DataFile
  participant Hub as Autodesk Hub
  participant Browser as System Web Browser

  User->>Panel: Click Document References
  Panel->>Cmd: command_created fires
  Cmd->>API: Read activeDocument.dataFile
  Cmd->>API: parentReferences / childReferences / drawings / fasteners
  Cmd->>Roots: Walk parent chain for each immediate parent
  Roots->>API: parentReferences at each recursion level
  Roots-->>Cmd: Deduplicated root DataFile list
  Cmd->>Hub: Resolve thumbnails for every listed document
  Hub-->>Cmd: Thumbnail futures
  Cmd-->>User: Show grouped dialog (Roots, Used In, Uses, Drawings, Fasteners, Related Data)
  alt User clicks Open in Fusion
    User->>Cmd: Click open
    Cmd->>API: documents.open(DataFile)
  else User clicks Open in browser
    User->>Cmd: Click web
    Cmd->>Browser: Launch DataFile.fusionWebURL
  end
  User->>Cmd: Close
```
