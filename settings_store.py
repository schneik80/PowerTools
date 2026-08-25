# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.
#
# Preferences store over settings/preferences.json. Defaults are derived from the
# command registry so newly added commands/groups gain sensible defaults
# automatically. Read by the start-up gating loop (commands/__init__.py), by the
# Preferences palette, and by the few commands that expose per-command settings.

import json
import os

from . import command_registry as registry
from . import config
from .lib import ptAddInUtils as ptutil

# Default folder sets for the "Add Project Folders" command (defaultfolders).
# These were hard-coded in the command; they now seed the user-editable lists.
DEFAULT_FOLDER_SETS = {
    "basic": ["_Global Parameters", "Drawings", "Archive", "Obit", "Wiki"],
    "advanced": [
        "01 - Assemblies",
        "02 - ECAD",
        "03 - Parts",
        "04 - Purchased Parts",
        "05 - 3DPCB Parts",
        "06 - Drawings",
        "07 - Documents",
        "08 - Render",
        "09 - Manufacture",
        "10 - Archive",
        "XX - Obit",
    ],
}

# Commands that ship switched off. Everything not listed here defaults to
# enabled. A user can turn any of these on in Preferences; this only decides
# what a fresh install starts with, since load() merges stored values over the
# defaults and so never overrides an existing choice.
DEFAULT_DISABLED_COMMANDS = frozenset(
    {
        "componentwarn",
        "docopen",
        "getandupdate",
        "refmanager",
        "sketchcirclecenterpoint",
        "versiondiff",
    }
)

# Commands that are only usable together, keyed by the set's lead command.
# Global Parameters owns the parameter documents; Link Global Parameters
# derives them into a design and Refresh Global Parameters Cache rewarms their
# cache — none of the satellites means anything with the others off, so
# Preferences offers ONE checkbox for the whole set and enablement resolves
# through the lead's flag. A member's own entry in preferences.json is inert:
# ignoring it (rather than migrating it) means an old selectively-disabled
# state heals itself the moment the lead is read.
COMMAND_SETS = {
    "globalParameters": ("linkGlobalParameters", "refreshGlobalParametersCache"),
}

# member module -> lead module, for enablement lookups.
SET_LEAD = {
    member: lead for lead, members in COMMAND_SETS.items() for member in members
}

# Per-command settings sections (defaults). Keyed by command module name.
COMMAND_SETTING_DEFAULTS = {
    "componentwarn": {"warn_non_leaf": False},
    "changecyclecolor": {"show_in_context_menu": True},
    "docopen": {"run_on_open": False, "run_on_activate": False},
    "defaultfolders": {
        "basic": list(DEFAULT_FOLDER_SETS["basic"]),
        "advanced": list(DEFAULT_FOLDER_SETS["advanced"]),
    },
    # Team Add-ins. The launch check is deferred rather than run inline, so
    # startup_delay_seconds is how long after Fusion finishes launching the
    # hub is read; auto_reload=False keeps every update waiting for a restart
    # instead of stopping and restarting a running add-in in place.
    "teamaddins": {
        "auto_check_on_launch": True,
        "startup_delay_seconds": 25,
        "auto_reload": True,
    },
}


def _defaults() -> dict:
    data = {
        "version": 1,
        "general": {"beta_mode": False},
        "groups": {g["key"]: {"enabled": True} for g in registry.GROUPS},
        "commands": {
            c["module"]: {"enabled": c["module"] not in DEFAULT_DISABLED_COMMANDS}
            for _, c in registry.iter_commands()
        },
        "command_settings": {k: dict(v) for k, v in COMMAND_SETTING_DEFAULTS.items()},
    }
    return data


# Commands whose registry key (and so whose settings key) has been renamed.
# Without this, a rename silently resets everyone's enable/disable state for
# that command back to the default, and leaves a dead key in preferences.json.
RENAMED_COMMANDS = {
    "assemblyintent": "assemblypalette",
}


def _migrate_renames(stored: dict) -> dict:
    """Carry settings across a command rename. Returns *stored*, modified.

    Applied to the stored file before it is merged over the defaults. The old
    key is dropped, so it disappears from disk the next time anything is saved.
    An existing entry under the new key always wins.
    """
    for old, new in RENAMED_COMMANDS.items():
        for section in ("commands", "command_settings"):
            block = stored.get(section)
            if not isinstance(block, dict) or old not in block:
                continue
            value = block.pop(old)
            block.setdefault(new, value)
    return stored


def _deep_merge(base: dict, override) -> dict:
    """Return *base* with *override* merged in (override wins; dicts recurse)."""
    out = dict(base)
    for key, val in (override or {}).items():
        if isinstance(val, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], val)
        else:
            out[key] = val
    return out


def _migrate_legacy(defaults: dict) -> dict:
    """First-run only: seed docopen enablement from the old cache/settings.json."""
    try:
        legacy = config.load_settings()
        if "show_in_location_enabled" in legacy:
            defaults["commands"]["docopen"]["enabled"] = bool(
                legacy["show_in_location_enabled"]
            )
    except Exception:
        pass
    return defaults


# Memoized merged preferences. The start-up gating loop plus the convenience
# accessors below call load() dozens of times per session; without this each
# call re-read and re-parsed the file and re-ran the deep-merge. Invalidated by
# save() (the only in-process writer).
_cache = None


def load() -> dict:
    """Return the full preferences dict, creating defaults on first run.

    The merged result is memoized; save() clears the cache.
    """
    global _cache
    if _cache is not None:
        return _cache
    defaults = _defaults()
    if not os.path.isfile(config.SETTINGS_PREFS_FILE):
        save(_migrate_legacy(defaults))
        return load()
    stored = ptutil.read_json(config.SETTINGS_PREFS_FILE, {})
    if not isinstance(stored, dict):
        stored = {}
    stored = _migrate_renames(stored)
    # Merge over defaults so newly added groups/commands pick up their defaults.
    _cache = _deep_merge(defaults, stored)
    return _cache


def save(data: dict) -> None:
    global _cache
    ptutil.write_json_atomic(config.SETTINGS_PREFS_FILE, data)
    _cache = None


# ── Convenience accessors ─────────────────────────────────────────────────────


def beta_mode() -> bool:
    return bool(load().get("general", {}).get("beta_mode", False))


def is_group_enabled(key: str) -> bool:
    return bool(load().get("groups", {}).get(key, {}).get("enabled", True))


def is_command_enabled(key: str) -> bool:
    """Whether command *key* is enabled, resolving set members through their lead.

    Args:
        key: The command's registry key (its folder name under commands/).

    Returns:
        True when the command's flag — or, for a COMMAND_SETS member, its lead
        command's flag — is enabled.
    """
    key = SET_LEAD.get(key, key)
    return bool(load().get("commands", {}).get(key, {}).get("enabled", True))


def is_enabled(group: dict, cmd: dict, prefs: dict) -> bool:
    """Whether a registry (group, command) pair should run, per *prefs*.

    The single rule behind both the start-up gating loop in
    ``commands/__init__.py`` and :func:`is_command_available`, so the two can
    never disagree about what is running.

    Args:
        group: A registry group dict (needs ``key``).
        cmd: A registry command dict (needs ``module``, may have ``beta``).
        prefs: An already-loaded preferences dict, as returned by load().

    Returns:
        True when the group is enabled, beta mode covers the command, and the
        command itself is enabled.
    """
    if not prefs.get("groups", {}).get(group["key"], {}).get("enabled", True):
        return False
    if cmd.get("beta") and not prefs.get("general", {}).get("beta_mode", False):
        return False
    # A COMMAND_SETS member runs on its lead command's flag — the set shares
    # one Preferences checkbox, and a member's own stored flag is inert.
    key = SET_LEAD.get(cmd["module"], cmd["module"])
    return bool(prefs.get("commands", {}).get(key, {}).get("enabled", True))


def is_command_available(module: str) -> bool:
    """True if *module* is registered and will actually be running this session.

    Commands that offer a hand-off to another command use this so they do not
    advertise a button for something the user has switched off in Preferences
    — a disabled command never registers its command definition, so the
    hand-off would be a dead end.

    Args:
        module: The command's registry key (its folder name under commands/).

    Returns:
        True when the command is registered and enabled; False otherwise,
        including for a module that is not in the registry at all.
    """
    prefs = load()
    for group, cmd in registry.iter_commands():
        if cmd["module"] == module:
            return is_enabled(group, cmd, prefs)
    return False


def command_setting(module: str, sub: str, default=None):
    return load().get("command_settings", {}).get(module, {}).get(sub, default)


# ── Import (browse + replace) ─────────────────────────────────────────────────


def validate(data) -> bool:
    return (
        isinstance(data, dict)
        and isinstance(data.get("general"), dict)
        and isinstance(data.get("groups"), dict)
        and isinstance(data.get("commands"), dict)
        # Reject imported files carrying unexpected top-level keys.
        and set(data).issubset(_defaults().keys())
    )


def import_from_file(path: str):
    """Validate *path* as a preferences JSON and REPLACE the active settings.

    Returns (ok: bool, message: str).
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        return False, f"Could not read JSON: {exc}"
    if not validate(data):
        return False, "That file is not a valid PowerTools preferences file."
    save(_deep_merge(_defaults(), data))
    return True, "Settings imported. Restart Fusion to apply."
