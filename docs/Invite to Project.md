# Invite to Project

**Opens the Autodesk Fusion Team web client to the Invite Members page for the active document's project.**

Use this command to add collaborators to the Hub project that contains the active document. After you send invitations, new members can be granted the appropriate access permissions from within Fusion Team. This command takes you directly to the correct project without requiring you to manually navigate the Fusion Team web interface.

---

## When to use this command

| Scenario | Recommendation |
|---|---|
| Add a new team member to the current project | Use **Invite to Project** |
| View who currently has access to the project | Use [Document Project Members](document-project-members.md) instead |
| Share the document with someone who does not need project membership | Use [Get a Share Link](get-a-share-link.md) instead |

---

## How to use this command

1. Open a document that is saved to an Autodesk Team Hub project.
2. Select **Share Menu** in the right Quick Access Toolbar.
3. Select **Invite to Project**.
4. Your default web browser opens directly to the **Invite Members** page for the project.
5. Enter the email addresses or names of the people you want to invite, assign their role, and send the invitations.

> **Note:** You must have sufficient Hub permissions to invite members. If you do not have permission, contact your Fusion Hub administrator.

---

## Requirements and limitations

- The document must be saved.
- The document must be stored in an Autodesk Hub project. If the document is a local file or has not been saved, this command cannot determine the project context.
- You must have the Hub role that permits inviting members (typically **Admin** or **Project Admin**).
- Your browser must be able to reach `autodesk.com` domains. If your browser blocks pop-ups from these domains, allow them in your browser settings.

---

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

---

## Related commands

- [Document Project Members](document-project-members.md) — View all current members and their access levels.
- [Get a Share Link](get-a-share-link.md) — Share the document publicly without adding project members.

---

*Copyright © 2026 IMA LLC. All rights reserved.*
