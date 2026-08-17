"""Unit tests for the palette's document-change auto-refresh in
``assemblyintent/entry.py``.

The galleries used to repaint only on ↻. They now follow every document open,
switch, save, and close, which makes three pieces of logic load-bearing and worth
pinning down here:

* the change fingerprint, because ``documentActivated`` fires on every tab switch
  and an unchanged repaint would put a few hundred KB of JSON on the bridge for
  nothing;
* the safety gate, because a repaint during the post-insert chain kills the Edit
  Initial Position command it opens -- the failure ``_schedule_finish_insert``
  exists to avoid;
* the thumbnail dedup, because the base64 thumbnails *are* the payload.

Pure logic with fakes -- no Fusion. ``entry`` is imported through the
``PowerTools.*`` scaffolding in ``conftest.py``, which also stubs ``adsk``.
"""

import importlib
import json
from types import SimpleNamespace

import pytest

entry = importlib.import_module("PowerTools.commands.assemblyintent.entry")


# --- Fakes -----------------------------------------------------------------


class FakeDataFile:
    def __init__(self, df_id, name):
        self.id = df_id
        self.name = name


class FakeDoc:
    """Stand-in for adsk.core.Document.

    ``documentReferences`` raises for a non-top-level document, which is exactly
    how ``_is_top_level_doc`` tells the two apart.
    """

    def __init__(self, name, df_id, is_saved=True, top_level=True):
        self.name = name
        self.dataFile = FakeDataFile(df_id, name) if df_id else None
        self.isSaved = is_saved
        self._top_level = top_level

    @property
    def documentReferences(self):
        if not self._top_level:
            raise RuntimeError("Cannot get documentReferences of a non-top-level doc")
        return SimpleNamespace(count=0)


class FakeDocuments:
    def __init__(self, docs):
        self._docs = docs

    @property
    def count(self):
        return len(self._docs)

    def item(self, i):
        return self._docs[i]


class FakePalette:
    """Records what was pushed to the page, in order."""

    def __init__(self, is_visible=True):
        self.isVisible = is_visible
        self.sent = []

    def sendInfoToHTML(self, action, data):  # noqa: N802 - Fusion API name
        self.sent.append((action, data))

    def payload(self, action):
        for sent_action, data in self.sent:
            if sent_action == action:
                return json.loads(data)
        raise AssertionError(f"{action} was never sent")


class FakePalettes:
    def __init__(self, palette):
        self._palette = palette

    def itemById(self, palette_id):  # noqa: N802 - Fusion API name
        return self._palette


def make_entries(*pairs):
    """Gallery cards as the list builders produce them."""
    return [
        {
            "dataFileId": df_id,
            "name": name,
            "intent": "part",
            "thumbUrl": thumb,
        }
        for df_id, name, thumb in pairs
    ]


@pytest.fixture(autouse=True)
def isolated_state(monkeypatch):
    """Reset the module state each test touches, and silence the debug log.

    ``_diag`` reaches ``Application.log`` through the real ``app`` object, which
    these tests replace with a fake.
    """
    monkeypatch.setattr(entry, "_last_gallery_signature", None)
    monkeypatch.setattr(entry, "_gallery_refresh_pending", False)
    monkeypatch.setattr(entry, "_thumbs_sent", set())
    monkeypatch.setattr(entry, "_pending_finish", None)
    monkeypatch.setattr(entry, "_inserted_in_session", set())
    monkeypatch.setattr(entry, "_diag", lambda msg: None)


@pytest.fixture
def palette(monkeypatch):
    """A visible palette, reachable the way _refresh_galleries reaches it."""
    p = FakePalette()
    monkeypatch.setattr(
        entry, "ui", SimpleNamespace(palettes=FakePalettes(p), activeCommand="")
    )
    return p


# --- The change fingerprint ------------------------------------------------


def test_signature_is_stable_for_identical_galleries() -> None:
    """The common case: a tab switch that changes nothing visible."""
    open_docs = make_entries(("a", "A", "data:x"))
    recent = make_entries(("b", "B", ""))
    first = entry._gallery_signature("Doc", open_docs, recent)
    second = entry._gallery_signature("Doc", list(open_docs), list(recent))
    assert first == second


@pytest.mark.parametrize(
    "doc_name, open_docs, recent",
    [
        # A renamed document, a re-intented one, a new card, one card gone,
        # a reordering, a thumbnail that has since been rendered, and a
        # different active document all have to break the match.
        ("Doc", make_entries(("a", "A2", "data:x")), make_entries(("b", "B", ""))),
        ("Doc", make_entries(("a", "A", "data:x"), ("c", "C", "")), []),
        ("Doc", [], make_entries(("b", "B", ""))),
        ("Doc", make_entries(("a", "A", "data:x")), make_entries(("b", "B", "data:y"))),
        ("Other", make_entries(("a", "A", "data:x")), make_entries(("b", "B", ""))),
    ],
)
def test_signature_changes_when_anything_visible_changes(
    doc_name, open_docs, recent
) -> None:
    baseline = entry._gallery_signature(
        "Doc", make_entries(("a", "A", "data:x")), make_entries(("b", "B", ""))
    )
    assert entry._gallery_signature(doc_name, open_docs, recent) != baseline


def test_signature_ignores_thumbnail_bytes() -> None:
    """Only present/absent matters — the URI is derived from a cache file keyed
    by the same id, so its content cannot change on its own."""
    a = entry._gallery_signature("Doc", make_entries(("a", "A", "data:one")), [])
    b = entry._gallery_signature("Doc", make_entries(("a", "A", "data:two")), [])
    assert a == b


def test_signature_notices_reordering() -> None:
    """Recent is ordered by last opened, so order is part of what the user sees."""
    forward = entry._gallery_signature(
        "Doc", [], make_entries(("a", "A", ""), ("b", "B", ""))
    )
    reversed_ = entry._gallery_signature(
        "Doc", [], make_entries(("b", "B", ""), ("a", "A", ""))
    )
    assert forward != reversed_


# --- The safety gate -------------------------------------------------------


def test_refresh_blocked_while_a_finish_is_pending(monkeypatch) -> None:
    """The post-insert chain is queued: a repaint here kills the command it
    is about to open."""
    monkeypatch.setattr(entry, "ui", SimpleNamespace(activeCommand=""))
    monkeypatch.setattr(entry, "_pending_finish", object())
    assert entry._refresh_is_safe() is False


@pytest.mark.parametrize("idle", ["", "SelectCommand"])
def test_refresh_allowed_when_fusion_is_idle(monkeypatch, idle) -> None:
    """Fusion reports idle as the Select command, not as nothing running."""
    monkeypatch.setattr(entry, "ui", SimpleNamespace(activeCommand=idle))
    assert entry._refresh_is_safe() is True


def test_refresh_blocked_while_a_command_is_running(monkeypatch) -> None:
    monkeypatch.setattr(
        entry, "ui", SimpleNamespace(activeCommand="FusionDcEditInitialPositionCommand")
    )
    assert entry._refresh_is_safe() is False


def test_refresh_allowed_when_active_command_is_unreadable(monkeypatch) -> None:
    """activeCommand is not on every build — an unreadable one must not
    permanently block the refresh."""

    class NoActiveCommand:
        @property
        def activeCommand(self):
            raise RuntimeError("not supported on this build")

    monkeypatch.setattr(entry, "ui", NoActiveCommand())
    assert entry._refresh_is_safe() is True


# --- Thumbnail dedup -------------------------------------------------------


def test_thumbnail_sent_once_then_omitted() -> None:
    entries = make_entries(("a", "A", "data:x"))
    first = entry._strip_sent_thumbs(entries)
    assert first[0]["thumbUrl"] == "data:x"

    second = entry._strip_sent_thumbs(entries)
    # Key absent, not empty: the page reads that as "reuse what you have".
    assert "thumbUrl" not in second[0]


def test_strip_leaves_the_input_untouched() -> None:
    """The caller fingerprints the full lists, so stripping must not mutate them."""
    entries = make_entries(("a", "A", "data:x"))
    entry._strip_sent_thumbs(entries)
    entry._strip_sent_thumbs(entries)
    assert entries[0]["thumbUrl"] == "data:x"


def test_empty_thumbnail_stays_empty() -> None:
    """An empty string means the document has no cached PNG at all, which is
    what drives the intent placeholder — it must survive as an empty value."""
    stripped = entry._strip_sent_thumbs(make_entries(("a", "A", "")))
    assert stripped[0]["thumbUrl"] == ""


# --- Open-list exclusion ---------------------------------------------------


@pytest.fixture
def open_docs_env(monkeypatch):
    """Three saved top-level design docs plus the active one."""
    active = FakeDoc("Active", "active-id")
    docs = [active, FakeDoc("One", "id-1"), FakeDoc("Two", "id-2")]
    monkeypatch.setattr(
        entry,
        "app",
        SimpleNamespace(documents=FakeDocuments(docs), activeDocument=active),
    )
    monkeypatch.setattr(entry, "_design_intent", lambda doc: 1)
    monkeypatch.setattr(entry, "_intent_name", lambda intent: "part")
    monkeypatch.setattr(entry, "_cached_thumbnail", lambda df_id: "data:" + df_id)
    return docs


def test_open_docs_excludes_the_active_document(open_docs_env) -> None:
    ids = [d["dataFileId"] for d in entry._list_open_docs()]
    assert ids == ["id-1", "id-2"]


def test_open_docs_drops_an_excluded_id(open_docs_env) -> None:
    """documentClosing fires while the doc is still in app.documents, so its
    card goes only if the id is excluded explicitly."""
    ids = [d["dataFileId"] for d in entry._list_open_docs(exclude_ids={"id-1"})]
    assert ids == ["id-2"]


def test_open_docs_ignores_an_unknown_exclusion(open_docs_env) -> None:
    ids = [d["dataFileId"] for d in entry._list_open_docs(exclude_ids={"nope"})]
    assert ids == ["id-1", "id-2"]


# --- The refresh itself ----------------------------------------------------


@pytest.fixture
def refresh_env(monkeypatch, open_docs_env):
    """Galleries with one open doc and one recent doc, cheaply."""
    monkeypatch.setattr(
        entry, "_list_open_docs", lambda exclude_ids=None: make_entries(("a", "A", ""))
    )
    monkeypatch.setattr(
        entry, "_list_recent_docs", lambda: make_entries(("b", "B", ""))
    )


def test_refresh_pushes_galleries_and_name(palette, refresh_env) -> None:
    entry._refresh_galleries("test")
    actions = [action for action, _ in palette.sent]
    assert actions == ["setDocumentName", "setOpenDocs", "setRecentDocs"]
    assert palette.payload("setOpenDocs")[0]["dataFileId"] == "a"


def test_refresh_does_not_resolve_the_target_project(palette, refresh_env) -> None:
    """The project resolution is the one cloud-touching call in the full state;
    the page re-checks it on focus, so a document event must not."""
    assert "setTargetProject" not in [action for action, _ in palette.sent]
    entry._refresh_galleries("test")
    assert "setTargetProject" not in [action for action, _ in palette.sent]
    assert "setTheme" not in [action for action, _ in palette.sent]


def test_refresh_skips_an_unchanged_repaint(palette, refresh_env) -> None:
    entry._refresh_galleries("first")
    sent = len(palette.sent)
    entry._refresh_galleries("second")
    assert len(palette.sent) == sent


def test_force_pushes_even_when_unchanged(palette, refresh_env) -> None:
    """What the page's flush needs: deliver a repaint that was skipped, whose
    content the fingerprint says is already on screen."""
    entry._refresh_galleries("first")
    sent = len(palette.sent)
    entry._refresh_galleries("flush", force=True)
    assert len(palette.sent) > sent


def test_refresh_defers_while_a_command_runs(monkeypatch, refresh_env) -> None:
    """Nothing is pushed, and the refresh is held rather than dropped."""
    held = FakePalette()
    monkeypatch.setattr(
        entry,
        "ui",
        SimpleNamespace(palettes=FakePalettes(held), activeCommand="SomeCommand"),
    )
    entry._refresh_galleries("documentActivated")
    assert held.sent == []
    assert entry._gallery_refresh_pending is True


def test_refresh_is_a_no_op_without_a_palette(monkeypatch, refresh_env) -> None:
    """The document handlers outlive stop(), so a missing palette must be silent."""
    monkeypatch.setattr(
        entry, "ui", SimpleNamespace(palettes=FakePalettes(None), activeCommand="")
    )
    entry._refresh_galleries("documentActivated")  # must not raise
    assert entry._last_gallery_signature is None


def test_refresh_skips_a_hidden_palette(monkeypatch, refresh_env) -> None:
    """The hand-offs hide the palette rather than closing it (_hide_palette),
    so an invisible one is a live object with nothing on screen."""
    hidden = FakePalette(is_visible=False)
    monkeypatch.setattr(
        entry, "ui", SimpleNamespace(palettes=FakePalettes(hidden), activeCommand="")
    )
    entry._refresh_galleries("documentActivated")
    assert hidden.sent == []


def test_second_refresh_omits_thumbnails_already_sent(
    monkeypatch, palette, open_docs_env
) -> None:
    """The payload shrinks to metadata once the page holds the thumbnails."""
    monkeypatch.setattr(
        entry,
        "_list_open_docs",
        lambda exclude_ids=None: make_entries(("a", "A", "data:x")),
    )
    monkeypatch.setattr(entry, "_list_recent_docs", lambda: [])
    entry._refresh_galleries("first")
    assert palette.payload("setOpenDocs")[0]["thumbUrl"] == "data:x"

    palette.sent.clear()
    entry._refresh_galleries("second", force=True)
    assert "thumbUrl" not in palette.payload("setOpenDocs")[0]
