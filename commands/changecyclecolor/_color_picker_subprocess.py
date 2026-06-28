# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.

"""Standalone color-picker script run as a subprocess from ``entry.py``.

tkinter cannot take over the run loop inside Fusion's process on macOS
(Cocoa/Qt conflict — ``tk.Tk()`` hangs). Launching this script in a fresh
Python process gives Tk its own clean run loop. Emits the chosen hex on
stdout (e.g. ``#aabbcc``); empty stdout means the user cancelled.

Argument: optional initial color, hex with leading ``#`` (default ``#808080``).
"""

import sys


def main() -> int:
    try:
        import tkinter as tk
        from tkinter import colorchooser
    except ImportError as exc:
        sys.stderr.write(f"tkinter unavailable: {exc}\n")
        return 2

    initial = sys.argv[1] if len(sys.argv) > 1 else "#808080"

    root = tk.Tk()
    root.withdraw()
    try:
        root.lift()
        root.attributes("-topmost", True)
        root.update_idletasks()
    except Exception:
        pass

    try:
        _rgb, hex_str = colorchooser.askcolor(
            color=initial, parent=root, title="Pick a color"
        )
    except Exception as exc:
        sys.stderr.write(f"colorchooser error: {exc}\n")
        return 3
    finally:
        try:
            root.destroy()
        except Exception:
            pass

    if hex_str:
        sys.stdout.write(hex_str)
    return 0


if __name__ == "__main__":
    sys.exit(main())
