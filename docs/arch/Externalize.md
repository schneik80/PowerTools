# Externalize — Architecture
[← Externalize guide](../Externalize.md)

## Architecture

The actual save/replace work runs **outside** `command_execute`, in a Fusion `CustomEvent` handler that the command fires before returning. This is required because `Component.saveCopyAs`'s upload pipeline does not advance while `command_execute` holds the main thread (Autodesk forum [11164467](https://forums.autodesk.com/t5/fusion-api-and-scripts-forum/datafilefuture-uploadstate-is-not-updating-when-commandinputs/td-p/11164467)). In a custom-event handler, the same call completes in a few seconds.

### System context

```mermaid
C4Context
  title Externalize – System Context

  Person(user, "Design Engineer", "Autodesk Fusion user converting inline components to cloud documents")
  System(addin, "PowerTools Assembly", "Autodesk Fusion add-in")
  System_Ext(fusion, "Autodesk Fusion", "Host application and Python API (adsk.core / adsk.fusion)")
  System_Ext(hub, "Autodesk Hub", "Cloud folder storing the active document and newly created external components")
  System_Ext(log, "Temp Log File", "Per-run progress log read by the resume logic on next launch and tailed by Console.app / PowerShell as a live viewer")

  Rel(user, addin, "Runs Externalize command")
  Rel(addin, fusion, "Reads inline occurrences; fires customEvent; handler calls saveCopyAs / deleteMe / addByInsert / AutoSaveFilesCommand / Document.save")
  Rel(addin, log, "Writes checkpoints; reads on next launch to detect resumable state")
  Rel(fusion, hub, "Uploads each component as a new document; commits parent assembly once at run end")
```

### Component view

```mermaid
C4Component
  title Externalize – Component View

  Person(user, "Design Engineer")
  Component(cmd_def, "command_execute", "Setup", "Reads inputs; builds pending list; computes resume; opens log; stores state in _pending_run; fires customEvent; returns immediately")
  Component(handler, "_RunnerHandler", "CustomEventHandler", "Runs the per-iteration loop OUTSIDE command_execute. saveCopyAs upload pipeline advances normally here.")
  Component(sel_input, "SelectionCommandInput", "Fusion UI", "Occurrence selector (disabled when Externalize All is checked)")
  Component(ext_all, "BoolValueCommandInput", "Fusion UI", "Externalize All checkbox")
  Component(save_loc, "DropDownCommandInput", "Fusion UI", "Save Location: Same as Document or Create Sub-folder")
  Component(log_inputs, "Logging tab", "Fusion UI", "Log Progress, log path, Open live log viewer")
  Component(resume_status, "TextBoxCommandInput", "Fusion UI", "Run status — driven by _analyze_resume_state on the temp log")
  Component(save_to_cloud, "_save_to_cloud", "Helper", "saveCopyAs + tight adsk.doEvents() poll on uploadState until UploadFinished")
  Component(temp_save, "_temp_save", "Helper", "Triggers AutoSaveFilesCommand text command — local recovery checkpoint, no new cloud version")
  Component(save_parent, "_save_parent_doc", "Helper", "Document.save once at end of run via futil.wait_for_upload — single new parent cloud version")
  Component(log_writer, "_LogWriter", "Helper", "Appends key events to the per-run log file")
  Component(resume, "_analyze_resume_state", "Helper", "Parses prior log for REPLACE_COMPLETE checkpoints; computes resume skip set")
  System_Ext(hub, "Autodesk Hub", "Receives uploaded components and one new parent version")

  Rel(user, cmd_def, "Clicks Externalize; chooses options; clicks OK")
  Rel(cmd_def, sel_input, "Reads target occurrence")
  Rel(cmd_def, ext_all, "Reads Externalize All flag")
  Rel(cmd_def, save_loc, "Reads chosen save location")
  Rel(cmd_def, log_inputs, "Reads logging options")
  Rel(cmd_def, resume_status, "Displays resume status")
  Rel(cmd_def, resume, "Computes skip set on launch and on execute")
  Rel(cmd_def, log_writer, "Writes header / status lines")
  Rel(cmd_def, handler, "fireCustomEvent('PTAT_externalize_runner') with state in _pending_run")
  Rel(handler, save_to_cloud, "Per component (if no existing cloud file): upload and get DataFile")
  Rel(handler, temp_save, "Per component (after replace): local recovery checkpoint")
  Rel(handler, save_parent, "Once at end: commit single new parent cloud version")
  Rel(handler, log_writer, "Writes step lines and CHECKPOINT markers")
  Rel(save_to_cloud, hub, "saveCopyAs → DataFileFuture → DataFile")
  Rel(save_parent, hub, "Document.save → new parent version")
```

### Per-run sequence

```mermaid
sequenceDiagram
  autonumber
  participant U as User
  participant Cmd as command_execute
  participant H as _RunnerHandler
  participant Save as _save_to_cloud
  participant API as Fusion API
  participant Hub as Autodesk Hub

  U->>Cmd: OK
  Cmd->>Cmd: read inputs, build pending list, write log header
  Cmd->>API: app.fireCustomEvent('PTAT_externalize_runner')
  Cmd-->>U: dialog closes
  Note over Cmd,H: command_execute returns; handler runs in customEvent context

  H->>API: design.activeProduct, root.occurrences
  loop for each component in pending list
    H->>API: _find_existing_cloud_file(folder, name)
    alt file already exists
      API-->>H: DataFile (reused)
    else upload needed
      H->>Save: saveCopyAs(component, folder, name)
      Save->>API: component.saveCopyAs(...)
      API-->>Save: DataFileFuture (uploadState=Processing)
      loop tight adsk.doEvents() spin
        Save->>API: future.uploadState
      end
      Save-->>H: DataFile
    end
    H->>API: occurrence.deleteMe()
    H->>API: addByInsert(DataFile, transform, isReferenced=True)
    H->>API: AutoSaveFilesCommand.execute() (local recovery save)
    H->>H: log CHECKPOINT|REPLACE_COMPLETE|...
  end
  H->>API: parent_doc.save('Externalize: N components replaced')
  API->>Hub: upload new parent version
  H-->>U: summary message box
```

### Why customEvent

A direct `saveCopyAs` from inside `command_execute` returns a `DataFileFuture` whose `uploadState` never transitions away from `Processing` — Fusion's upload pipeline does not advance while a command with CommandInputs holds the main thread. Cancelling the command makes the queued uploads land on the server, which is the smoking-gun observation behind the architecture. Moving the loop into a `CustomEvent` handler — fired from `command_execute`, executed *after* the dialog closes — gets us into a context where the same call completes in a few seconds. This was validated with an isolation spike before the refactor.

`AutoSaveFilesCommand` between iterations creates a local recovery save (no new cloud version) so a crash mid-run doesn't lose the in-progress replacements. The single `Document.save` at the end commits exactly one new parent assembly version, regardless of how many components were externalized.
