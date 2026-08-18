"""Unit tests for ``_action_launch_fasteners`` in ``assemblypalette/entry.py``.

The handler backs the palette's "Fasteners ↗" link, which hands off to Fusion's
own ``FusionFastenersCommand``. Fusion often has that command present but
*disabled* (part-intent or direct-modeling designs, Form environment, library /
AnyCAD components, off-hub), and ``execute()`` on a disabled definition is a
silent no-op -- so the handler must report the state instead of hiding the
palette on a click that would do nothing. Pure routing logic, tested with fakes;
``entry`` is imported via the ``PowerTools.*`` scaffolding in ``conftest.py``.
"""

import importlib

import pytest

entry = importlib.import_module("PowerTools.commands.assemblypalette.entry")


class FakeControlDefinition:
    """Stand-in for the command definition's control definition."""

    def __init__(self, is_enabled=True):
        self.isEnabled = is_enabled


class FakeCommandDefinition:
    """Stand-in for adsk.core.CommandDefinition that records execute() calls."""

    def __init__(self, is_enabled=True):
        self.controlDefinition = FakeControlDefinition(is_enabled)
        self.execute_calls = 0

    def execute(self):
        self.execute_calls += 1
        return True


class LegacyCommandDefinition:
    """Definition whose controlDefinition access raises, to exercise the guard."""

    def __init__(self):
        self.execute_calls = 0

    @property
    def controlDefinition(self):
        raise RuntimeError("not exposed on this build")

    def execute(self):
        self.execute_calls += 1
        return True


class FakePalette:
    """Stand-in for adsk.core.Palette, tracking the visibility the handler sets."""

    def __init__(self):
        self.isVisible = True


def _install_ui(monkeypatch, cmd_def):
    """Point entry's module-level ``ui`` at a fake whose lookup returns cmd_def.

    Returns the list of ids the handler looked up, so the test can assert it
    asked for the Fusion command id rather than something else.
    """
    looked_up = []

    class FakeCommandDefinitions:
        def itemById(self, cmd_id):
            looked_up.append(cmd_id)
            return cmd_def

    class FakeUI:
        commandDefinitions = FakeCommandDefinitions()

    monkeypatch.setattr(entry, "ui", FakeUI())
    return looked_up


@pytest.fixture(autouse=True)
def _silence_log(monkeypatch):
    """Keep the handler's success log out of the test output."""
    monkeypatch.setattr(entry.ptutil, "log", lambda *a, **k: None)


def test_enabled_command_hides_palette_and_executes(monkeypatch):
    """The happy path starts Fusion's command and gets the palette out of the way."""
    # Arrange
    cmd_def = FakeCommandDefinition(is_enabled=True)
    looked_up = _install_ui(monkeypatch, cmd_def)
    palette = FakePalette()

    # Act
    msg = entry._action_launch_fasteners(palette)

    # Assert: no message to show, palette hidden, command started once.
    assert msg == ""
    assert palette.isVisible is False
    assert cmd_def.execute_calls == 1
    assert looked_up == ["FusionFastenersCommand"]


def test_disabled_command_reports_and_leaves_palette_open(monkeypatch):
    """A disabled command explains itself rather than dismissing the palette."""
    # Arrange
    cmd_def = FakeCommandDefinition(is_enabled=False)
    _install_ui(monkeypatch, cmd_def)
    palette = FakePalette()

    # Act
    msg = entry._action_launch_fasteners(palette)

    # Assert: execute() on a disabled definition is a silent no-op, so it is
    # never called; the palette stays up to carry the message.
    assert "disabled" in msg
    assert palette.isVisible is True
    assert cmd_def.execute_calls == 0


def test_missing_command_reports_unavailable(monkeypatch):
    """A Fusion build without the command reports that, and nothing is hidden."""
    # Arrange
    _install_ui(monkeypatch, None)
    palette = FakePalette()

    # Act
    msg = entry._action_launch_fasteners(palette)

    # Assert
    assert "not available in this version of Fusion" in msg
    assert palette.isVisible is True


def test_unreadable_control_definition_defaults_to_enabled(monkeypatch):
    """When the enabled state cannot be read, Fusion gets to make the call."""
    # Arrange
    cmd_def = LegacyCommandDefinition()
    _install_ui(monkeypatch, cmd_def)
    palette = FakePalette()

    # Act
    msg = entry._action_launch_fasteners(palette)

    # Assert
    assert msg == ""
    assert palette.isVisible is False
    assert cmd_def.execute_calls == 1


def test_missing_palette_is_tolerated(monkeypatch):
    """A None palette (already closed) must not stop the handoff."""
    # Arrange
    cmd_def = FakeCommandDefinition(is_enabled=True)
    _install_ui(monkeypatch, cmd_def)

    # Act
    msg = entry._action_launch_fasteners(None)

    # Assert
    assert msg == ""
    assert cmd_def.execute_calls == 1
