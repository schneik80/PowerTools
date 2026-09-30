# Get Open in Team Link

[Back to README](../README.md)

## Overview

Get Open in Team Link copies a link to the clipboard that opens the active document in the Fusion Team web client.

This is the document's own Fusion Team address, not a new public share. It is the right link for stakeholders, reviewers and project managers who are members of the hub but do not work in the Fusion desktop application: the design opens in their browser, with hub permissions enforced.

| Scenario | Use |
|---|---|
| A hub member will review the document in a browser | **Get Open in Team Link** |
| A hub member will edit it in Fusion | [Get Open on Desktop Link](./Get%20Open%20on%20Desktop%20Link.md) |
| Someone outside the hub | [Get a Share Link](./Get%20a%20Share%20Link.md) |

## Prerequisites

- The active document must be saved to a hub. Otherwise the command asks you to save first.
- The recipient must be a member of the hub with access to the document.

## Where to find it

**Share Menu › Get Open in Team Link** on the right-hand Quick Access Toolbar.

## How to use

1. Open the document.
2. Select **Share Menu › Get Open in Team Link**. A progress indicator appears briefly.
3. A **Share Document** dialog confirms that an **Open in Team** link for the document is on the clipboard. For a design with external references it adds: *This design has external references. Sharing this design may share the referenced designs depending on the team member's permissions.*
4. Paste the link into an email or chat message.

## Comparison with Get Open on Desktop Link

| | Get Open in Team Link | Get Open on Desktop Link |
|---|---|---|
| Link format | `https://` Fusion Team URL | `fusion360://` link |
| Recipient needs | Hub membership and a browser | Hub membership and Fusion installed |
| Opens in | Fusion Team web client | Fusion desktop application |
| Use for | Review in a browser | Editing in Fusion |

## Limitations

- Recipients who are not hub members cannot open the link. Use [Get a Share Link](./Get%20a%20Share%20Link.md) for them.
- The external-reference note appears only for design documents.

> **Developers:** see the [architecture notes](./arch/Get%20Open%20in%20Team%20Link.md).

---

[Back to README](../README.md)

*Copyright © 2026 IMA LLC. All rights reserved.*
