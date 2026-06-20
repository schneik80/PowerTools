# Invite to Project — Architecture

[← Invite to Project guide](../Invite%20to%20Project.md)

## Architecture — command flow

The following diagram shows what the add-in does when you select **Invite to Project**.

```mermaid
C4Context
    title Invite to Project — System Interactions

    Person(designer, "Designer", "Autodesk Fusion user selecting the command")
    System(addin, "Share Menu Add-in", "Constructs the Fusion Team invite URL")
    System_Ext(fusionApi, "Autodesk Fusion API", "Provides the fusionWebURL for the active document")
    System_Ext(browser, "Default Web Browser", "Opens the Fusion Team invite page")
    System_Ext(fusionTeam, "Autodesk Fusion Team", "Hub web client — Invite Members page")

    Rel(designer, addin, "Selects Invite to Project")
    Rel(addin, fusionApi, "Reads dataFile.fusionWebURL")
    Rel(addin, browser, "Opens constructed invite URL via webbrowser.open()")
    Rel(browser, fusionTeam, "Navigates to Invite Members page")
    Rel(designer, fusionTeam, "Sends invitations and assigns roles")
```

### Detailed command flow

```mermaid
flowchart TD
    A([User selects Invite to Project]) --> B{Document saved?\napp.activeDocument.isSaved}
    B -- No --> C[Show save-required dialog\nCommand exits]
    B -- Yes --> D[Show progress indicator]
    D --> E[Read app.activeDocument.dataFile.fusionWebURL]
    E --> F[URL-encode the fusionWebURL]
    F --> G[Strip path after last /\nto get project-level URL]
    G --> H[Append ==/fpV2?redirectSource=fremont\n&action=ffpInviteMembers]
    H --> I[Hide progress indicator]
    I --> J[Open URL in default web browser\nwebbrowser.open shareLink]
    J --> K([Fusion Team Invite Members page opens])
```

---

## URL construction

The add-in derives the invite URL from `dataFile.fusionWebURL`, which points to the active document's page on Fusion Team. The construction process:

1. Reads the document's `fusionWebURL` (for example, `https://autodesk.com/team/hubs/.../projects/.../data/.../files/...`).
2. Trims the path to the project level by removing everything after the last `/`.
3. Appends the query string `==/fpV2?redirectSource=fremont&action=ffpInviteMembers` to redirect to the Invite Members page.

---

## Key API surface

| API element | Purpose |
|---|---|
| `futil.isSaved()` | Guards against operating on unsaved documents (checks `app.activeDocument.isSaved`; shows a "Please Save" prompt if not) |
| `app.activeDocument.dataFile.fusionWebURL` | Base URL used to construct the invite page URL |
| `urllib.parse.quote` / `urllib.parse.unquote` | URL encoding and decoding during path manipulation |
| `webbrowser.open(url)` | Opens the constructed URL in the system default browser |
