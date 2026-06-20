# Get a Share Link

**Enables sharing and copies the public share link to the system clipboard.**

Use this command to generate a publicly accessible URL for the active Autodesk Fusion document. You can paste the link into email messages, chat messages, or any other text to give colleagues or external reviewers browser-based access to the design — without requiring them to have Autodesk Fusion installed.

---

## When to use this command

| Scenario | Recommendation |
|---|---|
| Send design for review to someone outside your organization | Use **Get a Share Link** |
| Share with someone who does not have Autodesk Fusion installed | Use **Get a Share Link** |
| Share with a team member who needs edit access in Fusion | Use [Get Open on Desktop Link](get-open-on-desktop-link.md) instead |
| Share for review through the Fusion Team web viewer | Use [Get Open in Team Link](get-open-in-team-link.md) instead |

---

## How to use this command

1. Open the document you want to share. The document must be saved to an Autodesk Team Hub.
2. Select **Share Menu** in the right Quick Access Toolbar.
3. Select **Get a Share Link**.
4. If sharing has not been enabled previously, a progress indicator appears momentarily while the add-in enables sharing and retrieves the link.
5. A result dialog confirms that the link was copied to the clipboard and reports the current sharing state.
6. Paste the link wherever you need it.

---

## Result dialog

The result dialog confirms that the share link was copied and includes status notes for the following conditions:

| Condition | Dialog note |
|---|---|
| Document was already shared before this command ran | Reported in the result message |
| Downloading from the link is disabled | Noted; directs you to **Change Share Settings** |
| Share link is password protected | Noted in the result message |
| External references present, download enabled | Recipients can download referenced designs |
| External references present, download disabled | Referenced designs can be viewed but not downloaded |

---

## Requirements and limitations

- The document must be saved to an Autodesk Team Hub.
- If the Team Hub administrator has disabled share links for the Hub, a private permalink is copied to the clipboard instead. The private permalink provides Hub members with access to the document details page only — it does not allow public access.
- Enabling sharing requires a network round-trip to Autodesk Platform Services, which may take a few seconds. A progress indicator is shown during this operation.

---

## Architecture — command flow

The following diagram shows what the add-in does when you select **Get a Share Link**.

```mermaid
C4Context
    title Get a Share Link — System Interactions

    Person(designer, "Designer", "Autodesk Fusion user selecting the command")
    System(addin, "Share Menu Add-in", "Processes the share link request")
    System_Ext(fusionApi, "Autodesk Fusion API", "Reads and writes document share state")
    System_Ext(aps, "Autodesk Platform Services", "Stores sharing configuration and generates the share URL")
    System_Ext(clipboard, "System Clipboard", "Receives the generated share link")

    Rel(designer, addin, "Selects Get a Share Link")
    Rel(addin, fusionApi, "Reads isSaved, isShareAllowed, sharedLink state")
    Rel(addin, fusionApi, "Sets isShared = True if not already shared")
    Rel(fusionApi, aps, "Persists share state and retrieves linkURL")
    Rel(addin, clipboard, "Copies the share link via clipText()")
    Rel(addin, designer, "Shows result dialog with share state details")
```

### Detailed command flow

```mermaid
flowchart TD
    A([User selects Get a Share Link]) --> B{Document saved?}
    B -- No --> C[Show save-required dialog\nCommand exits]
    B -- Yes --> D{Hub sharing enabled?\nSimpleSharingPublicLinkCommand.isEnabled}
    D -- No --> E[Copy fusionWebURL permalink\nto system clipboard]
    E --> F[Show sharing-disabled message\nwith permalink note]
    D -- Yes --> G{shareState.isShared?}
    G -- No --> H[Show progress indicator\nSet isShared = True via Fusion API]
    G -- Yes --> I[wasShared = True]
    H --> J[Read shareState.linkURL]
    I --> J
    J --> K{linkURL empty?}
    K -- Yes --> L[Show failure dialog\nCommand exits]
    K -- No --> M[Copy shareLink to clipboard\nvia futil.clipText]
    M --> N[Build result message:\nshare state + download setting\n+ password setting + external refs]
    N --> O[Show result dialog]
```

---

## Key API surface

| API element | Purpose |
|---|---|
| `ui.commandDefinitions.itemById("SimpleSharingPublicLinkCommand")` | Checks whether sharing is enabled for this Hub |
| `futil.isSaved()` | Guards against operating on unsaved documents (checks `app.activeDocument.isSaved`; shows a "Please Save" prompt if not) |
| `app.activeDocument.dataFile.sharedLink` | Returns the `SharedLink` object for reading and setting share state |
| `sharedLink.isShared` | Reads or sets the sharing enabled state |
| `sharedLink.linkURL` | The public share URL |
| `sharedLink.isDownloadAllowed` | Whether recipients can download the document |
| `sharedLink.isPasswordRequired` | Whether the share link is password protected |
| `app.activeDocument.designDataFile.fusionWebURL` | Private permalink used when Hub sharing is disabled |
| `futil.clipText(text)` | Copies the link to the system clipboard |

---

## Related commands

- [Change Share Settings](change-share-settings.md) — Modify download permissions and password protection after sharing is enabled.
- [Get Open on Desktop Link](get-open-on-desktop-link.md) — Generate a link that opens the document for editing in Fusion.
- [Get Open in Team Link](get-open-in-team-link.md) — Generate a link that opens the document in the Fusion Team web viewer.

---

*Copyright © 2026 IMA LLC. All rights reserved.*
