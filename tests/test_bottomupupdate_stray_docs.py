"""Unit tests for the stray-document helpers in ``bottomupupdate/entry.py``.

Fusion implicitly opens related documents (configuration members / configured
designs) while the Bottom-Up Update loop opens parents or updates references,
and never closes them. ``_open_document_index`` snapshots what is open at run
start; ``_collect_stray_documents`` identifies anything opened since, so the
loop can close it. Both operate on the ``app.documents`` collection shape
(``count`` / ``item(i)``) and are tested here with fakes; ``entry`` is imported
via the ``PowerTools.*`` scaffolding in ``conftest.py``.
"""

import importlib

entry = importlib.import_module("PowerTools.commands.bottomupupdate.entry")


class FakeDataFile:
    def __init__(self, doc_id):
        self.id = doc_id


class FakeDoc:
    """Stand-in for adsk.core.Document with a dataFile and a name."""

    def __init__(self, doc_id, name):
        self.dataFile = FakeDataFile(doc_id) if doc_id else None
        self.name = name


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


def _never_top(_doc):
    return False


def test_open_document_index_maps_ids_to_names_and_skips_unsaved():
    """The snapshot maps dataFile ids to names; unsaved docs are omitted."""
    docs = FakeDocuments(
        [FakeDoc("id-a", "Top ASSY"), FakeDoc("id-b", "Child"), FakeDoc(None, "Unsaved")]
    )

    index = entry._open_document_index(docs)

    assert index == {"id-a": "Top ASSY", "id-b": "Child"}


def test_strays_are_documents_opened_after_the_snapshot():
    """Only documents absent from the initial snapshot are strays."""
    initial = {"id-a": "Top ASSY", "id-b": "Child"}
    cfg = FakeDoc("id-cfg", "CFG - Shock Mount Stud - Default")
    docs = FakeDocuments([FakeDoc("id-a", "Top ASSY"), FakeDoc("id-b", "Child"), cfg])

    strays = entry._collect_stray_documents(docs, initial, _never_top)

    assert strays == [cfg]


def test_top_document_is_never_a_stray():
    """The top assembly is excluded even if its id is not in the snapshot."""
    top = FakeDoc("id-top", "Top ASSY")
    docs = FakeDocuments([top, FakeDoc("id-new", "CFG - Thing")])

    strays = entry._collect_stray_documents(docs, {}, lambda doc: doc is top)

    assert [d.name for d in strays] == ["CFG - Thing"]


def test_unidentifiable_documents_are_left_alone():
    """A document without a dataFile id cannot be matched, so it is not closed."""
    docs = FakeDocuments([FakeDoc(None, "Unsaved sketchpad")])

    strays = entry._collect_stray_documents(docs, {}, _never_top)

    assert strays == []


def test_broken_collection_degrades_to_no_strays():
    """A failing documents collection yields empty results, never raises."""
    assert entry._open_document_index(BrokenDocuments()) == {}
    assert entry._collect_stray_documents(BrokenDocuments(), {}, _never_top) == []
