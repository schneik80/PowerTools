"""Unit tests for ``ptAddInUtils.document_required_message`` / ``require_document``.

``require_document`` is the single document precondition gate for commands: it
replaced seven hand-written "a design must be active" wordings and the
``isSaved()`` "Please Save" box, and it runs ``is_user_document`` first because
a native command launched with no document can segfault Fusion (#25). The
message builder is pure; the gate is exercised with plain stand-ins for the
``app`` / ``ui`` globals and the ``adsk`` casts (``conftest.py`` stubs ``adsk``).
"""

import importlib
import sys

import pytest

general_utils = importlib.import_module("PowerTools.lib.ptAddInUtils.general_utils")


# --- message --------------------------------------------------------------


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        (
            "document",
            "Recovery Save needs a document open. "
            "Open or create a document, then retry.",
        ),
        (
            "design",
            "Recovery Save needs a design open. Open or create a design, then retry.",
        ),
        (
            "drawing",
            "Recovery Save needs a drawing open. Open a drawing, then retry.",
        ),
    ],
)
def test_missing_message_per_kind(kind, expected):
    assert general_utils.document_required_message("Recovery Save", kind) == expected


@pytest.mark.parametrize("kind", general_utils.DOCUMENT_KINDS)
def test_unsaved_message_per_kind(kind):
    assert general_utils.document_required_message("Share", kind, saved=True) == (
        f"Share needs a saved {kind}. Save the {kind}, then retry."
    )


def test_unknown_kind_raises():
    with pytest.raises(ValueError):
        general_utils.document_required_message("X", "sketch")


# --- gate -----------------------------------------------------------------


class _Doc:
    def __init__(self, saved=True, user=True):
        self.isValid = user
        self.isVisible = user
        self.isActive = user
        self.isSaved = saved


class _Design:
    pass


class _Drawing:
    pass


class _App:
    def __init__(self, doc=None, product=None):
        self.activeDocument = doc
        self.activeProduct = product


class _Ui:
    def __init__(self):
        self.messages = []

    def messageBox(self, text, title):
        self.messages.append((text, title))


@pytest.fixture
def env(monkeypatch):
    """Install stand-ins; returns a setter for the active document/product."""
    ui = _Ui()
    monkeypatch.setattr(general_utils, "ui", ui)
    fusion = sys.modules["adsk.fusion"]
    drawing = importlib.import_module("adsk.drawing")
    monkeypatch.setattr(
        fusion.Design, "cast", lambda p: p if isinstance(p, _Design) else None
    )
    monkeypatch.setattr(
        drawing.Drawing, "cast", lambda p: p if isinstance(p, _Drawing) else None
    )

    def set_active(doc=None, product=None):
        monkeypatch.setattr(general_utils, "app", _App(doc, product))
        return ui

    return set_active


def test_no_document_shows_message_and_returns_none(env):
    ui = env()
    assert general_utils.require_document("Recovery Save") is None
    assert ui.messages == [
        (general_utils.document_required_message("Recovery Save"), "Recovery Save")
    ]


def test_document_kind_returns_the_document(env):
    doc = _Doc()
    ui = env(doc)
    assert general_utils.require_document("X") is doc
    assert ui.messages == []


def test_invisible_document_is_not_accepted(env):
    ui = env(_Doc(user=False), _Design())
    assert general_utils.require_document("X", "design") is None
    assert len(ui.messages) == 1


def test_design_kind_returns_the_design(env):
    design = _Design()
    ui = env(_Doc(), design)
    assert general_utils.require_document("X", "design") is design
    assert ui.messages == []


def test_design_kind_rejects_a_drawing(env):
    ui = env(_Doc(), _Drawing())
    assert general_utils.require_document("X", "design") is None
    assert ui.messages[0][0] == general_utils.document_required_message("X", "design")


def test_drawing_kind_returns_the_drawing(env):
    drawing = _Drawing()
    env(_Doc(), drawing)
    assert general_utils.require_document("X", "drawing") is drawing


def test_saved_rejects_an_unsaved_document_with_the_save_message(env):
    ui = env(_Doc(saved=False), _Design())
    assert general_utils.require_document("X", "design", saved=True) is None
    assert ui.messages == [
        (general_utils.document_required_message("X", "design", saved=True), "X")
    ]


def test_saved_accepts_a_saved_document(env):
    doc = _Doc()
    ui = env(doc)
    assert general_utils.require_document("X", saved=True) is doc
    assert ui.messages == []


def test_saved_with_no_document_gives_the_open_message(env):
    ui = env()
    assert general_utils.require_document("X", saved=True) is None
    assert ui.messages[0][0] == general_utils.document_required_message("X")


@pytest.mark.parametrize(
    "name", ["Export Mermaid Diagram...", "Export Mermaid Diagram…"]
)
def test_trailing_ellipsis_is_dropped(name):
    assert general_utils.document_required_message(name, "design").startswith(
        "Export Mermaid Diagram needs a design open."
    )
