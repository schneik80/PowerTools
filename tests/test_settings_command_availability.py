"""Unit tests for settings_store.is_enabled / is_command_available.

``is_enabled`` is the single rule deciding whether a registered command runs:
its group must be enabled, a beta command needs beta mode on, and the command
itself must be enabled. The start-up loop in ``commands/__init__.py`` applies it
per registry entry; ``is_command_available`` looks a single module up by key so
a command offering a hand-off (the Assembly Palette's "Assembly Builder..." and
"Global Parameters..." buttons) can hide a button for something the user has
switched off. The two must never disagree about what is running.

The module uses package-relative imports, so it is loaded via its full package
path with the conftest scaffolding in place.
"""

import importlib
from pathlib import Path

PT_PKG = Path(__file__).resolve().parent.parent.name
settings_store = importlib.import_module(f"{PT_PKG}.settings_store")
registry = importlib.import_module(f"{PT_PKG}.command_registry")

GROUP = {"key": "assembly", "label": "Assembly"}
PLAIN = {"module": "assemblybuilder", "beta": False}
BETA = {"module": "inferconstraints", "beta": True}


def _prefs(groups=None, commands=None, beta_mode=False) -> dict:
    """Build a minimal preferences dict.

    Args:
        groups: The "groups" section, defaulting to the assembly group on.
        commands: The "commands" section, defaulting to empty.
        beta_mode: Whether beta commands are permitted.

    Returns:
        A preferences dict shaped like settings_store.load()'s result.
    """
    return {
        "general": {"beta_mode": beta_mode},
        "groups": groups if groups is not None else {"assembly": {"enabled": True}},
        "commands": commands or {},
    }


# ---------------------------------------------------------------------------
# is_enabled
# ---------------------------------------------------------------------------


def test_enabled_by_default_when_prefs_say_nothing():
    # Arrange: a command nobody has ever touched.
    prefs = _prefs()

    # Act / Assert
    assert settings_store.is_enabled(GROUP, PLAIN, prefs) is True


def test_disabled_command_does_not_run():
    # Arrange
    prefs = _prefs(commands={"assemblybuilder": {"enabled": False}})

    # Act / Assert
    assert settings_store.is_enabled(GROUP, PLAIN, prefs) is False


def test_disabled_group_disables_its_commands():
    # Arrange: the command is on, but its whole group is off.
    prefs = _prefs(
        groups={"assembly": {"enabled": False}},
        commands={"assemblybuilder": {"enabled": True}},
    )

    # Act / Assert
    assert settings_store.is_enabled(GROUP, PLAIN, prefs) is False


def test_beta_command_needs_beta_mode():
    # Arrange
    off = _prefs(beta_mode=False)
    on = _prefs(beta_mode=True)

    # Act / Assert
    assert settings_store.is_enabled(GROUP, BETA, off) is False
    assert settings_store.is_enabled(GROUP, BETA, on) is True


def test_beta_mode_does_not_override_an_explicit_disable():
    # Arrange
    prefs = _prefs(commands={"inferconstraints": {"enabled": False}}, beta_mode=True)

    # Act / Assert
    assert settings_store.is_enabled(GROUP, BETA, prefs) is False


# ---------------------------------------------------------------------------
# is_command_available
# ---------------------------------------------------------------------------


def test_available_reads_the_live_preferences(monkeypatch):
    # Arrange: both hand-off targets registered, Global Parameters switched off.
    prefs = _prefs(commands={"globalParameters": {"enabled": False}})
    monkeypatch.setattr(settings_store, "load", lambda: prefs)

    # Act / Assert
    assert settings_store.is_command_available("assemblybuilder") is True
    assert settings_store.is_command_available("globalParameters") is False


def test_unknown_module_is_not_available(monkeypatch):
    # Arrange: a key that is not in the registry at all.
    monkeypatch.setattr(settings_store, "load", lambda: _prefs())

    # Act / Assert
    assert settings_store.is_command_available("nosuchcommand") is False


def test_handoff_targets_are_actually_registered():
    # Arrange / Act: guard against a rename silently turning a hand-off button
    # off for everyone, which is exactly what is_command_available would do for
    # a key no longer in the registry.
    modules = {cmd["module"] for _group, cmd in registry.iter_commands()}

    # Assert
    assert "assemblybuilder" in modules
    assert "globalParameters" in modules
