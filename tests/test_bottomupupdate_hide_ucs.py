"""Unit tests for ``hide_user_coordinate_systems_in_document`` in ``bottomupupdate/entry.py``.

The helper backs the Visibility-tab "Hide user coordinate systems" option. User
coordinate systems have no folder light bulb property, so the helper switches
each UCS light bulb off individually, and the ``userCoordinateSystems``
collection is in preview state in the Fusion API, so builds without it must be
reported rather than raise. Tested with fakes; ``entry`` is imported via the
``PowerTools.*`` scaffolding in ``conftest.py`` and the ``adsk`` entry points it
reads are monkeypatched per test.
"""

import importlib

entry = importlib.import_module("PowerTools.commands.bottomupupdate.entry")


class FakeApp:
    """Stand-in for adsk.core.Application exposing the active product."""

    activeProduct = object()


class FakeUCS:
    """Stand-in for adsk.fusion.UserCoordinateSystem with a settable light bulb."""

    def __init__(self, is_on=True):
        self.isLightBulbOn = is_on


class BrokenUCS:
    """UCS whose light bulb access raises, to exercise the per-item guard."""

    @property
    def isLightBulbOn(self):
        raise RuntimeError("marshalling failure")


class FakeUCSCollection:
    """Stand-in for adsk.fusion.UserCoordinateSystems with count / item()."""

    def __init__(self, items):
        self._items = items

    @property
    def count(self):
        return len(self._items)

    def item(self, index):
        return self._items[index]


class FakeComponent:
    """Component exposing the preview-state userCoordinateSystems collection."""

    def __init__(self, items):
        self.userCoordinateSystems = FakeUCSCollection(items)


class LegacyComponent:
    """Component from a Fusion build without user coordinate system support."""


class FakeDesign:
    """Stand-in for adsk.fusion.Design exposing activeComponent."""

    def __init__(self, component):
        self.activeComponent = component


def _install_design(monkeypatch, design):
    """Make the helper's Design.cast(app.activeProduct) resolve to the given design."""
    monkeypatch.setattr(entry.adsk.core.Application, "get", FakeApp)
    monkeypatch.setattr(entry.adsk.fusion.Design, "cast", lambda _product: design)


def test_visible_systems_are_hidden_and_counted(monkeypatch):
    """Every lit UCS is switched off and the count is reported."""
    # Arrange
    systems = [FakeUCS(True), FakeUCS(True), FakeUCS(True)]
    _install_design(monkeypatch, FakeDesign(FakeComponent(systems)))

    # Act
    result = entry.hide_user_coordinate_systems_in_document(object())

    # Assert
    assert all(ucs.isLightBulbOn is False for ucs in systems)
    assert "user coordinate systems hidden (3)" in result


def test_already_hidden_systems_are_not_recounted(monkeypatch):
    """Only the systems that were visible count toward the hidden total."""
    # Arrange
    systems = [FakeUCS(False), FakeUCS(True)]
    _install_design(monkeypatch, FakeDesign(FakeComponent(systems)))

    # Act
    result = entry.hide_user_coordinate_systems_in_document(object())

    # Assert
    assert "user coordinate systems hidden (1)" in result


def test_empty_collection_is_reported(monkeypatch):
    """A document with no user coordinate systems is a logged no-op."""
    # Arrange
    _install_design(monkeypatch, FakeDesign(FakeComponent([])))

    # Act
    result = entry.hide_user_coordinate_systems_in_document(object())

    # Assert
    assert result.strip() == "No user coordinate systems found in document"


def test_build_without_ucs_support_is_reported(monkeypatch):
    """An older Fusion build without the preview collection is reported, not an error."""
    # Arrange
    _install_design(monkeypatch, FakeDesign(LegacyComponent()))

    # Act
    result = entry.hide_user_coordinate_systems_in_document(object())

    # Assert
    assert "not supported by this Fusion build" in result


def test_failing_item_does_not_stop_the_others(monkeypatch):
    """A UCS that fails to hide is skipped; the remaining ones are still hidden."""
    # Arrange
    good = FakeUCS(True)
    _install_design(monkeypatch, FakeDesign(FakeComponent([BrokenUCS(), good])))

    # Act
    result = entry.hide_user_coordinate_systems_in_document(object())

    # Assert
    assert good.isLightBulbOn is False
    assert "user coordinate systems hidden (1)" in result


def test_missing_design_is_reported_without_raising(monkeypatch):
    """No active design degrades to a log line so the run continues."""
    # Arrange
    _install_design(monkeypatch, None)

    # Act
    result = entry.hide_user_coordinate_systems_in_document(object())

    # Assert
    assert result == "No active design found"


def test_api_failure_is_guarded(monkeypatch):
    """A collection-level failure is reported, never raised."""

    # Arrange
    class BrokenDesign:
        @property
        def activeComponent(self):
            raise RuntimeError("marshalling failure")

    _install_design(monkeypatch, BrokenDesign())

    # Act
    result = entry.hide_user_coordinate_systems_in_document(object())

    # Assert
    assert "Error using Fusion API to hide user coordinate systems" in result
