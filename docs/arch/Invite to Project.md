# Invite to Project — Architecture

[← Invite to Project guide](../Invite%20to%20Project.md)

| | |
|---|---|
| **Command ID** | `PTSHD_projectInvite` (`CMD_NAME` is `Invite to Project...`) |
| **Registry** | group `share` (`Share Document`); enabled by default |
| **UI location** | the `shareDropMenu` ("Share Menu") flyout on `QATRight`; inserted before Change Share Settings (`addCommand(cmd_def, "PTSHD_sharesettings", True)`), which has already started in registry order |
| **Files** | `commands/projectInvite/entry.py` (no `__init__.py`); `resources/` (16 light/dark and `@2x` variants, 32 light/dark PNGs) |
| **Shared helpers** | [`ptutil.add_handler`](architecture.md#event_utils); [`ptutil.isSaved`, `log`, `handle_error`](architecture.md#general_utils); [`ptutil.remove_from_qat_right_flyout`](architecture.md#ui_utils); [`config`](architecture.md#config) (workspace/panel constants are imported but unused) |
| **Tests** | none beyond `tests/test_command_contract.py` |

## Purpose

Opens the Fusion Team "Invite Members" page for the project that holds the active document in the default web browser. The project URL is derived from the document's `fusionWebURL`, so the document must be saved and in a project.

## How it is wired

- `start()`: `addButtonDefinition`; `commandCreated` → `command_created`; find-or-create the `shareDropMenu` flyout on `QATRight` (see [Get a Share Link](Get%20a%20Share%20Link.md)); `dropDown.controls.addCommand(cmd_def, "PTSHD_sharesettings", True)`.
- `stop()`: [`ptutil.remove_from_qat_right_flyout(CMD_ID, "shareDropMenu")`](architecture.md#ui_utils), then delete the definition.
- `command_created(args)`: wires `execute` → `command_execute` and `destroy` → `command_destroy`; no inputs, so `execute` runs immediately when a document is open.
- `command_execute(args)`: [`ptutil.isSaved()`](architecture.md#general_utils) false → return. Then, inside a `try` ending in `ptutil.handle_error(CMD_NAME)`: `ui.progressBar.showBusy("Generating Share Link")`; build the URL (below); `ptutil.log` it; `progressBar.hide()`; `webbrowser.open(shareLink)`. No message box is shown.
- `command_destroy(args)`: resets `local_handlers`.

## URL construction

1. `rootLink = quote(app.activeDocument.dataFile.fusionWebURL)`.
2. `rootLink = rootLink.rpartition("/")[0]` — drops the last path segment (the file), leaving the project-level URL.
3. `rootLink = urllib.parse.unquote(rootLink)`.
4. `shareLink = f"{rootLink}==/fpV2?redirectSource=fremont&action=ffpInviteMembers"`.

[Document Project Members](Document%20Project%20Members.md) builds the same URL with `action=ffpViewMembers`.

## Data and state

None.

## Diagram

None: the flow is linear (guard, build URL, open browser).

## Key API surface

| API element | Purpose |
|---|---|
| `app.activeDocument.dataFile.fusionWebURL` | Base URL the project URL is cut from |
| `urllib.parse.quote` / `unquote` | Encoding round-trip around the path cut |
| `webbrowser.open(url)` | Opens the invite page in the system default browser |

## Tests

- `tests/test_command_contract.py` — registry/doc/description contract; `PTSHD_projectInvite` is checked against the ID shape and is the anchor literal Change Share Settings references.

Not covered: `entry.py` is Fusion-bound and is not exercised by the suite; nothing here is verified in Fusion on this branch except by the AST guards in `tests/test_command_contract.py` and `tests/test_command_abort.py`, which import it under the `adsk` stub. The icon set is not pinned in `tests/test_command_icons.py`.

---

*Copyright © 2026 IMA LLC. All rights reserved.*
