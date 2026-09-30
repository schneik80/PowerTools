# Document Project Members — Architecture

[← Document Project Members guide](../Document%20Project%20Members.md)

| | |
|---|---|
| **Command ID** | `PTSHD_projectMembers` (`CMD_NAME` is `Document Project Members...`) |
| **Registry** | group `share` (`Share Document`); enabled by default; last in the group's start order |
| **UI location** | the `shareDropMenu` ("Share Menu") flyout on `QATRight`; appended (`addCommand(cmd_def, "", False)`), last in registry start order (issue #21) |
| **Files** | `commands/projectMembers/entry.py` (no `__init__.py`); `resources/` (16 light/dark, `16x16@2x-dark`, 32 light PNGs) |
| **Shared helpers** | [`ptutil.add_handler`](architecture.md#event_utils); [`ptutil.isSaved`, `log`, `handle_error`](architecture.md#general_utils); [`ptutil.remove_from_qat_right_flyout`](architecture.md#ui_utils); [`config`](architecture.md#config) (workspace/panel constants are imported but unused) |
| **Tests** | none beyond `tests/test_command_contract.py` |

## Purpose

Opens the Fusion Team "Members" page for the project that holds the active document in the default web browser, where access levels can be reviewed and changed. The project URL is derived from the document's `fusionWebURL`, so the document must be saved and in a project.

## How it is wired

- `start()`: `addButtonDefinition`; `commandCreated` → `command_created`; find-or-create the `shareDropMenu` flyout on `QATRight` (see [Get a Share Link](Get%20a%20Share%20Link.md)); `dropDown.controls.addCommand(cmd_def, "", False)` (appended).
- `stop()`: [`ptutil.remove_from_qat_right_flyout(CMD_ID, "shareDropMenu")`](architecture.md#ui_utils), then delete the definition. `commands/__init__.py` stops commands newest-first, so this is the first share command to stop and the flyout survives until the last sibling's control is removed (unless this is the only enabled share command).
- `command_created(args)`: wires `destroy` → `command_destroy`, then runs the whole command inline. No inputs and no `execute` handler: the Share Menu is live with no document open, where Fusion never raises `execute` (issue #16; [pattern](architecture.md#acting-from-commandcreated-when-there-are-no-inputs)).
- The body (formerly `command_execute`): [`ptutil.isSaved()`](architecture.md#general_utils) false → return. Then, inside a `try` ending in `ptutil.handle_error(CMD_NAME)`: `ui.progressBar.showBusy("Generating Share Link")`; build the URL (below); `ptutil.log` it (the log line says "Invite Link"); `progressBar.hide()`; `webbrowser.open(shareLink)`. No message box is shown.
- `command_destroy(args)`: resets `local_handlers`.

## URL construction

1. `rootLink = quote(app.activeDocument.dataFile.fusionWebURL)`.
2. `rootLink = rootLink.rpartition("/")[0]` — drops the last path segment (the file), leaving the project-level URL.
3. `rootLink = urllib.parse.unquote(rootLink)`.
4. `shareLink = f"{rootLink}==/fpV2?redirectSource=fremont&action=ffpViewMembers"`.

Identical to [Invite to Project](Invite%20to%20Project.md) except for the `action` value.

## Data and state

None.

## Diagram

None: the flow is linear (guard, build URL, open browser).

## Key API surface

| API element | Purpose |
|---|---|
| `app.activeDocument.dataFile.fusionWebURL` | Base URL the project URL is cut from |
| `urllib.parse.quote` / `unquote` | Encoding round-trip around the path cut |
| `webbrowser.open(url)` | Opens the members page in the system default browser |

## Tests

- `tests/test_command_contract.py` — registry/doc/description contract; `PTSHD_projectMembers` is checked against the ID shape.

Not covered: `entry.py` is Fusion-bound and is not exercised by the suite; nothing here is verified in Fusion on this branch except by the AST guards in `tests/test_command_contract.py` and `tests/test_command_abort.py`, which import it under the `adsk` stub. The icon set is not pinned in `tests/test_command_icons.py`.

---

*Copyright © 2026 IMA LLC. All rights reserved.*
