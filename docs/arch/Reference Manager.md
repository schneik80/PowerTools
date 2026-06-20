# Reference Manager — Architecture
[← Reference Manager guide](../Reference%20Manager.md)

## Architecture

The following diagram shows how the Reference Manager command interacts with Autodesk Fusion.

```mermaid
C4Context
  title Reference Manager – System Context

  Person(user, "Design Engineer", "Autodesk Fusion user managing document references")
  System(addin, "PowerTools Assembly", "Autodesk Fusion add-in")
  System_Ext(fusion, "Autodesk Fusion", "Host application — provides ReferenceManagerCmd and manages reference versioning")
  System_Ext(hub, "Autodesk Hub", "Cloud document storage and version history")

  Rel(user, addin, "Clicks Reference Manager on QAT")
  Rel(addin, fusion, "Executes built-in ReferenceManagerCmd")
  Rel(fusion, hub, "Reads and writes reference version data")
```

```mermaid
C4Component
  title Reference Manager – Component View

  Person(user, "Design Engineer")
  Component(cmd, "refmanager/entry.py", "PowerTools Command", "Registers QAT button and delegates to the built-in Fusion Reference Manager command")
  Component(ref_mgr_cmd, "ReferenceManagerCmd", "Built-in Fusion Command", "Native Autodesk Fusion reference management dialog with version selection and update capabilities")
  System_Ext(hub, "Autodesk Hub", "Provides reference version history and document metadata")

  Rel(user, cmd, "Clicks Reference Manager on QAT")
  Rel(cmd, ref_mgr_cmd, "Executes via ui.commandDefinitions")
  Rel(ref_mgr_cmd, hub, "Retrieves and updates reference version data")
  Rel(ref_mgr_cmd, user, "Displays Reference Manager dialog")
```

### User flow

```mermaid
sequenceDiagram
  autonumber
  actor User
  participant QAT as Quick Access Toolbar
  participant Cmd as Reference Manager
  participant RefMgr as ReferenceManagerCmd
  participant Hub as Autodesk Hub

  User->>QAT: Click Reference Manager
  QAT->>Cmd: command_created fires
  Cmd->>RefMgr: ui.commandDefinitions.itemById('ReferenceManagerCmd').execute()
  RefMgr->>Hub: Read reference list and version history
  Hub-->>RefMgr: Reference metadata
  RefMgr-->>User: Display Reference Manager dialog
  User->>RefMgr: Update all / update one / pick version / open
  RefMgr->>Hub: Apply selected reference updates
  Hub-->>RefMgr: New references resolved
  User->>RefMgr: Close dialog
  RefMgr-->>Cmd: Dialog dismissed
```
