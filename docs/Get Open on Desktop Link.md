# Get Open on Desktop Link

[Back to README](../README.md)

## Overview

Get Open on Desktop Link copies a link to the clipboard that opens the active document directly in Fusion on a teammate's computer.

A public share link opens a viewer; a Fusion Team link opens a web page. When the person you are writing to is a hub member who is going to *edit* the design, neither is what they want. This `fusion360://` link launches Fusion on their machine and loads the document, ready to work on.

| Scenario | Use |
|---|---|
| A hub member will open the document in Fusion to edit it | **Get Open on Desktop Link** |
| A hub member will review it in a browser | [Get Open in Team Link](./Get%20Open%20in%20Team%20Link.md) |
| Someone outside the hub, with or without Fusion | [Get a Share Link](./Get%20a%20Share%20Link.md) |

## Prerequisites

- The active document must be saved to a hub. Otherwise the command asks you to save first.
- The recipient must have Fusion installed, be signed in to the same hub, and have access to the document.

## Where to find it

**Share Menu › Get Open on Desktop Link** on the right-hand Quick Access Toolbar.

## How to use

1. Open the document.
2. Select **Share Menu › Get Open on Desktop Link**. A progress indicator appears briefly.
3. A **Share Document** dialog confirms that an **Open on Desktop** link for the document is on the clipboard. For a design with external references it adds: *This design has external references. Sharing this design may share the referenced designs depending on the team member's permissions.*
4. Paste the link into an email or chat message.

## What the link contains

```
fusion360://lineageUrn=<document id>&hubUrl=<hub url>&documentName=<document name>
```

All three values are URL-encoded; the hub URL is written in upper case.

## Limitations

- The `fusion360://` link is handled by the Fusion installation on the recipient's computer. It does nothing in a browser on a machine without Fusion.
- The recipient needs access to every referenced design for the full assembly to open.
- The external-reference note appears only for design documents.

> **Developers:** see the [architecture notes](./arch/Get%20Open%20on%20Desktop%20Link.md).

---

[Back to README](../README.md)

*Copyright © 2026 IMA LLC. All rights reserved.*
