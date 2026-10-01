"""Unit tests for ``partnumber_shared.doc_identity``.

The module backs the rule-3 re-acquire check in Assign Part Numbers and
Assign Drawing Number: identity captured before ``commit_assignments`` pumps
events, compared against ``app.activeDocument`` afterwards. It has no Fusion
dependency; ``identity_of`` is duck-typed, so the fakes below stand in for
``adsk.core.Document``. Loaded via its package path with the conftest
scaffolding (package-relative imports elsewhere in the package).
"""

import importlib
from pathlib import Path
from types import SimpleNamespace

import pytest

PT_PKG = Path(__file__).resolve().parent.parent.name
doc_identity = importlib.import_module(
    f"{PT_PKG}.commands.partnumber_shared.doc_identity"
)

DocIdentity = doc_identity.DocIdentity

_URN_A = "urn:adsk.wipprod:dm.lineage:aaaaaaaaaaaaaaaaaaaaaa"
_URN_B = "urn:adsk.wipprod:dm.lineage:bbbbbbbbbbbbbbbbbbbbbb"


class _Raising:
    """Every attribute read raises, like a detached Fusion wrapper."""

    def __getattr__(self, name):
        raise RuntimeError(f"detached: {name}")


# --- identity_of ------------------------------------------------------------


def test_identity_of_saved_document_reads_data_file_id_and_name():
    doc = SimpleNamespace(dataFile=SimpleNamespace(id=_URN_A), name="Bracket v3")
    ident = doc_identity.identity_of(doc)
    assert ident == DocIdentity(data_file_id=_URN_A, name="Bracket v3")
    assert ident.is_saved
    assert not ident.is_empty


def test_identity_of_unsaved_document_has_name_only():
    doc = SimpleNamespace(dataFile=None, name="Untitled")
    ident = doc_identity.identity_of(doc)
    assert ident == DocIdentity(data_file_id="", name="Untitled")
    assert not ident.is_saved


def test_identity_of_none_is_empty():
    ident = doc_identity.identity_of(None)
    assert ident.is_empty
    assert ident == DocIdentity()


def test_identity_of_never_raises_on_detached_wrapper():
    assert doc_identity.identity_of(_Raising()).is_empty


def test_identity_of_tolerates_data_file_whose_id_read_raises():
    doc = SimpleNamespace(dataFile=_Raising(), name="Still named")
    assert doc_identity.identity_of(doc) == DocIdentity(name="Still named")


# --- same_document ----------------------------------------------------------


@pytest.mark.parametrize(
    "before, after, expected",
    [
        # Both saved: the id decides, the name does not.
        (DocIdentity(_URN_A, "a"), DocIdentity(_URN_A, "a"), True),
        (DocIdentity(_URN_A, "a"), DocIdentity(_URN_A, "renamed"), True),
        (DocIdentity(_URN_A, "same"), DocIdentity(_URN_B, "same"), False),
        # Neither saved: the name is all there is.
        (DocIdentity("", "Untitled"), DocIdentity("", "Untitled"), True),
        (DocIdentity("", "Untitled"), DocIdentity("", "Untitled(1)"), False),
        # Saved state flipped during the wait: conservative False.
        (DocIdentity("", "Bracket"), DocIdentity(_URN_A, "Bracket"), False),
        (DocIdentity(_URN_A, "Bracket"), DocIdentity("", "Bracket"), False),
        # Either side unknown: never "same".
        (DocIdentity(), DocIdentity(), False),
        (DocIdentity(_URN_A, "a"), DocIdentity(), False),
        (DocIdentity(), DocIdentity(_URN_A, "a"), False),
    ],
)
def test_same_document(before, after, expected):
    assert doc_identity.same_document(before, after) is expected


def test_same_document_round_trips_through_identity_of():
    """The real call shape: two wrappers for one saved document."""
    wrapper_1 = SimpleNamespace(dataFile=SimpleNamespace(id=_URN_A), name="x")
    wrapper_2 = SimpleNamespace(dataFile=SimpleNamespace(id=_URN_A), name="x")
    assert wrapper_1 is not wrapper_2
    assert doc_identity.same_document(
        doc_identity.identity_of(wrapper_1), doc_identity.identity_of(wrapper_2)
    )
    assert not doc_identity.same_document(
        doc_identity.identity_of(wrapper_1), doc_identity.identity_of(None)
    )


# --- describe / abort_message ----------------------------------------------


def test_describe_forms():
    assert doc_identity.describe(DocIdentity(_URN_A, "n")) == _URN_A
    assert doc_identity.describe(DocIdentity("", "Untitled")) == "unsaved:Untitled"
    assert doc_identity.describe(DocIdentity()) == "<none>"


def test_abort_message_names_the_consumed_numbers_and_cache_version():
    msg = doc_identity.abort_message("PRT-000012, ASY-000003", 7)
    assert msg.startswith(
        "The document changed while the part-number cache was uploading; "
        "nothing was stamped."
    )
    assert "PRT-000012, ASY-000003" in msg
    assert "pn-cache.json v7" in msg
    assert "will not be reused" in msg


def test_abort_message_omits_version_when_unknown():
    msg = doc_identity.abort_message("DWG-000004", 0)
    assert "pn-cache.json v" not in msg
    assert "DWG-000004" in msg


def test_document_changed_carries_its_message():
    exc = doc_identity.DocumentChanged(doc_identity.abort_message("DWG-000001", 2))
    assert isinstance(exc, Exception)
    assert "nothing was stamped" in str(exc)
