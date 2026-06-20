# Get Open in Team Link — Architecture

[← Get Open in Team Link guide](../Get%20Open%20in%20Team%20Link.md)

## Architecture — command flow

The following diagram shows what the add-in does when you select **Get Open in Team Link**.

```mermaid
C4Context
    title Get Open in Team Link — System Interactions

    Person(designer, "Designer", "Autodesk Fusion user selecting the command")
    Person(recipient, "Hub Member", "Receives the link and views the document in a browser")
    System(addin, "Share Menu Add-in", "Retrieves the Fusion Team URL and copies it to the clipboard")
    System_Ext(fusionApi, "Autodesk Fusion API", "Provides the fusionWebURL from the data model")
    System_Ext(clipboard, "System Clipboard", "Receives the Fusion Team URL")
    System_Ext(fusionTeam, "Autodesk Fusion Team", "Web viewer — opens the document for browser-based review")

    Rel(designer, addin, "Selects Get Open in Team Link")
    Rel(addin, fusionApi, "Reads dataFile.fusionWebURL")
    Rel(addin, clipboard, "Copies URL via futil.clipText()")
    Rel(addin, designer, "Shows confirmation dialog")
    Rel(recipient, fusionTeam, "Selects the pasted link — document opens in browser")
```

### Detailed command flow

```mermaid
flowchart TD
    A([User selects Get Open in Team Link]) --> B{Document saved?\napp.activeDocument.isSaved}
    B -- No --> C[Show save-required dialog\nCommand exits]
    B -- Yes --> D[Show progress indicator]
    D --> E[Read app.activeDocument.dataFile.fusionWebURL]
    E --> F[Copy link to clipboard\nfutil.clipText shareLink]
    F --> G{Design has external references?\nhas_external_child_reference rootComp}
    G -- Yes --> H[Append external-references note\nto result message]
    G -- No --> I[Prepare standard result message]
    H --> I
    I --> J[Hide progress indicator]
    J --> K[Show confirmation dialog]
```

---

## Key API surface

| API element | Purpose |
|---|---|
| `futil.isSaved()` | Guards against operating on unsaved documents (checks `app.activeDocument.isSaved`; shows a "Please Save" prompt if not) |
| `app.activeDocument.dataFile.fusionWebURL` | The Fusion Team URL for the active document |
| `futil.clipText(text)` | Copies the link to the system clipboard |
| `has_external_child_reference(component)` | Recursive function that checks the component tree for linked external files |
