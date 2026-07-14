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

CMD_ID = "PT-preferences"
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

local_handlers = []


# ---------------------------------------------------------------------------
# Lifecycle — a single entry in the QAT File dropdown
# ---------------------------------------------------------------------------


def _qat_file_dropdown():
    qat = ui.toolbars.itemById("QAT")
    if not qat:
        return None
    return adsk.core.DropDownControl.cast(qat.controls.itemById("FileSubMenuCommand"))


def start():
    existing = ui.commandDefinitions.itemById(CMD_ID)
    if existing:
        existing.deleteMe()
    cmd_def = ui.commandDefinitions.addButtonDefinition(
        CMD_ID, CMD_NAME, CMD_Description, ICON_FOLDER
    )
    ptutil.add_handler(cmd_def.commandCreated, command_created)

    file_dd = _qat_file_dropdown()
    if file_dd and not file_dd.controls.itemById(CMD_ID):
        file_dd.controls.addCommand(cmd_def)


def stop():
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
    ptutil.add_handler(
        args.command.execute, command_execute, local_handlers=local_handlers
    )


def command_execute(args: adsk.core.CommandEventArgs):
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

    except Exception:
        ptutil.handle_error(CMD_NAME)

    html_args.returnData = "OK"
