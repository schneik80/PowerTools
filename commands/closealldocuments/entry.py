# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.
"""Close All Documents.

Closes every open document in one pass. Documents with nothing to save close
straight away; the rest are covered by a single Save / Don't Save / Cancel
prompt whose answer is applied to all of them, replacing the per-document native
prompt Fusion shows when documents are closed one at a time.

All work runs in ``command_created`` rather than an execute handler. The Fusion
API states that closing a document is not supported within any of the command
related events, so this command has to finish and return before a command
transaction opens. ``commands/refresh`` (which closes the active document) and
``commands/datatoggle`` use the same launcher shape.

Document handles are re-validated before every close. A handle held across a
pumped wait can be invalidated by background data-model work, and dereferencing
a stale one faults natively (0xC0000005 in NsDataModel10.dll) rather than
raising — the failure mode already seen in the Bottom-Up Update save/close
cycle, which is why each close is followed by a short event pump.
"""

from dataclasses import dataclass, field

import adsk.core

from ...lib import ptAddInUtils as ptutil
from . import logic

app = adsk.core.Application.get()
ui = app.userInterface

CMD_NAME = "Close All Documents"
CMD_ID = "PTND_closealldocuments"
CMD_Description = (
    "Close every open document, saving or discarding unsaved changes as a group"
)

# Version comment written by the group save.
SAVE_DESCRIPTION = "Saved by PowerTools Close All Documents"

# Seconds to let a close drain before the next one is queued. Matches the pump
# used by the Bottom-Up Update close cycle.
CLOSE_SETTLE_SECONDS = 0.25

# Local list of event handlers used to maintain a reference so
# they are not released and garbage collected.
local_handlers = []


@dataclass
class _Tally:
    """Running counts for the debug log, and anything that did not close.

    ``left_open`` holds ``(name, reason)`` pairs for documents that were meant
    to close but did not — the only outcome worth interrupting the user for.
    ``cancelled`` is kept separate: the user already knows they cancelled, so
    that case reports nothing, but it still has to suppress the final sweep.
    """

    closed: int = 0
    saved: int = 0
    discarded: int = 0
    cancelled: bool = False
    left_open: list = field(default_factory=list)


# Executed when add-in is run.
def start():
    cmd_def = ui.commandDefinitions.addButtonDefinition(
        CMD_ID, CMD_NAME, CMD_Description
    )
    ptutil.add_handler(cmd_def.commandCreated, command_created)

    file_dd = ptutil.get_qat_file_dropdown()
    if file_dd:
        file_dd.controls.addCommand(cmd_def, "ExportCommand", False)


# Executed when add-in is stopped.
def stop():
    ptutil.remove_from_qat_file_dropdown(CMD_ID)
    command_definition = ui.commandDefinitions.itemById(CMD_ID)
    if command_definition:
        command_definition.deleteMe()


# Function that is called when a user clicks the corresponding button in the UI.
# The whole command runs here: closing documents is not allowed once a command
# transaction has opened, so there is no execute handler to defer the work to.
def command_created(args: adsk.core.CommandCreatedEventArgs):
    ptutil.log(f"{CMD_NAME} Command Event")
    try:
        _close_all_documents()
    except Exception:
        ptutil.handle_error(CMD_NAME, show_message_box=True)


def _close_all_documents():
    """Close the clean documents, then settle the rest with one prompt."""
    docs = logic.snapshot_documents(app.documents)
    if not docs:
        ui.messageBox("There are no open documents to close.", CMD_NAME)
        return

    clean, dirty, new = logic.partition_documents(docs)
    tally = _Tally()

    # Documents with nothing to save close without asking.
    for doc in clean:
        _close_and_tally(doc, tally)

    if dirty or new:
        _resolve_modified_documents(dirty, new, tally)

    # Only sweep when everything else went as planned. Documents still open --
    # cancelled, or failed to save -- hold invisible children, and closing a
    # child out from under its open parent is exactly what the sweep must not do.
    if not tally.left_open and not tally.cancelled:
        tally.closed += _sweep_released_documents()

    # The counts go to the debug log rather than a message box: a clean sweep
    # needs no report, since the emptied tabs are the report. Only documents
    # that did not close are worth interrupting for.
    ptutil.log(
        f"{CMD_NAME}: closed={tally.closed} saved={tally.saved} "
        f"discarded={tally.discarded} left_open={len(tally.left_open)}"
    )
    if tally.left_open:
        ui.messageBox(logic.format_left_open(tally.left_open), CMD_NAME)


def _resolve_modified_documents(dirty, new, tally):
    """Ask once about the documents with unsaved changes, then act on all of them.

    Arguments:
    dirty -- Modified documents that have been saved before.
    new -- Modified documents that have never been saved.
    tally -- Counts to update in place.
    """
    modified = dirty + new
    answer = ui.messageBox(
        logic.format_save_prompt([logic.document_name(doc) for doc in modified]),
        CMD_NAME,
        adsk.core.MessageBoxButtonTypes.YesNoCancelButtonType,
        adsk.core.MessageBoxIconTypes.QuestionIconType,
    )

    if answer == adsk.core.DialogResults.DialogCancel:
        tally.cancelled = True
        return

    if answer == adsk.core.DialogResults.DialogYes:
        _save_then_close(dirty, tally)
        _close_via_fusion_prompt(new, tally)
        return

    for doc in modified:
        _close_and_tally(doc, tally, discarding=True)


def _save_then_close(docs, tally):
    """Save each previously-saved document, then close it.

    A document whose save fails or times out is left open rather than closed, so
    changes are never lost to a failed upload.
    """
    if not docs:
        return
    progress = ui.progressBar
    try:
        for doc in docs:
            name = logic.document_name(doc)
            progress.showBusy(f"{CMD_NAME} - saving {name}...")
            adsk.doEvents()
            ok, message = _save_document(doc, name)
            if not ok:
                ptutil.log(f"{CMD_NAME}: {message}")
                tally.left_open.append((name, "could not be saved"))
                continue
            tally.saved += 1
            _close_and_tally(doc, tally)
    finally:
        progress.hide()


def _save_document(doc, name):
    """Save one document and wait for its upload to finish.

    Activating first keeps the save on the document Fusion considers current,
    matching how the rest of the add-in saves.

    Arguments:
    doc -- The document to save.
    name -- Its name, already read defensively, used for logging.

    Returns:
    An ``(ok, message)`` pair from ``ptutil.wait_for_upload``.
    """
    try:
        doc.activate()
        ptutil.pump_events_for(CLOSE_SETTLE_SECONDS)
        save_result = doc.save(SAVE_DESCRIPTION)
    except Exception as save_error:
        return False, f"save call failed for {name}: {save_error}"
    return ptutil.wait_for_upload(save_result, name, document=doc, log_fn=ptutil.log)


def _close_via_fusion_prompt(docs, tally):
    """Close never-saved documents, letting Fusion collect a name and folder.

    ``doc.save()`` cannot write a document that has never been saved — an
    initial save needs saveAs with a name and folder — so ``close(True)`` hands
    the document to Fusion's own Save dialog. Fusion reports whether the close
    went through, so a user who cancels that dialog keeps the document. These
    are not counted as saved: Fusion's prompt also offers Don't Save, and there
    is no way to tell afterwards which the user picked.
    """
    for doc in docs:
        name = logic.document_name(doc)
        try:
            if not doc.isValid:
                tally.closed += 1
                continue
            if not doc.close(True):
                tally.left_open.append((name, "save was cancelled"))
                continue
        except Exception as close_error:
            ptutil.log(f"{CMD_NAME}: could not close {name}: {close_error}")
            tally.left_open.append((name, "could not be closed"))
            continue
        tally.closed += 1
        ptutil.pump_events_for(CLOSE_SETTLE_SECONDS)


def _sweep_released_documents() -> int:
    """Close anything Fusion still holds open once the main pass is done.

    Referenced children are opened invisibly and are only released when their
    parent closes, so a second look at the collection catches the leftovers.
    Only documents with nothing to save are swept; anything still holding
    changes reached that state deliberately above.

    Returns:
    How many documents the sweep closed.
    """
    closed = 0
    for doc in logic.snapshot_documents(app.documents):
        if logic.classify_document(doc) != logic.CLEAN:
            continue
        if _close_quietly(doc):
            closed += 1
    return closed


def _close_and_tally(doc, tally, discarding: bool = False):
    """Close one document without prompting and record the outcome."""
    if _close_quietly(doc):
        tally.closed += 1
        if discarding:
            tally.discarded += 1
    else:
        tally.left_open.append((logic.document_name(doc), "could not be closed"))


def _close_quietly(doc) -> bool:
    """Close *doc*, discarding any changes. Returns True when it is gone.

    Re-validates the handle first: one held across a pumped wait can be
    invalidated by background data-model work, and dereferencing a stale handle
    faults natively rather than raising. An already-invalid handle counts as
    closed, because the document it referred to is gone either way. Pumps
    briefly afterwards so the close drains before the next one is queued.
    """
    name = logic.document_name(doc)
    try:
        if not doc.isValid:
            return True
        doc.close(False)
    except Exception as close_error:
        ptutil.log(f"{CMD_NAME}: could not close {name}: {close_error}")
        return False
    ptutil.pump_events_for(CLOSE_SETTLE_SECONDS)
    return True


# This event handler is called when the command terminates.
def command_destroy(args: adsk.core.CommandEventArgs):
    # General logging for debug.
    ptutil.log(f"{CMD_NAME} Command Destroy Event")

    global local_handlers
    local_handlers = []
