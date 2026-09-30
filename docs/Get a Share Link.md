# Get a Share Link

[Back to README](../README.md)

## Overview

Get a Share Link turns on public sharing for the active document and copies the share link to the clipboard.

Fusion's own share dialog takes several clicks and a copy step every time you need the link. This command does the whole sequence at once and tells you the state of the share (download allowed, password set, external references included) in the same message, so you know what the recipient will be able to do before you paste the link.

| Scenario | Use |
|---|---|
| Send a design for review to someone outside your organization | **Get a Share Link** |
| Share with someone who does not have Fusion installed | **Get a Share Link** |
| Share with a hub member who will edit in Fusion | [Get Open on Desktop Link](./Get%20Open%20on%20Desktop%20Link.md) |
| Share for review in the Fusion Team web client | [Get Open in Team Link](./Get%20Open%20in%20Team%20Link.md) |

## Prerequisites

- The active document must be saved to a hub. Otherwise the command asks you to save first.

## Where to find it

**Share Menu › Get a Share Link** on the right-hand Quick Access Toolbar.

## How to use

1. Open the document you want to share.
2. Select **Share Menu › Get a Share Link**. A progress indicator reads *Generating Share Link* while sharing is turned on and the link is fetched.
3. A **Share Document** dialog confirms the link is on the clipboard and reports the share state.
4. Paste the link wherever you need it.

## The result dialog

| Line | When it appears |
|---|---|
| The document was already shared | Sharing was on before this command ran |
| Downloading the document from the share link is allowed | Download is on |
| Downloading from the link is not turned on. To enable downloading, go to **Share Settings** | Download is off |
| The share is password protected | A password is set |
| The share does not have a password. To set a password, go to **Share Settings** | No password |
| This design has external references. Sharing this design will also share the referenced designs. To avoid sharing referenced designs, either save this design as a new document and break link or disable download | Design with external references, download on |
| This design has external references. Sharing this design will allow the referenced designs to be viewed but not downloaded | Design with external references, download off |

Change download and password settings with [Change Share Settings](./Change%20Share%20Settings.md).

## Limitations

- If Fusion's share command is unavailable, usually because the hub administrator has disabled sharing, a private link to the document's page in Fusion Team is copied instead, and the dialog says so. That link works only for hub members.
- Turning sharing on is a cloud round-trip and can take a few seconds.
- The external-reference lines appear only for design documents.

> **Developers:** see the [architecture notes](./arch/Get%20a%20Share%20Link.md).

---

[Back to README](../README.md)

*Copyright © 2026 IMA LLC. All rights reserved.*
