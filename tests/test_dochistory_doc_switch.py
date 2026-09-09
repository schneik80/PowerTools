"""The Document History palette's response to the active document changing.

The palette reads one document, when it opens. Nothing used to tell it when that
stopped being the active one, so it went on showing the old history under the old
document's name - a correct-looking history of the wrong design, which is the
failure this whole module is written to avoid rather than a visible error.

Two pieces are pinned here: ``_document_identity``, which decides whether the
active document is the one on screen, and ``_close_palette_if_stale``, which
decides what to do about it. Both are driven with stand-ins; ``entry`` is imported
through the ``PowerTools.*`` scaffolding in ``conftest.py``.
"""

import importlib

import pytest

entry = importlib.import_module("PowerTools.commands.dochistory.entry")

URN = "urn:adsk.wipprod:dm.lineage:lwFgZcFuRqOnxqrOC5KLKQ"
OTHER_URN = "urn:adsk.wipprod:dm.lineage:Mg3FFVnzTBmk9s4HKyLNaw"


class FakeDataFile:
    def __init__(self, file_id):
        self.id = file_id


class FakeDoc:
    """A document, saved when given a file id and unsaved when not."""

    def __init__(self, name="top", file_id=None):
        self.name = name
        self.dataFile = FakeDataFile(file_id) if file_id else None


class BrokenDoc:
    """A document whose dataFile access raises, as an offline one can."""

    name = "top"

    @property
    def dataFile(self):
        raise RuntimeError("cloud data unavailable")


# ---------------------------------------------------------------------------
# _document_identity
# ---------------------------------------------------------------------------


def test_a_saved_document_is_identified_by_its_lineage_urn():
    """Not by the Document object: two API calls hand back different wrappers."""
    assert entry._document_identity(FakeDoc(file_id=URN)) == URN


def test_an_unsaved_document_falls_back_to_its_name():
    """It has no dataFile at all, and still has to be told from the next one."""
    # Arrange / Act
    one = entry._document_identity(FakeDoc(name="Untitled"))
    two = entry._document_identity(FakeDoc(name="Untitled 2"))

    # Assert
    assert one == "unsaved:Untitled"
    assert one != two


def test_no_document_identifies_as_nothing():
    assert entry._document_identity(None) == ""


def test_an_unreadable_data_file_falls_back_rather_than_raising():
    """This runs off a document event; raising here would surface as a crash."""
    assert entry._document_identity(BrokenDoc()) == "unsaved:top"


def test_an_empty_file_id_is_not_taken_as_an_identity():
    """An id of "" would match every other document that could not answer."""
    doc = FakeDoc(name="top")
    doc.dataFile = FakeDataFile("")
    assert entry._document_identity(doc) == "unsaved:top"


# ---------------------------------------------------------------------------
# _close_palette_if_stale
# ---------------------------------------------------------------------------


class FakePalettes:
    def __init__(self, present=True):
        self.present = present

    def itemById(self, palette_id):
        return object() if self.present else None


class FakeUi:
    def __init__(self, present=True):
        self.palettes = FakePalettes(present)


class FakeApp:
    def __init__(self, doc):
        self.activeDocument = doc


@pytest.fixture
def closed(monkeypatch):
    """Record teardowns instead of performing them."""
    calls = []
    monkeypatch.setattr(entry, "_close_palette", lambda reason: calls.append(reason))
    return calls


def _arrange(monkeypatch, shown_id, active_doc, palette_present=True):
    monkeypatch.setattr(entry, "_last_state", {"docId": shown_id} if shown_id else {})
    monkeypatch.setattr(entry, "ui", FakeUi(palette_present))
    monkeypatch.setattr(entry, "app", FakeApp(active_doc))


def test_switching_to_another_document_tears_the_palette_down(monkeypatch, closed):
    """The case from the report: the header would name one, the rows another."""
    # Arrange
    _arrange(monkeypatch, URN, FakeDoc(file_id=OTHER_URN))

    # Act
    entry._close_palette_if_stale()

    # Assert
    assert closed == ["active document changed"]


def test_reactivating_the_same_document_leaves_the_palette_alone(monkeypatch, closed):
    """Activation fires for reasons other than a switch; this must not churn."""
    # Arrange
    _arrange(monkeypatch, URN, FakeDoc(file_id=URN))

    # Act
    entry._close_palette_if_stale()

    # Assert
    assert closed == []


def test_a_new_unsaved_document_tears_the_palette_down(monkeypatch, closed):
    """It has no history at all, so the previous document's must not linger."""
    # Arrange
    _arrange(monkeypatch, URN, FakeDoc(name="Untitled"))

    # Act
    entry._close_palette_if_stale()

    # Assert
    assert closed == ["active document changed"]


def test_closing_the_last_document_tears_the_palette_down(monkeypatch, closed):
    """No active document cannot be the document on screen."""
    # Arrange
    _arrange(monkeypatch, URN, None)

    # Act
    entry._close_palette_if_stale()

    # Assert
    assert closed == ["active document changed"]


def test_nothing_happens_when_no_palette_of_ours_is_open(monkeypatch, closed):
    """The events fire for the whole session, not only while the palette is up."""
    # Arrange
    _arrange(monkeypatch, "", FakeDoc(file_id=OTHER_URN))

    # Act
    entry._close_palette_if_stale()

    # Assert
    assert closed == []


def test_nothing_happens_when_the_palette_has_already_gone(monkeypatch, closed):
    """State can outlive the palette if Fusion tore it down for its own reasons."""
    # Arrange
    _arrange(monkeypatch, URN, FakeDoc(file_id=OTHER_URN), palette_present=False)

    # Act
    entry._close_palette_if_stale()

    # Assert
    assert closed == []


def test_an_offline_document_tears_the_palette_down_rather_than_raising(
    monkeypatch, closed
):
    """A document whose cloud data will not read is not the one on screen."""
    # Arrange
    _arrange(monkeypatch, URN, BrokenDoc())

    # Act
    entry._close_palette_if_stale()

    # Assert
    assert closed == ["active document changed"]
