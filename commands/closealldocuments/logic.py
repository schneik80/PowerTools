# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.
"""Pure, Fusion-free helpers for the Close All Documents command.

Kept separate from ``entry.py`` so the "which documents need asking about"
decision and the report wording can be unit-tested without a live Fusion
runtime (see ``tests/test_closealldocuments_logic.py``).

Nothing here imports ``adsk``. The document helpers are duck-typed on the
shapes Fusion exposes — ``count`` / ``item(i)`` for the collection and
``name`` / ``isModified`` / ``dataFile`` / ``isVisible`` for a document — the
same approach ``bottomupupdate._collect_stray_documents`` uses so tests can
drive them with stand-ins.

Every attribute read is guarded. A document handle can go stale at any moment
(Fusion closes referenced children on its own), and a sweep that aborts partway
through is worse than one that skips the document it could not read.
"""

from __future__ import annotations

# Classification of an open document, deciding how it is closed.
CLEAN = "clean"  # nothing to save; close without asking
DIRTY = "dirty"  # modified and saved before, so doc.save() can save it
NEW = "new"  # modified but never saved; needs Fusion's own Save dialog


def document_name(doc) -> str:
    """Read a document's name, tolerating an invalid or unreadable handle."""
    try:
        return doc.name or "(unnamed)"
    except Exception:
        return "(unknown document)"


def snapshot_documents(documents) -> list:
    """Copy the live documents collection into a plain list.

    Closing a document mutates ``app.documents``, so the set to act on has to be
    captured before the first close rather than iterated live. Items that cannot
    be read are skipped instead of aborting the sweep.

    Arguments:
    documents -- A Fusion ``Documents`` collection (``count`` / ``item(i)``).

    Returns:
    The open documents, in collection order.
    """
    docs = []
    try:
        count = documents.count
    except Exception:
        return docs
    for index in range(count):
        try:
            doc = documents.item(index)
        except Exception:
            continue
        if doc is not None:
            docs.append(doc)
    return docs


def classify_document(doc) -> str:
    """Decide how one open document has to be closed.

    Returns ``CLEAN`` when there is nothing to save, ``DIRTY`` when the document
    has changes and has been saved before (so ``doc.save()`` can write them), or
    ``NEW`` when it has changes but no ``dataFile`` — an initial save needs a
    name and folder, which only Fusion's own Save dialog can collect.

    Unreadable handles fall to the cautious side: a document whose ``isModified``
    cannot be read is treated as ``DIRTY`` so it is never discarded without the
    save prompt covering it, and one whose ``dataFile`` cannot be read is treated
    as ``NEW`` so Fusion decides how to save it.
    """
    try:
        modified = bool(doc.isModified)
    except Exception:
        return DIRTY
    if not modified:
        return CLEAN
    try:
        has_data_file = doc.dataFile is not None
    except Exception:
        has_data_file = False
    return DIRTY if has_data_file else NEW


def partition_documents(docs) -> tuple:
    """Split open documents into the clean, dirty, and never-saved buckets.

    Arguments:
    docs -- Open documents, as returned by ``snapshot_documents``.

    Returns:
    A ``(clean, dirty, new)`` tuple of lists, each ordered visible-first.
    """
    buckets = {CLEAN: [], DIRTY: [], NEW: []}
    for doc in docs:
        buckets[classify_document(doc)].append(doc)
    return (
        _visible_first(buckets[CLEAN]),
        _visible_first(buckets[DIRTY]),
        _visible_first(buckets[NEW]),
    )


def format_save_prompt(names) -> str:
    """Build the single prompt covering every document with unsaved changes."""
    count = len(names)
    listed = "\n".join(f"    {name}" for name in names)
    return (
        f"{count} open document{_plural(count)} "
        f"{'has' if count == 1 else 'have'} unsaved changes:\n\n"
        f"{listed}\n\n"
        "Save the changes before closing?\n\n"
        "Yes - save each document, then close it.\n"
        "No - close them and discard the changes.\n"
        "Cancel - leave them open."
    )


def format_left_open(left_open) -> str:
    """Build the report naming the documents that are still open, and why.

    A successful close needs no report — the empty tabs say so. This is only
    shown when something did not close, so it covers just that: a save that
    failed, a Save dialog the user cancelled, or a close Fusion refused.

    Arguments:
    left_open -- ``(name, reason)`` pairs for documents that are still open.

    Returns:
    Plain text suitable for a message box.
    """
    count = len(left_open)
    lines = [
        f"{count} document{_plural(count)} {'is' if count == 1 else 'are'} still open:",
        "",
    ]
    lines.extend(f"    {name} - {reason}" for name, reason in left_open)
    return "\n".join(lines)


def _visible_first(docs) -> list:
    """Order a bucket so visible documents close before invisible ones.

    Fusion opens referenced children invisibly and releases them when their
    parent closes, so closing the visible parents first usually leaves nothing
    to do for the children.
    """
    return sorted(docs, key=lambda doc: 0 if _is_visible(doc) else 1)


def _is_visible(doc) -> bool:
    """Report whether a document is shown as a tab, defaulting to True."""
    try:
        return bool(doc.isVisible)
    except Exception:
        return True


def _plural(count: int) -> str:
    """Return the plural suffix for *count*."""
    return "" if count == 1 else "s"
