# Team Add-ins

[Back to README](../README.md)

## Overview

Team Add-ins checks the hub's `Shared Addins` folder and installs any add-in that is new or updated, automatically shortly after Fusion starts or on demand from the toolbar.

Deploying an in-house add-in to a team usually means a shared drive, an email with a zip, and a manual install on every machine, then the same again for every update. Team Add-ins replaces that with one folder in your Fusion Team hub: someone uploads an add-in `.zip`; everyone else running PowerTools picks it up shortly after their next Fusion launch, with nothing to publish, register or maintain. The folder listing *is* the catalogue, and the folder is always in the same place:

```
<active hub> / Assets / Shared Addins /
```

Two commands make up the feature:

| Command | Where | Purpose |
|---|---|---|
| [Set Up Shared Add-ins Folder](./Set%20Up%20Shared%20Add-ins%20Folder.md) | PowerTools Preferences › Team Add-ins | Find or create the folder, once per hub |
| **Team Add-ins** | **Utilities** tab › **Power Tools** panel | Check now, and show what the last check did |

## Prerequisites

- A Fusion Team hub with an **Assets** project and a `Shared Addins` folder in it. See [Set Up Shared Add-ins Folder](./Set%20Up%20Shared%20Add-ins%20Folder.md).
- Read access to that folder. Only whoever shares add-ins needs write access.

## Where to find it

**Utilities** tab › **Power Tools** panel › **Team Add-ins**, in the Design workspace. Hover the button for the last check's result, for example *Last checked 2026-09-30 09:14 — up to date.*

## Sharing an add-in

1. Zip the add-in's folder so the archive holds one top-level folder containing `<name>.manifest`:

   ```
   PowerTools-PlusProject.zip
   └── PowerTools-PlusProject/
       ├── PowerTools-PlusProject.manifest
       ├── PowerTools-PlusProject.py
       └── ...
   ```

   A zip of the folder's contents, with the manifest at the root, is accepted too.

2. Upload it to `Assets / Shared Addins` in Fusion Team.

That is the whole workflow. The filename minus its extension becomes the add-in's folder name in Fusion's add-ins directory, so `PowerTools-PlusProject.zip` installs as `PowerTools-PlusProject`. To publish an update, upload the new zip over the old one; Fusion's own file versioning is what Team Add-ins watches, so nothing has to be renamed or bumped.

> **The zip name and the manifest filename must match.** Fusion pairs an add-in folder with its manifest by name, so a mismatch would install a folder Fusion ignores. Team Add-ins refuses such a package and names both sides in the report.

`.ptaddin` is accepted as well as `.zip`; it is an ordinary zip with a different extension. Package names may contain letters, digits, `.`, `_` and `-`. Anything else in the folder, a readme or a spreadsheet, is ignored.

## What you see, and when

If nothing changed, you see nothing.

| Situation | What happens |
|---|---|
| Nothing changed | Nothing. The button's tooltip reports the time of the check. |
| Add-ins installed or updated | The **Team Add-ins** palette opens listing each one |
| A restart is needed | The same palette, with a banner: *Restart Fusion to finish updating N add-in(s).* |
| A package could not be installed | The same palette, with that add-in under **Not installed** and a banner saying some add-ins could not be installed. Everything else still installs |
| A file has a bad name, or a `.zip` and a `.ptaddin` share a name | Listed under **Folder problems** |
| An add-in disappears from the folder | Listed once as **No longer published**, and left installed |
| Not signed in, or no folder yet | Nothing at launch; the tooltip says there is no folder yet |
| You select the button and nothing changed | The palette opens anyway and says everything is up to date |

### Versions in the report

Each row shows the add-in's declared version when it has one. Because many add-ins never update the version in their manifest, the report falls back to Fusion's file revision, which advances on every upload:

| Case | Shown |
|---|---|
| Install, version declared | `1.0.0` |
| Install, no version | `rev 1` |
| Update, version bumped | `1.0.0 → 2.0.0` |
| Update, version not bumped | `1.0.0 · rev 3 → 4` |
| Update, no version at all | `rev 2 → 3` |

The declared version is display only. It never decides whether something is an update.

## How the check works

The check does not slow Fusion's launch: it is deferred by the delay set in Preferences (25 seconds by default) and runs after start-up has finished. If you are not signed in at that moment, it retries once a minute later.

It is tiered, so the normal case is nearly free:

| Tier | Cost | What happens |
|---|---|---|
| 1 | One folder listing | Fingerprint the folder as file names and revisions. Identical to last time: stop. This is the entire cost of a typical launch, and it catches additions, removals and re-uploads together. A manual check from the button always goes on to tier 2. |
| 2 | One download per changed file | Only packages whose revision moved, or that are new |
| 3 | One hash per download | If the bytes are unchanged, record the new revision and install nothing, so a re-upload of identical content never restarts a working add-in |

Installed add-ins go to Fusion's add-ins directory (`%APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns` on Windows, `~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns` on macOS) and are set to run on startup.

## Preferences

**File › PowerTools Preferences › Team Add-ins**:

| Setting | Default | Effect |
|---|---|---|
| **Enable Team Add-ins commands** | On | Turn off to remove the button and the launch check. Applies after a Fusion restart. |
| **Check the shared folder shortly after Fusion starts** | On | Turn off to check only from the button. Updates staged for a restart are still applied. |
| **Wait this many seconds after launch before checking** | 25 | Clamped to 5–600. |
| **Load updates immediately (otherwise they wait for a Fusion restart)** | On | Turn off to write updates to disk and load them at the next restart. |

The **Shared folder** card in the same section shows whether the folder exists, how many packages are in it, how many are installed on this machine, and when it last checked.

## What Team Add-ins never does

- **It never uninstalls anything.** A package removed from the folder is reported once and left alone; a hub hiccup or a permissions change can make a file look absent, and silently stripping working add-ins over that is worse than leaving one stale. Remove it yourself through **Utilities › Scripts and Add-Ins**.
- **It never creates the shared folder without asking.** Both **Create shared folder…** buttons confirm first.
- **It never overwrites PowerTools itself.** A package whose name resolves to the running add-in's folder is refused.
- **It never writes outside the add-ins folder.** Archive entries that would escape it are rejected before anything is written.

## Troubleshooting

| Symptom | What it means |
|---|---|
| Nothing happens at launch | Open **PowerTools Preferences › Team Add-ins** and read the **Shared folder** card. |
| *This hub has no 'Assets' project.* | The project has to exist first; creating one needs Fusion Team administrator rights, so PowerTools will not do it. |
| *Restart Fusion to finish updating…* | The add-in could not be loaded live, or **Load updates immediately** is off. The new files are on disk and are loaded on the next launch. |
| A package appears under **Not installed** with a name mismatch | Its manifest filename does not match the zip name. Rename one to match and upload again. |
| A second `Shared Addins` folder appeared | The lookup adopts existing folders regardless of case and spacing, so this should not happen; if it does, the two folders are in different projects. |

> **Developers:** see the [architecture notes](./arch/Team%20Add-ins.md).

---

[Back to README](../README.md)

*Copyright © 2026 IMA LLC. All rights reserved.*
