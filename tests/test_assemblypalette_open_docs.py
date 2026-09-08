"""Unit tests for the Assembly Palette Open gallery (``_list_open_docs``).

The Open tab lists the documents you can insert into the active design, so the
one document it must never list is the active document itself — a document
cannot contain itself, and clicking such a card either fails outright or (worse)
reports the misleading "must be in the same project" message that
``_action_insert_doc`` produces when ``addByInsert`` returns ``None``.

The filter was written from the start but compared ``id(doc)`` against
``id(app.activeDocument)``. Fusion hands back a **fresh Python wrapper** around
the same native ``Document`` on every API call, so those ids never match and the
active document was listed anyway. ``_list_recent_docs`` had it right all along:
compare ``dataFile.id``. The first two tests pin both shapes.

Because the galleries repaint only on ↻ (automatic refresh is parked — see
``docs/arch/Assembly Palette.md``), a Fusion tab switch can still leave a stale
card on screen, so ``_action_insert_doc`` re-checks the same rule at click time.
That guard is covered here too.

Fusion is not available, so the module's own seams are monkeypatched rather than
the ``adsk`` MagicMocks: ``entry.app`` for the document enumerator and
``entry._design_intent`` / ``entry._intent_name``, which are one-line delegates
to ``recents_utils``.

``entry`` is imported via the ``PowerTools.*`` scaffolding in ``conftest.py``.
"""

import importlib

import pytest

entry = importlib.import_module("PowerTools.commands.assemblypalette.entry")


class FakeDataFile:
    def __init__(self, df_id, name=None):
        self.id = df_id
        self.name = name if name is not None else f"{df_id}-name"


class FakeDoc:
    """Stand-in for adsk.core.Document, as ``_list_open_docs`` reads it.

    ``top_level=False`` makes ``documentReferences.count`` raise, which is
    exactly how Fusion signals a reference-loaded child — so ``_is_top_level_doc``
    runs for real against these fakes rather than being stubbed out.
    """

    def __init__(
        self,
        name,
        df_id=None,
        *,
        is_saved=True,
        intent="assembly",
        top_level=True,
        data_file_raises=False,
    ):
        self.name = name
        self.isSaved = is_saved
        self.intent = intent
        self._top_level = top_level
        self._data_file_raises = data_file_raises
        self._data_file = None if df_id is None else FakeDataFile(df_id)

    @property
    def documentReferences(self):
        if not self._top_level:
            raise RuntimeError(
                "Cannot get documentReferences of a non-top-level document"
            )
        return type("Refs", (), {"count": 0})()

    @property
    def dataFile(self):
        if self._data_file_raises:
            raise RuntimeError("no DataFile")
        return self._data_file


class FakeDocuments:
    def __init__(self, docs):
        self._docs = list(docs)

    @property
    def count(self):
        return len(self._docs)

    def item(self, i):
        return self._docs[i]


class FakeApp:
    def __init__(self, docs, active=None):
        self.documents = FakeDocuments(docs)
        self.activeDocument = active


@pytest.fixture
def open_docs(monkeypatch):
    """Wire the module's seams to plain Python fakes.

    ``_design_intent`` / ``_intent_name`` delegate to ``recents_utils``, which
    needs a live document; here the intent simply rides on the fake, and the
    name mapping is the identity.
    """
    monkeypatch.setattr(entry, "_design_intent", lambda doc: doc.intent)
    monkeypatch.setattr(entry, "_intent_name", lambda intent: intent or "")
    monkeypatch.setattr(entry, "_inserted_in_session", set())
    monkeypatch.setattr(entry, "_show_children", False)

    def build(docs, active=None):
        monkeypatch.setattr(entry, "app", FakeApp(docs, active))
        return entry._list_open_docs()

    return build


def _ids(cards):
    return [card["dataFileId"] for card in cards]


# ---------------------------------------------------------------------------
# The active document
# ---------------------------------------------------------------------------


def test_active_doc_excluded_when_wrapper_is_a_distinct_object(open_docs):
    """The regression pin: two wrappers, one document.

    ``app.activeDocument`` and ``Documents.item()`` return separate Python
    objects for the same native document, which is precisely why the old
    ``id(doc) == id(active)`` test never fired. Only the ``DataFile`` id ties
    them together.
    """
    listed = FakeDoc("Chassis", "df-active")
    active_wrapper = FakeDoc("Chassis", "df-active")
    assert listed is not active_wrapper
    assert id(listed) != id(active_wrapper)

    cards = open_docs([listed, FakeDoc("Bracket", "df-other")], active=active_wrapper)

    assert _ids(cards) == ["df-other"]


def test_active_doc_excluded_when_wrapper_is_the_same_object(open_docs):
    active = FakeDoc("Chassis", "df-active")
    cards = open_docs([active, FakeDoc("Bracket", "df-other")], active=active)
    assert _ids(cards) == ["df-other"]


def test_unsaved_active_doc_leaves_the_rest_listed(open_docs):
    """A brand-new document has no DataFile, so there is nothing to exclude by.

    Reading ``.dataFile`` on it raises; ``_active_data_file_id`` swallows that
    and the other open documents still list.
    """
    unsaved_active = FakeDoc("Untitled", None, is_saved=False, data_file_raises=True)
    cards = open_docs(
        [unsaved_active, FakeDoc("Bracket", "df-other")], active=unsaved_active
    )
    assert _ids(cards) == ["df-other"]


# ---------------------------------------------------------------------------
# The pre-existing filters
# ---------------------------------------------------------------------------


def test_unsaved_docs_are_not_listed(open_docs):
    cards = open_docs(
        [
            FakeDoc("Saved", "df-saved"),
            FakeDoc("Untitled", None, is_saved=False, data_file_raises=True),
        ],
        active=FakeDoc("Chassis", "df-active"),
    )
    assert _ids(cards) == ["df-saved"]


def test_non_design_docs_are_not_listed(open_docs):
    """Drawings and electronics files have no meaning as an inserted component."""
    cards = open_docs(
        [
            FakeDoc("Sheet", "df-drawing", intent=None),
            FakeDoc("Bracket", "df-other"),
        ],
        active=FakeDoc("Chassis", "df-active"),
    )
    assert _ids(cards) == ["df-other"]


@pytest.mark.parametrize("intent", ["part", "hybrid", "assembly"])
def test_every_design_intent_is_listed(open_docs, intent):
    cards = open_docs(
        [FakeDoc("Thing", "df-thing", intent=intent)],
        active=FakeDoc("Chassis", "df-active"),
    )
    assert _ids(cards) == ["df-thing"]
    assert cards[0]["intent"] == intent


def test_doc_whose_data_file_raises_is_skipped(open_docs):
    cards = open_docs(
        [
            FakeDoc("Odd", "df-odd", data_file_raises=True),
            FakeDoc("Bracket", "df-other"),
        ],
        active=FakeDoc("Chassis", "df-active"),
    )
    assert _ids(cards) == ["df-other"]


def test_docs_inserted_this_session_are_hidden(open_docs, monkeypatch):
    monkeypatch.setattr(entry, "_inserted_in_session", {"df-done"})
    cards = open_docs(
        [FakeDoc("Done", "df-done"), FakeDoc("Bracket", "df-other")],
        active=FakeDoc("Chassis", "df-active"),
    )
    assert _ids(cards) == ["df-other"]


def test_duplicate_data_file_ids_yield_one_card(open_docs):
    cards = open_docs(
        [FakeDoc("Bracket", "df-other"), FakeDoc("Bracket", "df-other")],
        active=FakeDoc("Chassis", "df-active"),
    )
    assert _ids(cards) == ["df-other"]


def test_card_name_comes_from_the_data_file(open_docs):
    cards = open_docs(
        [FakeDoc("wrapper name", "df-other")],
        active=FakeDoc("Chassis", "df-active"),
    )
    assert cards[0]["name"] == "df-other-name"


# ---------------------------------------------------------------------------
# Show referenced children
# ---------------------------------------------------------------------------


def test_reference_loaded_children_hidden_by_default(open_docs):
    cards = open_docs(
        [
            FakeDoc("Top", "df-top"),
            FakeDoc("Child", "df-child", top_level=False),
        ],
        active=FakeDoc("Chassis", "df-active"),
    )
    assert _ids(cards) == ["df-top"]


def test_reference_loaded_children_listed_when_show_children(open_docs, monkeypatch):
    monkeypatch.setattr(entry, "_show_children", True)
    cards = open_docs(
        [
            FakeDoc("Top", "df-top"),
            FakeDoc("Child", "df-child", top_level=False),
        ],
        active=FakeDoc("Chassis", "df-active"),
    )
    assert _ids(cards) == ["df-top", "df-child"]


def test_active_doc_stays_excluded_with_show_children(open_docs, monkeypatch):
    """The Show-referenced-children toggle pushes setOpenDocs on its own path."""
    monkeypatch.setattr(entry, "_show_children", True)
    cards = open_docs(
        [
            FakeDoc("Chassis", "df-active"),
            FakeDoc("Child", "df-child", top_level=False),
        ],
        active=FakeDoc("Chassis", "df-active"),
    )
    assert _ids(cards) == ["df-child"]


# ---------------------------------------------------------------------------
# The insert-time guard
# ---------------------------------------------------------------------------


def test_insert_refuses_the_active_document(monkeypatch):
    """A card left stale by a tab switch must be refused, not inserted.

    ``addByInsert`` is never reached: ``_find_data_file_by_id`` is patched to
    raise so the test fails loudly if the guard lets the click through.
    """
    monkeypatch.setattr(entry, "_active_design_or_none", lambda: object())
    monkeypatch.setattr(entry, "_active_data_file_id", lambda: "df-active")

    def boom(_df_id):
        raise AssertionError("_action_insert_doc reached the insert path")

    monkeypatch.setattr(entry, "_find_data_file_by_id", boom)

    message = entry._action_insert_doc({"dataFileId": "df-active"})

    assert message
    assert "cannot" in message


def test_insert_of_another_document_passes_the_guard(monkeypatch):
    """The guard must not swallow a legitimate insert on its way through."""
    monkeypatch.setattr(entry, "_active_design_or_none", lambda: object())
    monkeypatch.setattr(entry, "_active_data_file_id", lambda: "df-active")
    monkeypatch.setattr(entry, "_find_data_file_by_id", lambda _df_id: None)

    message = entry._action_insert_doc({"dataFileId": "df-other"})

    assert message == "Could not resolve the selected document."
