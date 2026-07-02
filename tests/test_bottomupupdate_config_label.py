"""Unit tests for ``_configuration_label`` in ``bottomupupdate/entry.py``.

The helper classifies a DataFile's configuration role so the processing loop
can skip configuration members and configured designs before opening them
(Fusion crashes natively in its configuration/PIM data-model when this command
opens them in bulk -- CER 2026-07-02). Pure attribute logic, tested with fakes;
``entry`` is imported via the ``PowerTools.*`` scaffolding in ``conftest.py``.
"""

import importlib

entry = importlib.import_module("PowerTools.commands.bottomupupdate.entry")


class FakeDataFile:
    """Stand-in for adsk.core.DataFile with the two configuration flags."""

    def __init__(self, is_configuration=False, is_configured_design=False):
        self.isConfiguration = is_configuration
        self.isConfiguredDesign = is_configured_design


class BrokenDataFile:
    """DataFile whose flag access raises, to exercise the guard path."""

    @property
    def isConfiguration(self):
        raise RuntimeError("marshalling failure")


def test_configuration_member_is_labelled():
    """A configuration-table member is identified for skipping."""
    data_file = FakeDataFile(is_configuration=True)

    assert entry._configuration_label(data_file) == "configuration member"


def test_configured_design_is_labelled():
    """A configured (top-table) design is identified for skipping."""
    data_file = FakeDataFile(is_configured_design=True)

    assert entry._configuration_label(data_file) == "configured design"


def test_plain_document_returns_empty_string():
    """An ordinary document is not labelled and is processed normally."""
    data_file = FakeDataFile()

    assert entry._configuration_label(data_file) == ""


def test_missing_properties_return_empty_string():
    """Older clients without the flags fall back to processing normally."""

    class LegacyDataFile:
        pass

    assert entry._configuration_label(LegacyDataFile()) == ""


def test_raising_property_is_guarded():
    """A marshalling failure degrades to 'not a configuration', never raises."""
    assert entry._configuration_label(BrokenDataFile()) == ""
