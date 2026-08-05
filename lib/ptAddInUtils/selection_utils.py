# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.
"""Capturing selection-input contents while a command dialog is open.

A ``SelectionCommandInput``'s contents are NOT reliably readable from the
``execute`` handler: Fusion may have released the selections by then, and
``selection(i)`` raises ``RuntimeError: 3 : invalid argument index`` even
though ``selectionCount`` reported entries. The risk is highest for
commands that defer work past the dialog (the CustomEvent pattern), where
execution happens well after the dialog closed.

The fix is to CAPTURE the picks while the dialog is still open -
``inputChanged`` and ``validateInputs`` both qualify - and to execute
from the captured entities. The entities themselves stay usable after
the dialog closes (proxies included); only the input's list does not.

Usage in a command module::

    _picks: dict = {}

    def command_input_changed(args):
        ptutil.capture_selections(args.inputs, _picks, "occurrence_sel")
        ...

    def command_execute(args):
        entity = ptutil.picked_one(_picks, "occurrence_sel")

Reset the store in ``command_destroy`` alongside ``local_handlers``.
"""

import adsk.core

from .general_utils import log

__all__ = ["capture_selections", "picked", "picked_one"]


def capture_selections(inputs, store: dict, *input_ids: str) -> None:
    """Snapshot the named selection inputs into *store*.

    Call from ``inputChanged`` and/or ``validateInputs`` - never from
    ``execute``. Reading stops at the first index that refuses rather
    than aborting the handler, so a partially-released input still
    yields what it can.

    Args:
        inputs: The command inputs collection from the event args.
        store: A dict owned by the command module, keyed by input id.
        input_ids: The selection input ids to capture.
    """
    for input_id in input_ids:
        selection = adsk.core.SelectionCommandInput.cast(inputs.itemById(input_id))
        if selection is None:
            continue
        entities = []
        try:
            count = selection.selectionCount
        except Exception:
            log(f"capture_selections: selectionCount failed for '{input_id}'.")
            continue
        for index in range(count):
            try:
                entities.append(selection.selection(index).entity)
            except Exception:
                break  # the input released the rest - keep what we have
        store[input_id] = entities


def picked(store: dict, input_id: str) -> list:
    """The entities captured for *input_id* (empty when nothing was picked)."""
    return store.get(input_id) or []


def picked_one(store: dict, input_id: str):
    """The single entity captured for *input_id*, else None."""
    entities = picked(store, input_id)
    return entities[0] if len(entities) == 1 else None
