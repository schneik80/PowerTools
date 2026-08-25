# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.

# PowerTools Preferences.
#
# A single HTML palette that consolidates PowerTools settings: enable/disable
# command groups and individual commands, a beta visibility toggle, per-command
# settings sections, and hub/related-data status. Enablement applies on the next
# Fusion restart (the start-up gating in commands/__init__.py reads the store).
#
# This command is infrastructure: it is always loaded (see commands/__init__.py)
# and registers a single "PowerTools Preferences" entry directly in the QAT File
# dropdown (replacing the old "PowerTools Settings" flyout).

import json
import os
import subprocess
import sys
import urllib.parse

import adsk.core

from ... import command_registry as registry
from ... import config, settings_store
from ...lib import ptAddInUtils as ptutil

app = adsk.core.Application.get()
ui = app.userInterface

CMD_ID = "PT_preferences"
CMD_NAME = "PowerTools Preferences"
CMD_Description = "Configure PowerTools: enable commands, beta tier, and hub settings."

PALETTE_ID = config.preferences_palette_id
PALETTE_NAME = "PowerTools Preferences"

# No icon assets yet — an empty resource folder string is valid and renders the
# default menu glyph (the palette itself supplies all the visuals).
ICON_FOLDER = ""
_HTML_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "resources", "html"
)
PALETTE_URL = os.path.join(_HTML_DIR, "index.html").replace("\\", "/")
INIT_JS_PATH = os.path.join(_HTML_DIR, "init.js")

# The Related Data command that the Hub Settings section launches.
CONFIGHUB_CMD_ID = f"{config.COMPANY_NAME}_{config.ADDIN_NAME}_configHub"

# The picker the Team Add-ins section launches.
CONFIG_TEAM_ADDINS_CMD_ID = (
    f"{config.COMPANY_NAME}_{config.ADDIN_NAME}_configTeamAddins"
)


# ---------------------------------------------------------------------------
# Lifecycle — a single entry in the QAT File dropdown
# ---------------------------------------------------------------------------


def _qat_file_dropdown():
    qat = ui.toolbars.itemById("QAT")
    if not qat:
        return None
    return adsk.core.DropDownControl.cast(qat.controls.itemById("FileSubMenuCommand"))


# The File dropdown entry is this command's only access point, and start() runs
# once when the add-in loads. If the QAT is not resolvable at that moment - Fusion
# started with no document open, or the add-in loaded before the UI finished
# building - the entry used to be skipped silently and never retried, leaving
# Preferences unreachable for the rest of the session even after a document was
# opened. That is a soft lockout rather than a cosmetic problem: this palette is
# the only way to re-enable a disabled command, so the alternative is hand-editing
# settings/preferences.json.
_control_placed = False


def _ensure_control() -> bool:
    """Add the File-dropdown entry if it is not already there.

    Idempotent, so it is safe to call repeatedly from the retry handler.

    Returns:
        True if the entry is in place, False if the dropdown is unavailable.
    """
    global _control_placed
    cmd_def = ui.commandDefinitions.itemById(CMD_ID)
    if not cmd_def:
        return False
    file_dd = _qat_file_dropdown()
    if not file_dd:
        return False
    if not file_dd.controls.itemById(CMD_ID):
        file_dd.controls.addCommand(cmd_def)
    _control_placed = True
    return True


def _retry_placement(args) -> None:
    """Re-attempt placement once a document exists.

    Deliberately left registered after it succeeds rather than removing itself:
    unhooking a handler from inside its own dispatch is not worth the risk, and
    the flag check costs nothing on the tab switches that follow.
    """
    if _control_placed:
        return
    if _ensure_control():
        ptutil.log(f"{CMD_NAME}: File dropdown entry added on document activate.")


def start():
    global _control_placed
    _control_placed = False

    existing = ui.commandDefinitions.itemById(CMD_ID)
    if existing:
        existing.deleteMe()
    cmd_def = ui.commandDefinitions.addButtonDefinition(
        CMD_ID, CMD_NAME, CMD_Description, ICON_FOLDER
    )
    ptutil.add_handler(cmd_def.commandCreated, command_created)

    if not _ensure_control():
        # Say so. This is the one command whose job is to be reachable when
        # something else is misconfigured, and it was the only QAT command that
        # failed mute - openrecent already logs the same condition.
        ptutil.log(
            f"{CMD_NAME}: QAT File dropdown unavailable at start-up, so the File "
            f"menu entry was not added. Retrying on the next document activate. "
            f"Settings file: {config.SETTINGS_PREFS_FILE}"
        )
        ptutil.add_handler(app.documentActivated, _retry_placement)


def stop():
    global _control_placed
    _control_placed = False
    file_dd = _qat_file_dropdown()
    if file_dd:
        ctrl = file_dd.controls.itemById(CMD_ID)
        if ctrl:
            ctrl.deleteMe()
    cmd_def = ui.commandDefinitions.itemById(CMD_ID)
    if cmd_def:
        cmd_def.deleteMe()
    palette = ui.palettes.itemById(PALETTE_ID)
    if palette:
        palette.deleteMe()


def command_created(args: adsk.core.CommandCreatedEventArgs):
    """Open the palette straight from the click.

    Deliberately *not* by way of the command's execute event. This item has no
    CommandInputs and no dialog, so there is nothing for execute to commit —
    and execute only fires when Fusion runs the command through its
    document-scoped pipeline. With no document open the control was live and
    commandCreated fired, but the command terminated without executing, so the
    palette never opened and nothing appeared in the log because nothing had
    raised. The File-menu commands that already work with no document (Close
    All Documents, Toggle Data Pane, Scripts and Add-Ins) all do their work
    here for the same reason.
    """
    ptutil.log(f"{CMD_NAME}: opening palette.")
    _show_palette()


# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------


def _show_palette():
    palettes = ui.palettes
    palette = palettes.itemById(PALETTE_ID)
    if palette is not None:
        try:
            palette.deleteMe()
        except Exception:
            pass
        palette = None

    _write_init_js(_gather_state())
    palette = palettes.add(
        id=PALETTE_ID,
        name=PALETTE_NAME,
        htmlFileURL=PALETTE_URL,
        isVisible=True,
        showCloseButton=True,
        isResizable=True,
        width=920,
        height=760,
        useNewWebBrowser=True,
    )
    ptutil.add_handler(palette.closed, _palette_closed)
    ptutil.add_handler(palette.incomingFromHTML, _palette_incoming)
    if palette.dockingState == adsk.core.PaletteDockingStates.PaletteDockStateFloating:
        palette.dockingState = adsk.core.PaletteDockingStates.PaletteDockStateRight
    palette.isVisible = True


def _palette_closed(args: adsk.core.UserInterfaceGeneralEventArgs):
    palette = ui.palettes.itemById(PALETTE_ID)
    if palette is not None:
        try:
            palette.deleteMe()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


def _os_is_dark() -> bool:
    """Best-effort OS dark-mode detection (for the 'match device' theme)."""
    if sys.platform == "win32":
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\Themes\Personalize",
            ) as key:
                val, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
                return val == 0
        except Exception:
            return True
    if sys.platform == "darwin":
        try:
            out = subprocess.run(
                ["defaults", "read", "-g", "AppleInterfaceStyle"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            return out.stdout.strip() == "Dark"
        except Exception:
            return True
    return True


def _theme() -> str:
    themes = adsk.core.UserInterfaceThemes
    theme = app.preferences.generalPreferences.userInterfaceTheme
    if theme == themes.DeviceUserInterfaceTheme:
        is_dark = _os_is_dark()
    else:
        is_dark = theme in (
            themes.DarkBlueUserInterfaceTheme,
            themes.DarkGrayUserInterfaceTheme,
        )
    return "dark" if is_dark else "light"


def _module_for(key):
    # Imported (and cached) on demand via the commands package's lazy loader.
    # This runs only when the palette is shown, so it does not add to the
    # start-up hot path; it lets the palette display friendly names/descriptions
    # for every command, including ones the user has disabled.
    try:
        from .. import load_command

        return load_command(key)
    except Exception:
        return None


def _hub_info() -> dict:
    hub_id = hub_name = ""
    try:
        hub = app.data.activeHub
        if hub is not None:
            hub_id = getattr(hub, "id", "") or ""
            hub_name = getattr(hub, "name", "") or ""
    except Exception:
        pass

    cfg = {}
    configured = False
    if hub_id:
        try:
            config.reload_hub_config()
            cfg = config.COMPANY_HUB_CONFIGS.get(hub_id, {})
            configured = bool(cfg.get("project_id") and cfg.get("folder_id"))
        except Exception:
            pass
    return {
        "hubId": hub_id,
        "hubName": hub_name,
        "configured": configured,
        "projectName": cfg.get("project_name", ""),
        "folderName": cfg.get("folder_name", ""),
    }


def _team_addins_info() -> dict:
    """Status card data for the Team Add-ins section.

    Team Add-ins has nothing saved to report: the folder is a convention, so
    this asks the hub whether it is actually there. That is a live call, but it
    only happens when the user opens this palette.
    """
    info = {
        "state": "error",
        "hubName": "",
        "projectName": "",
        "folderName": "",
        "message": "",
        "packageCount": 0,
        "installedCount": 0,
        "checkedAt": "",
    }
    try:
        from ..teamaddins import sync, team_fs

        info.update(team_fs.folder_status(app))
        info.update(sync.installed_summary(team_fs.active_hub_id(app)))
    except Exception as exc:
        info["message"] = f"Could not read the hub: {exc}"
        ptutil.log(f"{CMD_NAME}: team add-ins status unavailable — {exc}")
    return info


def _gather_state() -> dict:
    prefs = settings_store.load()
    groups = []
    for g in registry.GROUPS:
        cmds = []
        for c in g["commands"]:
            mod = _module_for(c["module"])
            cmds.append(
                {
                    "key": c["module"],
                    "name": getattr(mod, "CMD_NAME", None) or c["module"],
                    "summary": getattr(mod, "CMD_Description", "") or "",
                    "doc": config.DOCS_BASE_URL + urllib.parse.quote(c["doc"]),
                    "beta": bool(c["beta"]),
                    "hasSettings": bool(c["has_settings"]),
                    "enabled": bool(
                        prefs["commands"].get(c["module"], {}).get("enabled", True)
                    ),
                }
            )
        groups.append(
            {
                "key": g["key"],
                "label": g["label"],
                "enabled": bool(prefs["groups"].get(g["key"], {}).get("enabled", True)),
                "commands": cmds,
            }
        )

    return {
        "theme": _theme(),
        "beta": bool(prefs.get("general", {}).get("beta_mode", False)),
        "groups": groups,
        "commandSettings": prefs.get("command_settings", {}),
        "settingsPath": config.SETTINGS_PREFS_FILE,
        "hub": _hub_info(),
        "teamAddins": _team_addins_info(),
        "restartNote": "Changes apply on the next Fusion restart.",
    }


def _write_init_js(state: dict) -> None:
    try:
        with open(INIT_JS_PATH, "w", encoding="utf-8") as fh:
            fh.write(f"window.__ptInit = {json.dumps(state)};\n")
    except Exception as exc:
        ptutil.log(f"{CMD_NAME}: could not write init.js — {exc}")


def _send_state(palette):
    if palette:
        palette.sendInfoToHTML("setState", json.dumps(_gather_state()))


# ---------------------------------------------------------------------------
# Incoming messages from the palette
# ---------------------------------------------------------------------------


def _mutate(fn):
    prefs = settings_store.load()
    fn(prefs)
    settings_store.save(prefs)


def _open_in_default_app(path: str):
    try:
        if sys.platform == "win32":
            os.startfile(path)  # noqa: F821 (Windows only)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception as exc:
        ptutil.log(f"{CMD_NAME}: could not open {path} — {exc}")


def _palette_incoming(html_args: adsk.core.HTMLEventArgs):
    action = html_args.action
    try:
        data = json.loads(html_args.data) if html_args.data else {}
    except Exception:
        data = {}

    palette = ui.palettes.itemById(PALETTE_ID)

    try:
        if action == "ready":
            _send_state(palette)

        elif action == "setBeta":
            value = bool(data.get("value"))
            _mutate(lambda p: p["general"].__setitem__("beta_mode", value))
            _send_state(palette)  # beta visibility changes the tree

        elif action == "setGroup":
            key = data.get("key")
            value = bool(data.get("enabled"))
            _mutate(
                lambda p: p["groups"].setdefault(key, {}).__setitem__("enabled", value)
            )

        elif action == "setCommand":
            key = data.get("key")
            value = bool(data.get("enabled"))
            _mutate(
                lambda p: (
                    p["commands"].setdefault(key, {}).__setitem__("enabled", value)
                )
            )

        elif action == "setCommandSetting":
            key = data.get("key")
            sub = data.get("sub")
            value = data.get("value")
            _mutate(
                lambda p: (
                    p.setdefault("command_settings", {})
                    .setdefault(key, {})
                    .__setitem__(sub, value)
                )
            )

        elif action == "openDoc":
            url = data.get("url")
            if url and url.startswith(("http://", "https://")):
                import webbrowser

                webbrowser.open(url)

        elif action == "openSettingsFile":
            settings_store.load()  # ensure the file exists
            _open_in_default_app(config.SETTINGS_PREFS_FILE)

        elif action == "importSettings":
            dlg = ui.createFileDialog()
            dlg.title = "Import PowerTools Settings"
            dlg.filter = "JSON files (*.json)"
            dlg.isMultiSelectEnabled = False
            if dlg.showOpen() == adsk.core.DialogResults.DialogOK:
                ok, msg = settings_store.import_from_file(dlg.filename)
                ui.messageBox(msg, CMD_NAME)
                if ok:
                    _send_state(palette)

        elif action == "browseHubFolder":
            cmd_def = ui.commandDefinitions.itemById(CONFIGHUB_CMD_ID)
            if cmd_def:
                cmd_def.execute()
            else:
                ui.messageBox(
                    "The Related Data commands are disabled. Enable them in the "
                    "Commands list and restart Fusion to configure a hub folder.",
                    CMD_NAME,
                )
            _send_state(palette)

        elif action == "setUpTeamAddinsFolder":
            cmd_def = ui.commandDefinitions.itemById(CONFIG_TEAM_ADDINS_CMD_ID)
            if cmd_def:
                cmd_def.execute()
            else:
                ui.messageBox(
                    "The Team Add-ins commands are disabled. Enable them in the "
                    "Commands list and restart Fusion to set up the folder.",
                    CMD_NAME,
                )
            _send_state(palette)

    except Exception:
        ptutil.handle_error(CMD_NAME)

    html_args.returnData = "OK"
