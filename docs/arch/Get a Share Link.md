# Get a Share Link — Architecture

[← Get a Share Link guide](../Get%20a%20Share%20Link.md)

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
