#  Copyright 2022 by Autodesk, Inc.
#  Permission to use, copy, modify, and distribute this software in object code form
#  for any purpose and without fee is hereby granted, provided that the above copyright
#  notice appears in all copies and that both that copyright notice and the limited
#  warranty and restricted rights notice below appear in all supporting documentation.
#
#  AUTODESK PROVIDES THIS PROGRAM "AS IS" AND WITH ALL FAULTS. AUTODESK SPECIFICALLY
#  DISCLAIMS ANY IMPLIED WARRANTY OF MERCHANTABILITY OR FITNESS FOR A PARTICULAR USE.
#  AUTODESK, INC. DOES NOT WARRANT THAT THE OPERATION OF THE PROGRAM WILL BE
#  UNINTERRUPTED OR ERROR FREE.

import datetime
import os
import subprocess
import time
import traceback
from contextlib import contextmanager

import adsk.core

app = adsk.core.Application.get()
ui = app.userInterface

# Attempt to read DEBUG and PERF_TRACE flags from parent config.
try:
    from ... import config

    DEBUG = getattr(config, "DEBUG", False)
    PERF_TRACE = getattr(config, "PERF_TRACE", False)
    _CACHE_PATH = getattr(config, "CACHE_PATH", "")
except Exception:
    DEBUG = False
    PERF_TRACE = False
    _CACHE_PATH = ""

# Persistent debug log (only written when DEBUG is on). The Text Commands
# window is not saved to disk and Fusion's own app log only receives our
# error-level entries, so without this file there is nothing to inspect
# after the fact.
_DEBUG_LOG_MAX_BYTES = 5_000_000


def debug_log_path() -> str:
    """Path of the PowerTools debug log file ("" when no cache path)."""
    if not _CACHE_PATH:
        return ""
    return os.path.join(_CACHE_PATH, "powertools-debug.log")


def _level_tag(level) -> str:
    try:
        if level == adsk.core.LogLevels.ErrorLogLevel:
            return "ERROR"
        if level == adsk.core.LogLevels.WarningLogLevel:
            return "WARN"
    except Exception:
        pass
    return "INFO"


def _append_debug_file(message: str, level) -> None:
    """Append one timestamped line to the debug log (size-capped)."""
    path = debug_log_path()
    if not path:
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    mode = "a"
    try:
        if os.path.getsize(path) > _DEBUG_LOG_MAX_BYTES:
            mode = "w"  # start over rather than grow without bound
    except OSError:
        pass  # file does not exist yet
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(path, mode, encoding="utf-8") as handle:
        handle.write(f"{stamp} [{_level_tag(level)}] {message}\n")


def log(
    message: str,
    level: adsk.core.LogLevels = adsk.core.LogLevels.InfoLogLevel,
    force_console: bool = False,
):
    """Utility function to easily handle logging in your app.

    All logging is gated on config.DEBUG: stdout, the Fusion log file, and
    the Fusion Text Commands window are only written when config.DEBUG is
    True. When DEBUG is False this function is a no-op.

    Arguments:
    message -- The message to log.
    level -- The logging severity level.
    force_console -- Retained for backward compatibility. It no longer
                     overrides the config.DEBUG gate.
    """
    # Every log destination below is gated on config.DEBUG.
    if not DEBUG:
        return

    # Goes to the attached debugger / IDE stdout only.
    print(message)

    # Persist every entry to the PowerTools debug log file so diagnostics
    # survive the session (the Text Commands window is not saved to disk).
    try:
        _append_debug_file(message, level)
    except Exception:
        pass  # the logger must never take the add-in down with it

    # Errors are also persisted to the Fusion log file.
    if level == adsk.core.LogLevels.ErrorLogLevel:
        app.log(message, level, adsk.core.LogTypes.FileLogType)

    # User-facing log in the Fusion Text Commands window.
    app.log(message, level, adsk.core.LogTypes.ConsoleLogType)


def pump_events_for(seconds: float, tick_seconds: float = 0.03) -> None:
    """Wait ``seconds`` while keeping the Fusion UI and upload pipeline alive.

    Fusion commands run on the UI thread, so a bare ``time.sleep`` freezes the
    whole application for its duration and also starves Fusion's asynchronous
    save/upload pipeline of the ``adsk.doEvents()`` pumping it needs to advance.
    This waits the same total time but pumps events every ``tick_seconds`` so the
    UI stays responsive (progress dialog, Cancel) and background uploads keep
    progressing, without busy-spinning at 100% CPU.

    Arguments:
    seconds -- Total time to wait. Values <= 0 pump once and return.
    tick_seconds -- Maximum gap between ``adsk.doEvents()`` pumps.
    """
    if seconds <= 0:
        adsk.doEvents()
        return
    tick = max(0.005, min(tick_seconds, seconds))
    end = time.monotonic() + seconds
    while True:
        adsk.doEvents()
        if time.monotonic() >= end:
            return
        time.sleep(tick)


def clipText(linkText):
    """Utility function to copy text to the clipboard.

    Augments:
    linkText -- string to copy to system clipboard.
    """
    if os.name == "nt":
        subprocess.run(["clip.exe"], input=linkText.strip().encode("utf-8"), check=True)
    else:
        subprocess.run(["pbcopy"], input=linkText.strip().encode("utf-8"), check=True)
    app.log(f"link: {linkText} was added to clipboard")


def isSaved() -> bool:
    """Utility function to check if the active document has been saved.

    Returns:
    bool -- True if the active document has been saved, False otherwise.
    """
    # Check that the active document has been saved.
    if not app.activeDocument.isSaved:
        ui.messageBox(
            "The active document must be saved before you can continue.",
            "Please Save",
            0,
            2,
        )
        return False
    return True


def handle_error(name: str, show_message_box: bool = False):
    """Utility function to simplify error handling.

    Arguments:
    name -- A name used to label the error.
    show_message_box -- Indicates if the error should be shown in the message box.
                        If False, it will only be shown in the Text Command window
                        and logged to the log file.
    """

    log("===== Error =====", adsk.core.LogLevels.ErrorLogLevel)
    log(f"{name}\n{traceback.format_exc()}", adsk.core.LogLevels.ErrorLogLevel)

    # If desired you could show an error as a message box.
    if show_message_box:
        ui.messageBox(f"{name}\n{traceback.format_exc()}")


@contextmanager
def perf_timer(label: str, context: str = ""):
    """Wall-clock timer for diagnosing performance bottlenecks.

    Wraps a block of code and, when config.PERF_TRACE is True, emits a
    structured [PERF] line to the Fusion Text Command window on exit.

    Usage:
        with ptutil.perf_timer("documents.open", "GP._load_from_doc"):
            params_doc = app.documents.open(data_file, False)

    Has zero runtime cost (no timing overhead, no log write) when PERF_TRACE is False.
    """
    if not PERF_TRACE:
        yield
        return
    t0 = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - t0
        log(f"[PERF] {context:<30} | {label:<35} | {elapsed:.3f} s", force_console=True)
