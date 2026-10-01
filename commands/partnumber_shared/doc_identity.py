# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.
"""Document identity across a pumped wait -- pure logic, no ``adsk`` import.

``pn_cache.commit_assignments`` pumps events for up to 15 s per attempt plus
backoff. A ``Document`` handle held across that wait can be invalidated by
background data-model work and fault natively on the next dereference
(AGENTS.md rule 3; a1d22e1, 11cfc51), and the user can switch, close or reload
the document in that time. The callers therefore capture an identity *before*
the wait, re-acquire ``app.activeDocument`` *after* it, and compare.

Identity is ``dataFile.id`` for a saved document and the document name as a
fallback for an unsaved one -- the same rule ``dochistory._document_identity``
and ``matchunits._document_key`` use. Two API calls never hand back the same
Python wrapper, so ``is`` / ``==`` on the Document objects is never the test.

``identity_of`` is duck-typed so it can be exercised with plain fakes here
and with real ``adsk.core.Document`` objects in Fusion.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DocIdentity:
    """What was known about a document at one instant."""

    data_file_id: str = ""
    name: str = ""

    @property
    def is_saved(self) -> bool:
        return bool(self.data_file_id)

    @property
    def is_empty(self) -> bool:
        """Nothing readable: no document, or every property read failed."""
        return not self.data_file_id and not self.name


class DocumentChanged(Exception):
    """The active document after a pumped wait is not the one before it.

    ``str(exc)`` is the user-facing text (see :func:`abort_message`).
    """


def identity_of(doc) -> DocIdentity:
    """Read a :class:`DocIdentity` from a Document-like object, never raising.

    Every property read is guarded: Fusion property reads on a detached
    wrapper can throw, and a ``None`` document must yield an empty identity.
    """
    if doc is None:
        return DocIdentity()
    data_file_id = ""
    try:
        data_file = doc.dataFile
        if data_file is not None:
            data_file_id = str(data_file.id or "")
    except Exception:
        data_file_id = ""
    name = ""
    try:
        name = str(doc.name or "")
    except Exception:
        name = ""
    return DocIdentity(data_file_id=data_file_id, name=name)


def same_document(before: DocIdentity, after: DocIdentity) -> bool:
    """True when *before* and *after* provably describe the same document.

    * Both saved: ``dataFile.id`` decides; the name is ignored (a rename does
      not change the document).
    * Neither saved: the name decides -- the only handle an unsaved document
      offers.
    * Exactly one saved: False. The saved state flipped during the wait, and
      the conservative answer costs a re-run, not a stamp on the wrong
      document.
    * Either side empty (no document, or unreadable): False.
    """
    if before.is_empty or after.is_empty:
        return False
    if before.is_saved and after.is_saved:
        return before.data_file_id == after.data_file_id
    if before.is_saved or after.is_saved:
        return False
    return before.name == after.name


def describe(identity: DocIdentity) -> str:
    """Short log form: the id for a saved document, ``unsaved:<name>`` else."""
    if identity.is_empty:
        return "<none>"
    if identity.is_saved:
        return identity.data_file_id
    return "unsaved:" + identity.name


def abort_message(reserved: str, cache_version: int) -> str:
    """User text for the document-changed abort.

    States what is already durable: ``commit_assignments`` has persisted the
    counter bump to pn-cache.json by the time the callers re-acquire the
    document, so the numbers in *reserved* are consumed whether or not they
    were stamped. Nothing on the document has been touched.
    """
    version = f" (pn-cache.json v{cache_version})" if cache_version else ""
    return (
        "The document changed while the part-number cache was uploading; "
        "nothing was stamped.\n\n"
        f"{reserved} already reserved in the hub Pn-Cache{version} and will "
        "not be reused. Re-run the command on the intended document to assign "
        "the next number."
    )
