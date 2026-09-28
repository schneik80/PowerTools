"""Unit tests for the saved-document gate on the palette's Assembly Builder handoff.

The palette offers **Assembly Builder…** only while the active document has
never been saved. The page disables the button from ``activeDocSaved``, but no
save event reaches the palette, so ``_palette_incoming`` re-checks at click
time: a saved document gets a message and a fresh ``setActiveDocSaved`` push
instead of the handoff. Pure routing logic, tested with fakes; ``entry`` is
imported via the ``PowerTools.*`` scaffolding in ``conftest.py``.
"""

import importlib
import json

import pytest

entry = importlib.import_module("PowerTools.commands.assemblypalette.entry")


class FakeDocument:
    def __init__(self, is_saved):
        self.isSaved = is_saved


class FakeApp:
    def __init__(self, doc):
        self.activeDocument = doc


class FakePalette:
    """Stand-in for adsk.core.Palette recording visibility and pushes."""

    def __init__(self):
        self.isVisible = True
        self.sent = []

    def sendInfoToHTML(self, action, data):
        self.sent.append((action, data))


class FakeHTMLEventArgs:
    def __init__(self, action, data="{}"):
        self.action = action
        self.data = data
        self.returnData = ""


@pytest.fixture
def harness(monkeypatch):
    """Fake ui/app for entry; returns a setter for the active document."""
    palette = FakePalette()
    boxes = []
    executed = []

    class FakePalettes:
        def itemById(self, pid):
            return palette

    class FakeUI:
        palettes = FakePalettes()

        def messageBox(self, msg, title=""):
            boxes.append(msg)

    monkeypatch.setattr(entry, "ui", FakeUI())
    monkeypatch.setattr(entry, "_execute_command", executed.append)
    monkeypatch.setattr(entry.ptutil, "log", lambda *a, **k: None)

    def set_doc(doc):
        monkeypatch.setattr(entry, "app", FakeApp(doc))

    return palette, boxes, executed, set_doc


def test_unsaved_document_hands_off_to_builder(harness):
    palette, boxes, executed, set_doc = harness
    set_doc(FakeDocument(is_saved=False))

    entry._palette_incoming(FakeHTMLEventArgs("launchAssemblyBuilder"))

    assert executed == [entry._ASSEMBLY_BUILDER_CMD_ID]
    assert palette.isVisible is False
    assert boxes == []


def test_saved_document_is_refused_and_page_updated(harness):
    palette, boxes, executed, set_doc = harness
    set_doc(FakeDocument(is_saved=True))

    args = FakeHTMLEventArgs("launchAssemblyBuilder")
    entry._palette_incoming(args)

    # No handoff, the palette stays up, the user is told why, and the page is
    # told the document is saved so the button greys out.
    assert executed == []
    assert palette.isVisible is True
    assert boxes == [entry._BUILDER_SAVED_MSG]
    assert palette.sent == [("setActiveDocSaved", json.dumps(True))]
    assert args.returnData == "OK"


@pytest.mark.parametrize("is_saved", [True, False])
def test_recheck_pushes_current_saved_state(harness, is_saved):
    palette, boxes, executed, set_doc = harness
    set_doc(FakeDocument(is_saved=is_saved))

    entry._palette_incoming(FakeHTMLEventArgs("recheckDocSaved"))

    assert palette.sent == [("setActiveDocSaved", json.dumps(is_saved))]
    assert executed == []


def test_no_active_document_reads_as_unsaved(harness):
    """With no document open the gate must not raise; nothing is saved."""
    _, _, _, set_doc = harness
    set_doc(None)

    assert entry._active_doc_is_saved() is False
