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

## Related commands

- [Document Project Members](document-project-members.md) — View all current members and their access levels.
- [Get a Share Link](get-a-share-link.md) — Share the document publicly without adding project members.

---

> **Developers:** see the [architecture notes](./Arch/Invite%20to%20Project.md).

---

*Copyright © 2026 IMA LLC. All rights reserved.*
