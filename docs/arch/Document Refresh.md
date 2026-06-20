# Document Refresh — Architecture
[← Document Refresh guide](../Document%20Refresh.md)

## Architecture

The following diagram shows how the Document Refresh command interacts with Autodesk Fusion and the Autodesk Hub.

```mermaid
C4Context
  title Document Refresh – System Context

  Person(user, "Design Engineer", "Autodesk Fusion team member pulling the latest design version")
  System(addin, "PowerTools Assembly", "Autodesk Fusion add-in")
  System_Ext(fusion, "Autodesk Fusion", "Host application and Python API (adsk.core)")
  System_Ext(hub, "Autodesk Hub", "Cloud document storage and version management")

  Rel(user, addin, "Runs Document Refresh")
  Rel(addin, fusion, "Closes active document; finds DataFile by ID; reopens document")
  Rel(fusion, hub, "Fetches the latest version of the document on reopen")
```

```mermaid
C4Component
  title Document Refresh – Component View

  Person(user, "Design Engineer")
  Component(cmd, "refresh/entry.py", "PowerTools Command", "Registers button in File dropdown menu and handles command lifecycle")
  Component(api_app, "adsk.core.Application", "Fusion API", "Provides activeDocument, data.findFileById, and documents.open")
  Component(api_doc, "adsk.core.Document", "Fusion API", "Represents the active document; provides dataFile.id for Hub lookup")
  System_Ext(hub, "Autodesk Hub", "Cloud document storage")

  Rel(user, cmd, "Clicks Refresh Active Document")
  Rel(cmd, api_doc, "Reads dataFile.id of the active document")
  Rel(cmd, api_app, "Calls close(False) then documents.open(dataFile)")
  Rel(api_app, hub, "Retrieves the latest document version on open")
```

### User flow

```mermaid
sequenceDiagram
  autonumber
  actor User
  participant QAT as QAT › File menu
  participant Cmd as Refresh Active Document
  participant API as Fusion API
  participant Hub as Autodesk Hub

  User->>QAT: Click Refresh Active Document
  QAT->>Cmd: command_created fires
  Cmd->>API: Read activeDocument.dataFile.id
  Cmd->>API: app.data.findFileById(id)
  API-->>Cmd: DataFile reference
  Cmd->>API: activeDocument.close(False)
  Cmd->>API: app.documents.open(DataFile)
  API->>Hub: Fetch latest document version
  Hub-->>API: Document content
  API-->>User: Document reopens at latest Hub version
```
