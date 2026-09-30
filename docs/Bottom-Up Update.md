# Bottom-up Update

[Back to README](../README.md)

## Overview

Bottom-up Update saves and updates every referenced document in the open assembly from the bottom up, with options to rebuild, apply design intent, hide reference geometry and log the run.

Migrating an assembly after a Fusion update, or bringing every component of a distributed design to a clean current version, means opening each document, updating its references, rebuilding, saving, and doing it in the right order so nothing is saved against a stale child. SolidWorks and Inventor hand this to their Task Schedulers. Fusion has nothing, so Bottom-up Update is the batch job: it walks the assembly, sorts the documents so leaves come first, and opens, updates, rebuilds, saves and confirms the upload of each one, resuming from a checkpoint if the run is interrupted.

## Prerequisites

- A design document saved to a hub, with external references.
- Write access to every referenced document.

## Where to find it

**Utilities** tab › **Power Tools** panel › **Bottom-up Update**, in the Design workspace.

## How to use

1. Open the assembly and select **Bottom-up Update**.
2. Read **Run status** on the **Main** tab; it says whether this run starts fresh or resumes.
3. Set the options on the three tabs.
4. Select **OK**. Do not work in Fusion while the run proceeds; watch the live log viewer.
5. When it finishes, a dialog reads *Bottom-up Update complete.* with the log path. The count of documents saved and the elapsed time are in the log.

## Options

### Main tab

| Option | Default | Effect |
|---|---|---|
| **Update Contexts** | On | Runs Fusion's **Update Contexts** in each document, and in the root, before the rebuild and save |
| **Rebuild all** | On | Forces a full compute of each document. Turn off only to preserve the existing computed state |
| **Skip standard components** | On | Skips documents in the **Standard Components** project (the fastener library) |
| **Skip already saved Documents** | Off | Skips documents already saved by the running Fusion build |
| **Skip configured designs** | On | Skips configured designs and configuration members |
| **Apply Design Doc Intent** | On | Sets each document's design intent from its content (see below) |
| **Enable Timeline** | Off | Converts direct-modeling documents to parametric (see below) |
| **Run status** | — | Read-only: fresh run or resume |
| **Upload check interval (seconds)** (Advanced) | 0.5 | How often the upload is polled after each save |

### Visibility tab

Each option hides that geometry in the root component of every document before it is saved, and sets the folder's light bulb so new items of that type behave the same way.

| Option | Default |
|---|---|
| **Hide origins** | Off |
| **Hide joints** | Off |
| **Hide sketches** | Off |
| **Hide joint origins** | Off |
| **Hide canvases** | Off |
| **Hide user coordinate systems** | Off (hidden one by one; skipped on a Fusion build without them) |

### Logging tab

| Option | Default | Effect |
|---|---|---|
| **Log Progress** | On | Writes a plain-text log |
| **Log file path** | Blank, meaning `<document name>.log` in your system's temporary folder | **Browse…** to choose another location |
| **Open live log viewer** | On | Opens Console.app (macOS) or a PowerShell tail window (Windows) when the run starts |

## What a run does

1. **Resume check.** The existing log, if any, is read: the Fusion version and the document list are compared with the current ones to decide between a fresh run and a resume.
2. **Traversal and sort.** The assembly is walked into a dependency graph and sorted so every document is processed after the documents it references.
3. **Per document**, in that order: open; update its references; enable the timeline if asked; apply the visibility options; apply design intent; run Update Contexts; rebuild; save with the comment `Auto save in Fusion: <version>, by rebuild assembly.`; wait for the upload to complete; close; write a `CHECKPOINT|SAVE_UPLOAD_COMPLETE` line.
4. **Root.** **Get All Latest** and **Update All From Parent** run on the root, then its contexts are updated, and it is saved and its upload confirmed.
5. **Report.** The completion dialog and the log's summary.

Fusion's automatic recovery saves are suspended for the run and restored afterwards, and documents Fusion opened on its own during the run are closed at the end.

### Design intent

| Intent applied | When |
|---|---|
| **Part** | The document has no child components |
| **Assembly** | It has children but no sketches or bodies of its own |
| **Hybrid** | It has children and sketches or bodies |

### Enable Timeline

A direct-modeling document (*Do not capture design history*) is switched to parametric; Fusion captures the existing geometry as a base feature at the top of the new timeline. A parametric document is left alone. The switch is one-way and is saved as a new version, so try it on a small assembly first.

### Update Contexts

An assembly context is the parent design a component was edited inside; when the parent changes, the context goes out of date. Fusion's **Update Contexts** command is started in each document; the log records that it was *started*, and a short pause lets it land before the save. A failure is logged and the run continues.

### Upload confirmation

After each save the run waits for the cloud upload to complete before closing the document, up to 300 seconds. A timeout is logged as an error and the run continues. The final **Get All Latest** and **Update All From Parent** each have a 120-second limit; if either fails the run stops with an error.

### Resuming

The log records the Fusion version, the document list and a checkpoint line for every confirmed save. When the dialog opens, **Run status** says one of:

| Status | Meaning |
|---|---|
| *No previous log found. A full run will start.* | Nothing to resume |
| *Previous temp log is from a different Fusion client version. A full run will start.* | The log came from another build |
| *Previous run completed successfully. Log will be reset for a new run.* | The last run finished |
| *Previous run did not complete, but the document save list has changed. A full run will start.* | The assembly changed |
| *Resume available. Processing will continue after the last saved document.* | The run picks up after the last checkpoint |

Resume detection reads the default log location. To force a fresh start, delete the log file from your temporary folder.

## Limitations

- Visibility options act on the root component of each document, not on nested components inside it.
- Skipping standard components is by project name (**Standard Components**), not by vendor.
- Save every open document before starting, close documents that are not part of the assembly, and process very large assemblies as smaller sub-assemblies where you can.

## Troubleshooting

| Symptom | Cause | What to do |
|---|---|---|
| *No document references found* | The document has no external references | Run it on an assembly with linked components |
| A document is skipped | It is locked or read-only, or in the Standard Components project | Check hub permissions and whether another user has it open |
| Run status offers a full run after an interruption | Different Fusion build, or the document list changed | Accept the full run |
| Upload wait times out | Slow network or large file | Increase the interval; check connectivity |
| The live log viewer does not open | Console.app or PowerShell unavailable | Open the log file from your temporary folder |

> **Developers:** see the [architecture notes](./arch/Bottom-Up%20Update.md).

---

[Back to README](../README.md)

*Copyright © 2026 IMA LLC. All rights reserved.*
