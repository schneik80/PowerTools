# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.

"""OS-aware log file conveniences shared across commands."""

import os
import subprocess
import sys
import tempfile


def default_log_directory() -> str:
    """Return the default directory for log files based on the current OS."""
    if sys.platform in ("darwin", "win32"):
        return tempfile.gettempdir()
    return os.path.expanduser("~/Documents")


def open_live_log_viewer(log_file_path: str):
    """Open a platform-native live log viewer for the given file.

    macOS: Console.app via `open -a Console <path>` — natively follows live log files.
    Windows: PowerShell + `Get-Content -Wait`.

    Returns (success: bool, message: str).
    """
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", "-a", "Console", log_file_path])
            return True, "Opened live log viewer in Console.app"

        if sys.platform == "win32":
            command = f'Get-Content -Path "{log_file_path}" -Wait'
            subprocess.Popen(
                [
                    "powershell",
                    "-NoExit",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-Command",
                    command,
                ]
            )
            return True, "Opened live log viewer in PowerShell"

        return (
            False,
            "Live log viewer auto-open is currently supported on macOS and Windows only",
        )
    except Exception as e:
        return False, f"Failed to open live log viewer: {e}"
