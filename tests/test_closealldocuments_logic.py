"""Unit tests for the Close All Documents pure-logic helpers.

Exercises the decision the command turns on — which open documents can close
without asking, which need the save prompt, and which have never been saved and
so need Fusion's own Save dialog — plus the wording of the prompt and the
closing report. These helpers have no Fusion dependency and are duck-typed on
the ``app.documents`` collection shape, so they run against the stand-ins below;
the module uses package-relative imports, so it is loaded via its full package
path with the conftest scaffolding in place.
"""

import importlib
from pathlib import Path

PT_PKG = Path(__file__).resolve().parent.parent.name
logic = importlib.import_module(f"{PT_PKG}.commands.closealldocuments.logic")


class FakeDoc:
    """Stand-in for adsk.core.Document."""

    def __init__(self, name, is_modified=False, has_data_file=True, is_visible=True):
        self.name = name
        self.isModified = is_modified
        self.dataFile = object() if has_data_file else None
        self.isVisible = is_visible


class RaisingDoc:
    """Document whose attributes raise, to exercise the guard paths."""

    def __init__(self, *, name=True, modified=True, data_file=True):
        self._raise_name = name
        self._raise_modified = modified
        self._raise_data_file = data_file

    @property
    def name(self):
        if self._raise_name:
            raise RuntimeError("name unavailable")
        return "Readable"

    @property
    def isModified(self):
        if self._raise_modified:
            raise RuntimeError("isModified unavailable")
        return True

    @property
    def dataFile(self):
        if self._raise_data_file:
            raise RuntimeError("dataFile unavailable")
        return object()

    @property
    def isVisible(self):
        return True


class FakeDocuments:
    """Stand-in for the app.documents collection (count / item(i))."""

    def __init__(self, docs):
        self._docs = list(docs)

    @property
    def count(self):
        return len(self._docs)

    def item(self, index):
        return self._docs[index]


class BrokenDocuments:
    """Collection whose count raises, to exercise the guard path."""

    @property
    def count(self):
        raise RuntimeError("collection unavailable")


class PartlyBrokenDocuments(FakeDocuments):
    """Collection whose second item raises, to prove the sweep continues."""

    def item(self, index):
        if index == 1:
            raise RuntimeError("item unavailable")
        return self._docs[index]


# ---------------------------------------------------------------------------
# snapshot_documents
# ---------------------------------------------------------------------------


def test_snapshot_copies_the_collection_in_order() -> None:
    """The snapshot is a plain list, taken before anything is closed."""
    a, b = FakeDoc("A"), FakeDoc("B")

    assert logic.snapshot_documents(FakeDocuments([a, b])) == [a, b]


def test_snapshot_of_an_empty_collection_is_empty() -> None:
    assert logic.snapshot_documents(FakeDocuments([])) == []


def test_snapshot_skips_unreadable_items() -> None:
    """One bad item must not abort the whole sweep."""
    a, b, c = FakeDoc("A"), FakeDoc("B"), FakeDoc("C")

    assert logic.snapshot_documents(PartlyBrokenDocuments([a, b, c])) == [a, c]


def test_snapshot_skips_none_items() -> None:
    assert logic.snapshot_documents(FakeDocuments([None])) == []


def test_broken_collection_degrades_to_no_documents() -> None:
    assert logic.snapshot_documents(BrokenDocuments()) == []


# ---------------------------------------------------------------------------
# classify_document
# ---------------------------------------------------------------------------


def test_unmodified_document_is_clean() -> None:
    assert logic.classify_document(FakeDoc("A", is_modified=False)) == logic.CLEAN


def test_unmodified_and_never_saved_document_is_still_clean() -> None:
    """An untouched new design has nothing to lose, so it needs no prompt."""
    doc = FakeDoc("Untitled", is_modified=False, has_data_file=False)

    assert logic.classify_document(doc) == logic.CLEAN


def test_modified_and_previously_saved_document_is_dirty() -> None:
    assert logic.classify_document(FakeDoc("A", is_modified=True)) == logic.DIRTY


def test_modified_and_never_saved_document_is_new() -> None:
    """No dataFile means doc.save() cannot work; Fusion must collect a folder."""
    doc = FakeDoc("Untitled", is_modified=True, has_data_file=False)

    assert logic.classify_document(doc) == logic.NEW


def test_unreadable_modified_flag_falls_back_to_dirty() -> None:
    """Never discard a document whose state could not be read."""
    assert logic.classify_document(RaisingDoc(modified=True)) == logic.DIRTY


def test_unreadable_data_file_falls_back_to_new() -> None:
    """If we cannot tell whether it was saved, let Fusion decide how to save it."""
    doc = RaisingDoc(modified=False, data_file=True)

    assert logic.classify_document(doc) == logic.NEW


# ---------------------------------------------------------------------------
# partition_documents
# ---------------------------------------------------------------------------


def test_partition_splits_the_three_buckets() -> None:
    clean = FakeDoc("Clean")
    dirty = FakeDoc("Dirty", is_modified=True)
    new = FakeDoc("Untitled", is_modified=True, has_data_file=False)

    assert logic.partition_documents([dirty, new, clean]) == ([clean], [dirty], [new])


def test_partition_of_all_clean_documents_needs_no_prompt() -> None:
    """The no-dialog path: nothing lands in the dirty or new buckets."""
    docs = [FakeDoc("A"), FakeDoc("B")]

    _, dirty, new = logic.partition_documents(docs)

    assert dirty == [] and new == []


def test_partition_of_nothing_is_three_empty_buckets() -> None:
    assert logic.partition_documents([]) == ([], [], [])


def test_visible_documents_are_ordered_before_invisible_ones() -> None:
    """Closing a visible parent first releases the children it holds open."""
    child = FakeDoc("Child", is_visible=False)
    parent = FakeDoc("Parent ASSY", is_visible=True)

    clean, _, _ = logic.partition_documents([child, parent])

    assert [doc.name for doc in clean] == ["Parent ASSY", "Child"]


def test_ordering_is_stable_within_a_visibility_group() -> None:
    a, b = FakeDoc("A"), FakeDoc("B")

    clean, _, _ = logic.partition_documents([a, b])

    assert clean == [a, b]


# ---------------------------------------------------------------------------
# document_name
# ---------------------------------------------------------------------------


def test_document_name_reads_the_name() -> None:
    assert logic.document_name(FakeDoc("Chassis")) == "Chassis"


def test_document_name_survives_an_unreadable_handle() -> None:
    assert logic.document_name(RaisingDoc(name=True)) == "(unknown document)"


def test_document_name_falls_back_for_a_blank_name() -> None:
    assert logic.document_name(FakeDoc("")) == "(unnamed)"


# ---------------------------------------------------------------------------
# format_save_prompt / format_left_open
# ---------------------------------------------------------------------------


def test_prompt_lists_every_modified_document() -> None:
    text = logic.format_save_prompt(["Chassis", "Bracket"])

    assert "2 open documents have unsaved changes" in text
    assert "Chassis" in text and "Bracket" in text


def test_prompt_is_singular_for_one_document() -> None:
    text = logic.format_save_prompt(["Chassis"])

    assert "1 open document has unsaved changes" in text


def test_prompt_explains_all_three_buttons() -> None:
    text = logic.format_save_prompt(["Chassis"])

    assert "Yes -" in text and "No -" in text and "Cancel -" in text


def test_left_open_names_each_document_with_a_reason() -> None:
    text = logic.format_left_open(
        [("Chassis", "could not be saved"), ("Bracket", "save was cancelled")]
    )

    assert "2 documents are still open:" in text
    assert "Chassis - could not be saved" in text
    assert "Bracket - save was cancelled" in text


def test_left_open_is_singular_for_one_document() -> None:
    text = logic.format_left_open([("Chassis", "could not be saved")])

    assert "1 document is still open:" in text
