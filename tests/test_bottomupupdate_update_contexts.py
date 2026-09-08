"""Unit tests for ``update_contexts_in_document`` in ``bottomupupdate/entry.py``.

The helper backs the Main-tab "Update Contexts" option. Fusion exposes no API
for assembly contexts, so the helper starts ``EIPContextsUpdateCmd`` as a text
command -- ``CommandDefinition.execute()`` on it is a silent no-op from inside a
running command. These tests pin the contract the batch loop depends on: the
text command is the route used, whatever Fusion answers is carried into the log,
a failure is reported rather than raised (a raise would abort a run part-way
through an assembly), and the helper never reaches for ``ui.activeCommand`` or
``ui.terminateActiveCommand`` -- polling the active command from inside
``command_execute`` sees Bottom-Up Update itself, and terminating it segfaulted
Fusion on 2026-09-08. ``entry`` is imported via the ``PowerTools.*`` scaffolding
in ``conftest.py``.
"""

import importlib

import pytest

entry = importlib.import_module("PowerTools.commands.bottomupupdate.entry")


class FakeApp:
    """Stand-in for adsk.core.Application recording text commands."""

    def __init__(self, result="", error=None):
        self.result = result
        self.error = error
        self.commands = []

    def executeTextCommand(self, command):
        self.commands.append(command)
        if self.error:
            raise self.error
        return self.result


class ForbiddenUserInterface:
    """A ui whose command-stack members are traps.

    Reading activeCommand or terminating the active command from inside
    command_execute is what crashed Fusion; these tests fail loudly if the
    helper ever reaches for either again.
    """

    @property
    def activeCommand(self):
        raise AssertionError("update_contexts_in_document must not read activeCommand")

    def terminateActiveCommand(self):
        raise AssertionError(
            "update_contexts_in_document must not terminate the active command"
        )


@pytest.fixture(autouse=True)
def _no_event_pumping(monkeypatch):
    """Keep the helper's settle instant; nothing here should sleep."""
    monkeypatch.setattr(entry.ptutil, "pump_events_for", lambda *a, **k: None)
    monkeypatch.setattr(entry, "ui", ForbiddenUserInterface())


def _install_app(monkeypatch, fake_app):
    monkeypatch.setattr(entry, "app", fake_app)
    return fake_app


def test_the_command_is_started_as_a_text_command(monkeypatch):
    """CommandDefinition.execute() silently no-ops; Commands.Start is the route."""
    # Arrange
    fake_app = _install_app(monkeypatch, FakeApp())

    # Act
    result = entry.update_contexts_in_document("Bracket")

    # Assert
    assert fake_app.commands == [f"Commands.Start {entry.CONTEXT_UPDATE_CMD_ID}"]
    assert result.strip() == "Update contexts started for Bracket"


def test_fusions_reply_is_carried_into_the_log(monkeypatch):
    """Whatever the text command answers is recorded, not discarded."""
    # Arrange
    _install_app(monkeypatch, FakeApp(result="Ok\n"))

    # Act
    result = entry.update_contexts_in_document("Bracket")

    # Assert
    assert result.strip() == "Update contexts started for Bracket: Ok"


def test_the_settle_pump_runs_before_the_caller_saves(monkeypatch):
    """The cloud round-trips need pumping or the save races them."""
    # Arrange
    _install_app(monkeypatch, FakeApp())
    pumped = []
    monkeypatch.setattr(
        entry.ptutil, "pump_events_for", lambda seconds, *a, **k: pumped.append(seconds)
    )

    # Act
    entry.update_contexts_in_document("Bracket")

    # Assert
    assert pumped == [entry._CONTEXT_UPDATE_SETTLE_SECONDS]


def test_text_command_failure_is_guarded(monkeypatch):
    """A failing text command is reported, never propagated to the loop."""
    # Arrange
    _install_app(monkeypatch, FakeApp(error=RuntimeError("no such command")))

    # Act
    result = entry.update_contexts_in_document("Bracket")

    # Assert
    assert "Update contexts failed for Bracket" in result
    assert "no such command" in result


def test_a_failure_does_not_pump_or_touch_the_command_stack(monkeypatch):
    """The failure path returns immediately; no settle, no stack access."""
    # Arrange
    _install_app(monkeypatch, FakeApp(error=RuntimeError("boom")))
    pumped = []
    monkeypatch.setattr(
        entry.ptutil, "pump_events_for", lambda seconds, *a, **k: pumped.append(seconds)
    )

    # Act
    entry.update_contexts_in_document("Bracket")

    # Assert
    assert pumped == []
