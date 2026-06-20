# Get and Update — Architecture
[← Get and Update guide](../Get%20and%20Update.md)

## Architecture

The following diagram shows how the Get and Update command interacts with Autodesk Fusion.

```mermaid
C4Context
  title Get and Update – System Context

  Person(user, "Design Engineer", "Autodesk Fusion user keeping references and contexts current")
  System(addin, "PowerTools Assembly", "Autodesk Fusion add-in")
  System_Ext(fusion, "Autodesk Fusion", "Host application and Python API (adsk.core)")
  System_Ext(hub, "Autodesk Hub", "Cloud document storage and version management")

  Rel(user, addin, "Clicks Get and Update on QAT")
  Rel(addin, fusion, "Executes GetAllLatestCmd then ContextUpdateAllFromParentCmd")
  Rel(fusion, hub, "Downloads latest reference versions")
```

```mermaid
C4Component
  title Get and Update – Component View

  Person(user, "Design Engineer")
  Component(cmd, "getandupdate/entry.py", "PowerTools Command", "Registers QAT button and delegates to built-in Fusion commands")
  Component(get_latest, "GetAllLatestCmd", "Built-in Fusion Command", "Downloads the newest version of every child reference")
  Component(ctx_update, "ContextUpdateAllFromParentCmd", "Built-in Fusion Command", "Refreshes all assembly contexts that are out of date")
  System_Ext(hub, "Autodesk Hub", "Provides latest document versions")

  Rel(user, cmd, "Clicks Get and Update button")
  Rel(cmd, get_latest, "Executes via ui.commandDefinitions")
  Rel(cmd, ctx_update, "Executes via ui.commandDefinitions")
  Rel(get_latest, hub, "Fetches latest reference versions")
```

### User flow

```mermaid
sequenceDiagram
  autonumber
  actor User
  participant QAT as Quick Access Toolbar
  participant Cmd as Get and Update
  participant Get as GetAllLatestCmd
  participant Ctx as ContextUpdateAllFromParentCmd
  participant Hub as Autodesk Hub

  User->>QAT: Click Get and Update
  QAT->>Cmd: command_created fires
  Cmd->>Get: ui.commandDefinitions.itemById('GetAllLatestCmd').execute()
  Get->>Hub: Fetch newest version for each child reference
  Hub-->>Get: Updated reference versions
  Get-->>Cmd: Latest references downloaded
  Cmd->>Ctx: ui.commandDefinitions.itemById('ContextUpdateAllFromParentCmd').execute()
  Ctx-->>Cmd: Assembly contexts refreshed
  Cmd-->>User: Active assembly is current
```
