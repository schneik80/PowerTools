# Document Project Members — Architecture

[← Document Project Members guide](../Document%20Project%20Members.md)

## Architecture — command flow

The following diagram shows what the add-in does when you select **Document Project Members**.

```mermaid
C4Context
    title Document Project Members — System Interactions

    Person(designer, "Designer", "Autodesk Fusion user selecting the command")
    System(addin, "Share Menu Add-in", "Constructs the Fusion Team members URL")
    System_Ext(fusionApi, "Autodesk Fusion API", "Provides the fusionWebURL for the active document")
    System_Ext(browser, "Default Web Browser", "Opens the Fusion Team members page")
    System_Ext(fusionTeam, "Autodesk Fusion Team", "Hub web client — Project Members page")

    Rel(designer, addin, "Selects Document Project Members")
    Rel(addin, fusionApi, "Reads dataFile.fusionWebURL")
    Rel(addin, browser, "Opens constructed members URL via webbrowser.open()")
    Rel(browser, fusionTeam, "Navigates to Project Members page")
    Rel(designer, fusionTeam, "Reviews and manages member permissions")
```

### Detailed command flow

```mermaid
flowchart TD
    A([User selects Document Project Members]) --> B{Document saved?\napp.activeDocument.isSaved}
    B -- No --> C[Show save-required dialog\nCommand exits]
    B -- Yes --> D[Show progress indicator]
    D --> E[Read app.activeDocument.dataFile.fusionWebURL]
    E --> F[URL-encode the fusionWebURL]
    F --> G[Strip path after last /\nto get project-level URL]
    G --> H[Append ==/fpV2?redirectSource=fremont\n&action=ffpViewMembers]
    H --> I[Hide progress indicator]
    I --> J[Open URL in default web browser\nwebbrowser.open shareLink]
    J --> K([Fusion Team Project Members page opens])
```

---

## URL construction

The add-in derives the members URL from `dataFile.fusionWebURL`, which points to the active document's page on Fusion Team. The construction process:

1. Reads the document's `fusionWebURL` (for example, `https://autodesk.com/team/hubs/.../projects/.../data/.../files/...`).
2. Trims the path to the project level by removing everything after the last `/`.
3. Appends the query string `==/fpV2?redirectSource=fremont&action=ffpViewMembers` to redirect to the Members page.

This pattern is identical to [Invite to Project](invite-to-project.md), but uses the `ffpViewMembers` action instead of `ffpInviteMembers`.

---

## Key API surface

| API element | Purpose |
|---|---|
| `futil.isSaved()` | Guards against operating on unsaved documents (checks `app.activeDocument.isSaved`; shows a "Please Save" prompt if not) |
| `app.activeDocument.dataFile.fusionWebURL` | Base URL used to construct the members page URL |
| `urllib.parse.quote` / `urllib.parse.unquote` | URL encoding and decoding during path manipulation |
| `webbrowser.open(url)` | Opens the constructed URL in the system default browser |
