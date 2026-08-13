"""Unit tests for ``enable_timeline_in_document`` in ``bottomupupdate/entry.py``.

The helper backs the Main-tab "Enable Timeline" option: a direct-modeling
document is switched to parametric so Fusion captures a timeline, while a
document that already has one is left untouched (the switch is one-way). Pure
design-type bookkeeping, tested with fakes; ``entry`` is imported via the
``PowerTools.*`` scaffolding in ``conftest.py`` and the ``adsk`` entry points it
reads are monkeypatched per test.
"""

import importlib

import pytest

entry = importlib.import_module("PowerTools.commands.bottomupupdate.entry")

DIRECT = "DirectDesignType"
PARAMETRIC = "ParametricDesignType"


class FakeApp:
    """Stand-in for adsk.core.Application exposing the active product."""

    activeProduct = object()


class FakeDesign:
    """Stand-in for adsk.fusion.Design with a settable designType."""

    def __init__(self, design_type):
        self.designType = design_type


class BrokenDesign:
    """Design whose designType access raises, to exercise the guard path."""

    @property
    def designType(self):
        raise RuntimeError("marshalling failure")


@pytest.fixture(autouse=True)
def _install_adsk_fakes(monkeypatch):
    """Point entry's adsk design-type enum at stable sentinel values."""
    monkeypatch.setattr(entry.adsk.fusion.DesignTypes, "DirectDesignType", DIRECT)
    monkeypatch.setattr(
        entry.adsk.fusion.DesignTypes, "ParametricDesignType", PARAMETRIC
    )


def _install_design(monkeypatch, design):
    """Make the helper's Design.cast(app.activeProduct) resolve to the given design."""
    monkeypatch.setattr(entry.adsk.core.Application, "get", FakeApp)
    monkeypatch.setattr(entry.adsk.fusion.Design, "cast", lambda _product: design)


def test_direct_modeling_document_is_switched_to_parametric(monkeypatch):
    """A history-off document gets the timeline enabled."""
    # Arrange
    design = FakeDesign(DIRECT)
    _install_design(monkeypatch, design)

    # Act
    result = entry.enable_timeline_in_document(object())

    # Assert
    assert design.designType == PARAMETRIC
    assert "Timeline enabled" in result


def test_parametric_document_is_left_untouched(monkeypatch):
    """A document that already has a timeline is not re-assigned."""
    # Arrange
    design = FakeDesign(PARAMETRIC)
    _install_design(monkeypatch, design)

    # Act
    result = entry.enable_timeline_in_document(object())

    # Assert
    assert design.designType == PARAMETRIC
    assert result.strip() == "Timeline already enabled"


def test_missing_design_is_reported_without_raising(monkeypatch):
    """No active design degrades to a log line so the run continues."""
    # Arrange
    _install_design(monkeypatch, None)

    # Act
    result = entry.enable_timeline_in_document(object())

    # Assert
    assert result == "No active design found"


def test_api_failure_is_guarded(monkeypatch):
    """A design-type read/write failure is reported, never raised."""
    # Arrange
    _install_design(monkeypatch, BrokenDesign())

    # Act
    result = entry.enable_timeline_in_document(object())

    # Assert
    assert "Error using Fusion API to enable the timeline" in result
