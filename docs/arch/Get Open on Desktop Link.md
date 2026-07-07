# Get Open on Desktop Link — Architecture

[← Get Open on Desktop Link guide](../Get%20Open%20on%20Desktop%20Link.md)

## Architecture — command flow

The following diagram shows what the add-in does when you select **Get Open on Desktop Link**.

```mermaid
C4Context
    title Get Open on Desktop Link — System Interactions

    Person(designer, "Designer", "Autodesk Fusion user selecting the command")
    Person(recipient, "Team Member", "Receives the link and opens the document in their Fusion client")
    System(addin, "Share Menu Add-in", "Constructs the fusion360:// deep link")
    System_Ext(fusionApi, "Autodesk Fusion API", "Provides document ID, Hub URL, and document name")
    System_Ext(clipboard, "System Clipboard", "Receives the generated fusion360:// link")
    System_Ext(fusionDesktop, "Autodesk Fusion (Recipient)", "Handles the fusion360:// protocol and opens the document")

    Rel(designer, addin, "Selects Get Open on Desktop Link")
    Rel(addin, fusionApi, "Reads dataFile.id, parentProject.parentHub.fusionWebURL, document name")
    Rel(addin, clipboard, "Copies fusion360:// link via futil.clipText()")
    Rel(addin, designer, "Shows confirmation dialog")
    Rel(recipient, fusionDesktop, "Selects the pasted link")
    Rel(fusionDesktop, fusionApi, "Resolves document by lineageUrn and opens it")
```

### Detailed command flow

```mermaid
flowchart TD
    A([User selects Get Open on Desktop Link]) --> B{Document saved?\napp.activeDocument.isSaved}
    B -- No --> C[Show save-required dialog\nCommand exits]
    B -- Yes --> D[Show progress indicator]
    D --> E[Read dataFile.id\nURL-encode as lineageUrn parameter]
    E --> F[Read parentHub.fusionWebURL\nRemove trailing 3 chars, uppercase, URL-encode]
    F --> G[Read document name\nURL-encode as documentName parameter]
    G --> H[Assemble fusion360:// URI:\nlineageUrn + hubUrl + documentName]
    H --> I[Copy link to clipboard\nfutil.clipText shareLink]
    I --> J{Design has external references?\nhas_external_child_reference rootComp}
    J -- Yes --> K[Append external-references note\nto result message]
    J -- No --> L[Prepare standard result message]
    K --> L
    L --> M[Hide progress indicator]
    M --> N[Show confirmation dialog]
```

---

## Key API surface

| API element | Purpose |
|---|---|
| `futil.isSaved()` | Guards against operating on unsaved documents (checks `app.activeDocument.isSaved`; shows a "Please Save" prompt if not) |
| `app.activeDocument.dataFile.id` | The document's lineage URN, used as the primary deep-link identifier |
| `app.activeDocument.dataFile.parentProject.parentHub.fusionWebURL` | The Hub URL encoded into the link so the recipient's client connects to the correct Hub |
| `app.activeDocument.name` | The document name encoded into the link for display purposes |
| `urllib.parse.quote(string)` | URL-encodes each link parameter |
| `futil.clipText(text)` | Copies the assembled link to the system clipboard |
| `has_external_child_reference(component)` | Recursive function that checks the component tree for linked external files |
