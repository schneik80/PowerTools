"""Unit tests for the autosave suspend/restore pair in ``bottomupupdate/entry.py``.

``_suspend_autosave`` / ``_restore_autosave`` temporarily disable Fusion's
automatic-versioning background thread and save-on-close automation while the
Bottom-Up Update loop runs its own save/close cycle (the concurrent-autosave
mitigation for the recurring native NsDataModel10.dll crash). The pair is pure
preference bookkeeping, so it is tested with a fake application object; the
``entry`` module is imported via the ``PowerTools.*`` scaffolding in
``conftest.py`` and ``adsk.core.Application.get`` is monkeypatched per test.
"""

import importlib

import pytest

entry = importlib.import_module("PowerTools.commands.bottomupupdate.entry")


class FakeGeneralPrefs:
    """Stand-in for adsk.core.GeneralPreferences with the two autosave switches."""

    def __init__(self, versioning=True, save_on_close=True):
        self.isAutomaticVersioningEnabled = versioning
        self.isAutomaticSaveOnCloseEnabled = save_on_close


class FakeApp:
    """Stand-in for adsk.core.Application exposing preferences.generalPreferences."""

    def __init__(self, prefs):
        class _Prefs:
            generalPreferences = prefs

        self.preferences = _Prefs()


class BrokenApp:
    """Application whose preferences access raises, to exercise the guard path."""

    @property
    def preferences(self):
        raise RuntimeError("preferences unavailable")


@pytest.fixture(autouse=True)
def _reset_suspension_state():
    """Ensure no suspension state leaks between tests."""
    entry._autosave_prior_state = None
    yield
    entry._autosave_prior_state = None


def _install_app(monkeypatch, app):
    """Point entry's adsk.core.Application.get at the given fake app."""
    monkeypatch.setattr(entry.adsk.core.Application, "get", lambda: app)


def test_suspend_disables_both_switches_and_restore_reinstates(monkeypatch):
    """Suspend turns both autosave switches off; restore puts them back."""
    # Arrange
    prefs = FakeGeneralPrefs(versioning=True, save_on_close=True)
    _install_app(monkeypatch, FakeApp(prefs))
    log_lines = []

    # Act
    entry._suspend_autosave(log_lines.append)

    # Assert: both off, prior values recorded and logged for crash recovery.
    assert prefs.isAutomaticVersioningEnabled is False
    assert prefs.isAutomaticSaveOnCloseEnabled is False
    assert entry._autosave_prior_state == {
        "isAutomaticVersioningEnabled": True,
        "isAutomaticSaveOnCloseEnabled": True,
    }
    assert any("suspended" in line for line in log_lines)

    # Act
    entry._restore_autosave(log_lines.append)

    # Assert
    assert prefs.isAutomaticVersioningEnabled is True
    assert prefs.isAutomaticSaveOnCloseEnabled is True
    assert entry._autosave_prior_state is None


def test_restore_reinstates_mixed_prior_values_exactly(monkeypatch):
    """A user who already had one switch off gets that exact state back."""
    # Arrange: versioning already disabled by the user, save-on-close enabled.
    prefs = FakeGeneralPrefs(versioning=False, save_on_close=True)
    _install_app(monkeypatch, FakeApp(prefs))

    # Act
    entry._suspend_autosave()
    entry._restore_autosave()

    # Assert
    assert prefs.isAutomaticVersioningEnabled is False
    assert prefs.isAutomaticSaveOnCloseEnabled is True


def test_second_suspend_does_not_overwrite_prior_state(monkeypatch):
    """Suspending twice must not capture the already-disabled values as prior."""
    # Arrange
    prefs = FakeGeneralPrefs(versioning=True, save_on_close=True)
    _install_app(monkeypatch, FakeApp(prefs))

    # Act: double suspend, then restore.
    entry._suspend_autosave()
    entry._suspend_autosave()
    entry._restore_autosave()

    # Assert: originals restored, not False/False.
    assert prefs.isAutomaticVersioningEnabled is True
    assert prefs.isAutomaticSaveOnCloseEnabled is True


def test_restore_is_idempotent(monkeypatch):
    """A second restore is a no-op and does not touch the preferences again."""
    # Arrange
    prefs = FakeGeneralPrefs(versioning=True, save_on_close=True)
    _install_app(monkeypatch, FakeApp(prefs))
    entry._suspend_autosave()
    entry._restore_autosave()

    # Act: user flips a switch after restore; a stray second restore runs.
    prefs.isAutomaticVersioningEnabled = False
    entry._restore_autosave()

    # Assert: the user's change is untouched.
    assert prefs.isAutomaticVersioningEnabled is False


def test_suspend_failure_is_a_logged_no_op(monkeypatch):
    """If preferences are unreachable the run continues with autosave active."""
    # Arrange
    _install_app(monkeypatch, BrokenApp())
    log_lines = []

    # Act: neither call may raise.
    entry._suspend_autosave(log_lines.append)
    entry._restore_autosave(log_lines.append)

    # Assert
    assert entry._autosave_prior_state is None
    assert any("Could not suspend autosave" in line for line in log_lines)
