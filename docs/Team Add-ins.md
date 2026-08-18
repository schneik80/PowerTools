# Team Add-ins

[Back to README](../README.md)

## Overview

**Team Add-ins** keeps a team's private Fusion add-ins in step through a shared folder in your Fusion Team hub. Someone drops an add-in `.zip` into that folder; everyone else running Power Tools picks it up shortly after Fusion starts, with no restart and nothing to publish, register, or maintain.

There is no index file, no manifest to write, and no folder to browse for. The folder listing *is* the catalogue, and the folder is always in the same place:

```
<active hub> / Assets / Shared Addins /
```

the same convention Power Tools already uses for `Assets / Pn-Cache`.

Two commands make up the feature:

| Command | Where | Purpose |
| ------- | ----- | ------- |
| [Set Up Shared Add-ins Folder](./Set%20Up%20Shared%20Add-ins%20Folder.md) | PowerTools Preferences → Team Add-ins | Find or create the folder, once per hub |
| **Team Add-ins** | Design → **Tools** tab → **Power Tools** panel | Check now, and show what the last check did |

Until that folder exists, Team Add-ins is completely dormant: no network calls, no UI, nothing at launch.

---

## Sharing an add-in

1. Zip the add-in's folder so the archive holds one top-level folder containing `<name>.manifest`:

   ```
   PowerTools-PlusProject.zip
   └── PowerTools-PlusProject/
       ├── PowerTools-PlusProject.manifest
       ├── PowerTools-PlusProject.py
       └── ...
   ```

2. Upload it to `Assets / Shared Addins` in Fusion Team.

That is the whole workflow. The filename minus its extension becomes the add-in's folder name under Fusion's AddIns directory, so `PowerTools-PlusProject.zip` installs as `PowerTools-PlusProject`.

To publish an update, upload the new zip over the old one. Fusion keeps its own version history per file, and that is what Team Add-ins watches — you do not need to rename anything, bump anything, or touch a manifest.

> **The folder name, the manifest filename and the manifest `id` must all match.** Fusion pairs an add-in folder with its manifest by name, so a mismatch would install a folder Fusion silently ignores. Team Add-ins refuses the package and names both sides rather than let that happen.

`.ptaddin` is accepted as well as `.zip`. It is an ordinary zip with an opaque extension, useful if a hub ever starts treating archives as something to expand. Anything else in the folder — a readme, a spreadsheet — is ignored.

---

## What you see, and when

The rule the feature is built around: **if nothing changed, you see nothing.** A dialog on every Fusion launch would be worse than no feature at all.

| Situation | What happens |
| --------- | ------------ |
| Nothing changed | Nothing. The toolbar button's tooltip reads *"Last checked 09:14 — up to date."* |
| Add-ins installed or updated | The **Team Add-ins** palette opens listing each one |
| A restart is needed | The same palette, with an amber banner naming how many |
| A package is corrupt or unusable | The same palette, with that add-in in a **Not installed** section. Everything else still installs |
| An add-in disappears from the folder | Listed once as **No longer published**, and left installed |
| No folder yet, or not signed in | Nothing at all |
| You click the button and nothing changed | The palette opens anyway saying you are up to date — a click always gets an answer |

A package that is broken at the source is reported once, not on every launch. Clicking the toolbar button always re-reports it.

### Versions in the report

Each row shows the add-in's declared version when it has one. Because plenty of add-ins never update the version in their own manifest, the palette falls back to Fusion's file revision, which moves on every upload regardless:

| Case | Shown |
| ---- | ----- |
| Install, version declared | `1.0.0` |
| Install, no version | `rev 1` |
| Update, version bumped | `1.0.0 → 2.0.0` |
| Update, version not bumped | `1.0.0 · rev 3 → 4` |
| Update, no version at all | `rev 2 → 3` |

The declared version is **display only**. It never decides whether something is an update.

---

## How the check works

### It does not slow down Fusion's launch

Fusion's Data API can only be called from the main thread, so a background thread cannot read the hub on its own. Instead the work is *deferred*:

1. `start()` registers the command and returns immediately — Fusion's launch is untouched.
2. A daemon timer waits 25 seconds on a worker thread.
3. The worker fires a Fusion custom event, the one call that is safe off the main thread.
4. Fusion dispatches the handler on the main thread, on a turn long after start-up has finished.

### It is tiered, so the normal case is nearly free

| Tier | Cost | What happens |
| ---- | ---- | ------------ |
| 1 | One folder listing | Fingerprint the folder as `{filename: revision}`. Identical to last time → stop. **This is the entire cost of a typical launch**, and it catches additions, removals and re-uploads together |
| 2 | One download per changed file | Only packages whose revision moved, or that are new |
| 3 | One hash per download | If the bytes are unchanged, record the new revision and install nothing — a re-upload of identical content never restarts a working add-in |

Nothing in that chain reads a version number written by a human.

---

## Settings

**PowerTools Preferences → Team Add-ins**:

| Setting | Default | Effect |
| ------- | ------- | ------ |
| Check the shared folder shortly after Fusion starts | On | Turn off to make the feature manual-only |
| Wait this many seconds after launch before checking | 25 | Clamped to 5–600 |
| Load updates immediately | On | Turn off to write updates to disk but leave them for the next Fusion restart |

Disabling the **Team Add-ins** group in the Commands list removes the toolbar button and the launch check entirely.

The status card in the same section reports live state: whether the folder exists, how many packages are in it, how many are installed on this machine, and when it last checked.

---

## What Team Add-ins will not do

- **It never uninstalls anything.** A package removed from the folder is reported once and left alone — a hub hiccup or a permissions change can make a file look absent, and silently stripping working add-ins over that is worse than leaving something stale. Remove it yourself via **Utilities → Scripts and Add-Ins**.
- **It never creates the shared folder on its own.** Only the Preferences button does that, and it asks first.
- **It never overwrites Power Tools itself.** A package whose name resolves to the running add-in's folder is refused.
- **It never extracts outside the install folder.** Archive members that would escape via `..` are rejected before anything is written.

---

## Troubleshooting

**Nothing happens at launch.** Open Preferences → Team Add-ins and check the status card. Create a `.debug` marker file in the add-in root to enable logging, then watch Fusion's text-commands log for `Team Add-ins:` lines.

**"This hub has no Assets project."** The project has to exist first, and creating one needs Fusion Team admin rights, so Power Tools deliberately will not do it for you.

**"Restart Fusion to finish updating."** The add-in was in use and its files could not be replaced in place. The new version is staged and applied automatically at the start of the next Fusion session.

**An add-in installs but does not appear.** Its `<id>.manifest` does not match its filename. Team Add-ins reports this rather than installing it, so check the palette message.

**A second "Shared Addins" folder appeared.** It should not — the lookup matches loosely, so `Shared AddIns`, `shared add-ins` and `SharedAddins` are all adopted rather than duplicated. If it happens anyway, the two folders are in different projects.

---

## Open questions

Confirmed on a live build: the folder convention, `.zip` round-tripping through Fusion Team intact, first-time install with dynamic load, and updating an already-installed add-in.

Still unverified: whether registering a path already inside the standard AddIns directory leaves a duplicate entry in **Utilities → Scripts and Add-Ins** after the next Fusion launch, once Fusion's own start-up scan also finds the folder.

---

[Architecture reference](./arch/Team%20Add-ins.md) · [Back to README](../README.md)
