# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.
#
# Consolidated command registry runner. Imports every command module declared in
# command_registry.GROUPS, then on start-up creates the shared UI access points,
# always starts the Preferences command, and starts each registered command only
# when its group + command are enabled and (for beta commands) beta mode is on.
# Enablement is read from settings_store at start-up, so changes apply on the
# next Fusion restart.

import importlib

from . import _ui_bootstrap
from .preferences import entry as preferences
from .. import command_registry as registry
from .. import settings_store
from ..lib import ptAddInUtils as ptutil

# Command entry modules are imported lazily and cached here — only when a command
# is actually started, or when the Preferences palette introspects it for display.
# Disabled commands are therefore never imported on the start-up hot path (and a
# module that fails to import no longer breaks loading of the whole add-in).
MODULES = {}


def load_command(module_key: str):
    """Import (and cache) a command's entry module by its registry key."""
    module = MODULES.get(module_key)
    if module is None:
        module = importlib.import_module(f".{module_key}.entry", __package__)
        MODULES[module_key] = module
    return module


# Modules whose start() actually ran this session, so stop() only tears those down.
_started = []


def _should_start(group, cmd, prefs) -> bool:
    if not prefs.get("groups", {}).get(group["key"], {}).get("enabled", True):
        return False
    if cmd.get("beta") and not prefs.get("general", {}).get("beta_mode", False):
        return False
    return bool(prefs.get("commands", {}).get(cmd["module"], {}).get("enabled", True))


def start():
    # Shared "Power Tools" panel is created once, before any command registers.
    try:
        _ui_bootstrap.create_shared_access_points()
    except Exception:
        ptutil.handle_error("_ui_bootstrap.create_shared_access_points")

    # Preferences is infrastructure — always available so the user can re-enable
    # anything they have turned off.
    try:
        preferences.start()
    except Exception:
        ptutil.handle_error("preferences")

    prefs = settings_store.load()
    for group, cmd in registry.iter_commands():
        if not _should_start(group, cmd, prefs):
            continue
        try:
            # Import happens here, lazily, only for commands that will start.
            module = load_command(cmd["module"])
            module.start()
            _started.append(module)
        except Exception:
            ptutil.handle_error(cmd["module"])


def stop():
    # Stop only the commands that actually started, newest first.
    for module in reversed(_started):
        try:
            module.stop()
        except Exception:
            ptutil.handle_error(getattr(module, "__name__", "command"))
    _started.clear()

    try:
        preferences.stop()
    except Exception:
        ptutil.handle_error("preferences")

    # Remove the shared access points once every command has cleaned up.
    try:
        _ui_bootstrap.remove_shared_access_points()
    except Exception:
        ptutil.handle_error("_ui_bootstrap.remove_shared_access_points")
