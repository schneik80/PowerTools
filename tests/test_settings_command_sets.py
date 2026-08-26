"""Unit tests for settings_store.COMMAND_SETS resolution.

The three Global Parameters commands (globalParameters, linkGlobalParameters,
refreshGlobalParametersCache) are one capability: the satellites mean nothing
with the others off. Preferences therefore offers a single checkbox for the
set, and enablement resolves through the lead command's flag everywhere it is
read -- the start-up gate in ``commands/__init__.py`` and the
``is_command_enabled`` accessor. A member's own entry in preferences.json is
inert, so an old selectively-disabled state heals itself without migration.

Modules use package-relative imports, so they are loaded via their full
package path with the conftest scaffolding in place.
"""

import importlib
from pathlib import Path

PT_PKG = Path(__file__).resolve().parent.parent.name
settings_store = importlib.import_module(f"{PT_PKG}.settings_store")
registry = importlib.import_module(f"{PT_PKG}.command_registry")
commands_pkg = importlib.import_module(f"{PT_PKG}.commands")

LEAD = "globalParameters"
MEMBERS = ("linkGlobalParameters", "refreshGlobalParametersCache")

ASSEMBLY_GROUP = {"key": "assembly", "label": "Assembly"}


def _prefs(commands=None, groups=None) -> dict:
    """Build a minimal preferences dict shaped like settings_store.load()'s.

    Args:
        commands: The "commands" section, defaulting to empty.
        groups: The "groups" section, defaulting to the assembly group on.

    Returns:
        A preferences dict.
    """
    return {
        "general": {"beta_mode": False},
        "groups": groups if groups is not None else {"assembly": {"enabled": True}},
        "commands": commands or {},
    }


# ---------------------------------------------------------------------------
# The set definition itself
# ---------------------------------------------------------------------------


def test_set_lead_is_derived_from_command_sets():
    for lead, members in settings_store.COMMAND_SETS.items():
        for member in members:
            assert settings_store.SET_LEAD[member] == lead


def test_set_commands_are_all_registered():
    # A rename in the registry without one here would silently detach the set:
    # the member would grow its own row back, or the lead's flag would gate
    # nothing. Same trap settings_store.RENAMED_COMMANDS exists for.
    modules = {cmd["module"] for _group, cmd in registry.iter_commands()}
    for lead, members in settings_store.COMMAND_SETS.items():
        assert lead in modules
        for member in members:
            assert member in modules


def test_set_members_share_the_lead_command_group():
    # The Preferences payload drops member rows and annotates the lead, which
    # only reads correctly while the whole set lives in one registry group.
    group_of = {}
    for group, cmd in registry.iter_commands():
        group_of[cmd["module"]] = group["key"]
    for lead, members in settings_store.COMMAND_SETS.items():
        for member in members:
            assert group_of[member] == group_of[lead]


# ---------------------------------------------------------------------------
# is_command_enabled resolves members through the lead
# ---------------------------------------------------------------------------


def test_member_follows_a_disabled_lead(monkeypatch):
    # Arrange: lead off; a member's own flag says on and must be ignored.
    prefs = _prefs(
        commands={
            LEAD: {"enabled": False},
            MEMBERS[0]: {"enabled": True},
        }
    )
    monkeypatch.setattr(settings_store, "load", lambda: prefs)

    # Act / Assert
    assert settings_store.is_command_enabled(LEAD) is False
    for member in MEMBERS:
        assert settings_store.is_command_enabled(member) is False


def test_member_follows_an_enabled_lead_over_its_own_stale_flag(monkeypatch):
    # Arrange: the pre-set state a user could have saved -- one member off on
    # its own. The lead's flag wins, healing the split without migration.
    prefs = _prefs(
        commands={
            LEAD: {"enabled": True},
            MEMBERS[1]: {"enabled": False},
        }
    )
    monkeypatch.setattr(settings_store, "load", lambda: prefs)

    # Act / Assert
    for member in MEMBERS:
        assert settings_store.is_command_enabled(member) is True


def test_non_set_command_still_reads_its_own_flag(monkeypatch):
    # Arrange
    prefs = _prefs(commands={"assemblybuilder": {"enabled": False}})
    monkeypatch.setattr(settings_store, "load", lambda: prefs)

    # Act / Assert
    assert settings_store.is_command_enabled("assemblybuilder") is False
    assert settings_store.is_command_enabled("assemblypalette") is True


# ---------------------------------------------------------------------------
# The start-up gate applies the same rule
# ---------------------------------------------------------------------------


def _cmd(module: str) -> dict:
    return {"module": module, "beta": False}


def test_should_start_gates_members_on_the_lead():
    # Arrange
    prefs = _prefs(
        commands={
            LEAD: {"enabled": False},
            MEMBERS[0]: {"enabled": True},
        }
    )

    # Act / Assert: neither the lead nor its members start.
    assert commands_pkg._should_start(ASSEMBLY_GROUP, _cmd(LEAD), prefs) is False
    for member in MEMBERS:
        assert commands_pkg._should_start(ASSEMBLY_GROUP, _cmd(member), prefs) is False


def test_should_start_runs_members_when_the_lead_is_on():
    # Arrange: a member's own stale disable is ignored.
    prefs = _prefs(
        commands={
            LEAD: {"enabled": True},
            MEMBERS[1]: {"enabled": False},
        }
    )

    # Act / Assert
    for member in MEMBERS:
        assert commands_pkg._should_start(ASSEMBLY_GROUP, _cmd(member), prefs) is True


def test_should_start_still_honours_the_group_gate_for_members():
    # Arrange: set enabled, whole Assembly group off.
    prefs = _prefs(
        commands={LEAD: {"enabled": True}},
        groups={"assembly": {"enabled": False}},
    )

    # Act / Assert
    assert commands_pkg._should_start(ASSEMBLY_GROUP, _cmd(LEAD), prefs) is False
    for member in MEMBERS:
        assert commands_pkg._should_start(ASSEMBLY_GROUP, _cmd(member), prefs) is False
