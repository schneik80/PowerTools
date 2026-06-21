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

from . import config
from . import command_registry as registry

# Per-command settings sections (defaults). Keyed by command module name.
COMMAND_SETTING_DEFAULTS = {
    "componentwarn": {"warn_non_leaf": False},
    "docopen": {"run_on_open": True, "run_on_activate": True},
}


def _defaults() -> dict:
    data = {
        "version": 1,
        "general": {"beta_mode": False},
        "groups": {g["key"]: {"enabled": True} for g in registry.GROUPS},
        "commands": {c["module"]: {"enabled": True} for _, c in registry.iter_commands()},
        "command_settings": {k: dict(v) for k, v in COMMAND_SETTING_DEFAULTS.items()},
    }
    return data


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


def load() -> dict:
    """Return the full preferences dict, creating defaults on first run."""
    defaults = _defaults()
    if not os.path.isfile(config.SETTINGS_PREFS_FILE):
        save(_migrate_legacy(defaults))
        return load()
    try:
        with open(config.SETTINGS_PREFS_FILE, "r", encoding="utf-8") as f:
            stored = json.load(f)
        if not isinstance(stored, dict):
            stored = {}
    except Exception:
        stored = {}
    # Merge over defaults so newly added groups/commands pick up their defaults.
    return _deep_merge(defaults, stored)


def save(data: dict) -> None:
    os.makedirs(config.SETTINGS_DIR, exist_ok=True)
    with open(config.SETTINGS_PREFS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


# ── Convenience accessors ─────────────────────────────────────────────────────

def beta_mode() -> bool:
    return bool(load().get("general", {}).get("beta_mode", False))


def is_group_enabled(key: str) -> bool:
    return bool(load().get("groups", {}).get(key, {}).get("enabled", True))


def is_command_enabled(key: str) -> bool:
    return bool(load().get("commands", {}).get(key, {}).get("enabled", True))


def command_setting(module: str, sub: str, default=None):
    return load().get("command_settings", {}).get(module, {}).get(sub, default)


# ── Import (browse + replace) ─────────────────────────────────────────────────

def validate(data) -> bool:
    return (
        isinstance(data, dict)
        and isinstance(data.get("general"), dict)
        and isinstance(data.get("groups"), dict)
        and isinstance(data.get("commands"), dict)
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
