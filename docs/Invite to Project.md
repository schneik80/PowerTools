# Invite to Project...

[Back to README](../README.md)

## Overview

Invite to Project opens your web browser at the Invite Members page of the project that holds the active document.

Adding a collaborator otherwise means opening Fusion Team, finding the right hub, then the right project, then the Members page. This command takes you there in one step from the document you are working in.

| Scenario | Use |
|---|---|
| Add someone to the current project | **Invite to Project...** |
| See who already has access | [Document Project Members...](./Document%20Project%20Members.md) |
| Share the document without project membership | [Get a Share Link](./Get%20a%20Share%20Link.md) |

## Prerequisites

- The active document must be saved to a hub project. Otherwise the command asks you to save first.
- Inviting members needs a hub role that allows it, typically project admin. If you lack it, the page will say so.

## Where to find it

**Share Menu › Invite to Project...** on the right-hand Quick Access Toolbar.

## How to use

1. Open a document in the project.
2. Select **Share Menu › Invite to Project...**.
3. Your default browser opens at the project's **Invite Members** page in Fusion Team. Enter the people to invite, choose their role, and send.

There is no confirmation dialog in Fusion; the browser page is the result.

## Limitations

- The page opens in your default browser, signed in as whoever that browser is signed in as.
- If the browser cannot be opened, nothing is reported.

> **Developers:** see the [architecture notes](./arch/Invite%20to%20Project.md).

---

[Back to README](../README.md)

*Copyright © 2026 IMA LLC. All rights reserved.*
