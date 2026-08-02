# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.
"""Shared HTML-palette plumbing for PowerTools palette commands.

The palette commands (Assembly Intent, Assembly Builder, Preferences, Wire
Report) share three load-bearing mechanisms that used to be copy-pasted
per command:

- Theme resolution (:func:`fusion_theme` / :func:`os_is_dark`): Fusion's
  UI theme, with the OS setting resolved for "device" mode.
- The init.js first-paint sidecar (:func:`write_init_js`):
  ``palettes.add`` rejects URL query strings and the page loads async, so
  the initial state is written to a git-ignored ``init.js`` the page reads
  synchronously as ``window.__ptInit``.
- The delete-then-add lifecycle (:func:`recreate_palette`): Fusion's
  ``palette.closed`` sometimes leaves a torn-down palette object in
  ``ui.palettes`` whose ``isVisible`` toggles silently no-op; deleting any
  pre-existing palette and adding a fresh one is the reliable cure.
"""

import json
import subprocess
import sys

import adsk.core

from .event_utils import add_handler
from .general_utils import log

app = adsk.core.Application.get()
ui = app.userInterface


def os_is_dark() -> bool:
    """Best-effort OS dark-mode detection (for the 'match device' theme)."""
    if sys.platform == "win32":
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\Themes\Personalize",
            ) as key:
                # AppsUseLightTheme: 1 = light, 0 = dark.
                val, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
                return val == 0
        except Exception:
            return True  # Fusion's modern default look is dark
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


def fusion_theme() -> str:
    """Fusion's effective UI theme: ``"dark"`` or ``"light"``.

    ``userInterfaceTheme`` is Classic(0)/LightGray(1) = light,
    DarkBlue(2)/DarkGray(3) = dark, Device(4) = follow the OS.
    """
    themes = adsk.core.UserInterfaceThemes
    theme = app.preferences.generalPreferences.userInterfaceTheme
    if theme == themes.DeviceUserInterfaceTheme:
        return "dark" if os_is_dark() else "light"
    if theme in (
        themes.DarkBlueUserInterfaceTheme,
        themes.DarkGrayUserInterfaceTheme,
    ):
        return "dark"
    return "light"


def write_init_js(path: str, state: dict, log_name: str = "palette") -> None:
    """Write *state* to the init.js first-paint sidecar as window.__ptInit.

    The page loads it via ``<script src="init.js">`` so the state is
    available synchronously before first paint; as an external script
    there is no HTML parser, so an embedded ``</script>`` in names is
    safe. Trust it only for the initial render: Windows CEF caches
    init.js by URL, so pages must push fresh state over
    ``sendInfoToHTML`` on their htmlReady handshake.
    """
    try:
        with open(path, "w", encoding="utf-8") as sidecar:
            sidecar.write(f"window.__ptInit = {json.dumps(state)};\n")
    except Exception as e:
        log(f"{log_name}: could not write init.js - {e}")


def recreate_palette(
    palette_id: str,
    name: str,
    url: str,
    width: int,
    height: int,
    handlers: dict | None = None,
    local_handlers: list | None = None,
    docking: int | None = None,
) -> adsk.core.Palette:
    """Delete-then-add a docked HTML palette and hook its event handlers.

    Fusion's ``palette.closed`` sometimes leaves a palette object in
    ``ui.palettes`` that has been internally torn down - toggling
    ``isVisible`` on it silently no-ops. Deleting any pre-existing palette
    and creating a fresh one is the reliable cure, and re-registers the
    handlers cleanly each time instead of accumulating stale ones across
    sessions.

    Args:
        palette_id: The palette id (see config's palette-id constants).
        name: Palette display title (also used as the log label).
        url: The palette's htmlFileURL.
        width: Initial palette width in pixels.
        height: Initial palette height in pixels.
        handlers: Callbacks keyed ``"incoming"`` (incomingFromHTML),
            ``"closed"``, and ``"navigating"`` (navigatingURL); absent
            keys are not hooked.
        local_handlers: Keep-alive list for the handlers (None keeps them
            in the global handler list).
        docking: Applied when the fresh palette comes up floating
            (right-docked when None).

    Returns:
        The new visible Palette.
    """
    palettes = ui.palettes
    palette = palettes.itemById(palette_id)
    if palette is not None:
        try:
            palette.deleteMe()
        except Exception as e:
            log(f"{name}: could not delete the stale palette - {e}")
    palette = palettes.add(
        id=palette_id,
        name=name,
        htmlFileURL=url,
        isVisible=True,
        showCloseButton=True,
        isResizable=True,
        width=width,
        height=height,
        useNewWebBrowser=True,
    )
    for key, event in (
        ("incoming", palette.incomingFromHTML),
        ("closed", palette.closed),
        ("navigating", palette.navigatingURL),
    ):
        callback = (handlers or {}).get(key)
        if callback is not None:
            add_handler(event, callback, local_handlers=local_handlers)
    if docking is None:
        docking = adsk.core.PaletteDockingStates.PaletteDockStateRight
    if palette.dockingState == adsk.core.PaletteDockingStates.PaletteDockStateFloating:
        palette.dockingState = docking
    palette.isVisible = True
    return palette
