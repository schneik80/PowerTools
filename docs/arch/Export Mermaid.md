# Export Mermaid Diagram — Architecture

[← Export Mermaid Diagram guide](../Export%20Mermaid.md)

| | |
|---|---|
| **Command ID** | `PTE_exportmermaid` (`CMD_NAME = "Export Mermaid Diagram..."`) |
| **Registry** | group `exports` (`Exports`); enabled by default |
| **UI location** | QAT **File** dropdown (`FileSubMenuCommand`), `controls.addCommand(cmd_def, "ExportCommand", True)` — directly before Fusion's **Export** item; no icon folder |
| **Files** | `commands/exportmermaid/entry.py` only |
| **Shared helpers** | [`ptutil.add_handler`](architecture.md#event_utils), [`ptutil.log`, `ptutil.handle_error`](architecture.md#general_utils) |
| **Tests** | none of its own; `tests/test_command_contract.py`, `tests/test_command_abort.py` |

## Purpose

Writes the active design's occurrence tree as a Mermaid `graph LR` flowchart to `<document name>.mmd` in a folder the user picks, then opens the same diagram in the Mermaid Live viewer in the system browser. One edge per parent/child occurrence pair; node ids are the occurrence names with Mermaid-hostile characters removed. There is no dialog and no options: the whole command is one `execute`.

## How it is wired

- `start()`: `addButtonDefinition(CMD_ID, CMD_NAME, CMD_Description)`, `command_created` on `commandCreated` (global handler list), then adds the control to the File dropdown before `ExportCommand`.
- `stop()`: deletes the File-dropdown control and the definition.
- `command_created(args)`: registers `command_destroy`, then `ptutil.require_document(CMD_NAME, "design")`; with no active design it shows the standard message ("Export Mermaid Diagram needs a design open. Open or create a design, then retry.") and returns. Otherwise it calls `_export_mermaid(design)` inside a `try`. There are no inputs and no `execute` handler: the control sits in the File dropdown, which exists on the start screen, and `execute` never fires there (rule 1, #25).
- `_export_mermaid(design)`:
  1. `resultString` = a `%%{init: ...}%%` front-matter block (theme `base`, look `classic`, layout `elk`, five `themeVariables`) + `graph LR\n`.
  2. `traverseAssembly(design.parentDocument.name, rootComp.occurrences.asList, 1, resultString)` — see below.
  3. `ui.createFolderDialog()` ("Choose Folder to save Mermaid Graph"); on `DialogOK` writes `os.path.join(folder, safe_name + ".mmd")` (`safe_name` replaces `<>:"/\|?*` in the document name with `_`), UTF-8; shows "Graph saved at: <path>"; then encodes `{"code": <mermaid>, "mermaid": "{\"theme\": \"base\"}"}` as base64 and calls `webbrowser.open("https://mermaid.live/view#base64:<state>")`. Cancel -> return, nothing written and no browser.
  4. Exceptions (caught in `command_created`) -> `ptutil.handle_error(CMD_NAME, show_message_box=True)`.
- `command_destroy(args)`: resets `local_handlers`.

### Tree walk

`traverseAssembly(sParent, occurrences, currentLevel, inputString)` iterates `occurrences.item(i)`. For each occurrence it sanitises both `occ.name` and `sParent` — `-`, `<`, `>` become `_`; `"`, `=`, `(`, `)` are deleted — builds `"<parent> --> <child>\n"`, deletes every space in that line, appends it, and recurses into `occ.childOccurrences` with the **unsanitised** `occ.name` as the new parent (it is sanitised again at the next level). The root's label is the document name; child ids are occurrence names including their `:<n>` instance suffix, so two instances of one component are two nodes. `currentLevel` is carried but unused.

## Data and state

- Module-level: `local_handlers` only.
- Output: `<sanitised document name>.mmd` in the chosen folder; the same text is also sent to `mermaid.live` in the URL fragment (the diagram content leaves the machine only as far as the browser; the fragment is not sent to the server by the browser, but the site renders it). No caches, settings, custom events or temp files.

## Tests

- `tests/test_command_contract.py` — `CMD_Description`, literal `CMD_ID` shape, registry/doc/README contract.
- `tests/test_command_abort.py` — the `doExecute` AST guard.

`entry.py` is Fusion-bound and is not exercised by the suite; nothing here is verified in Fusion on this branch except by the AST guards above, which import it under the `adsk` stub. `traverseAssembly` and the name sanitising are pure string logic but live in `entry.py` and have no tests; no icon set exists to pin.

---

*Copyright © 2026 IMA LLC. All rights reserved.*
