# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.

# Consolidated PowerTools add-in entry point.
# Fusion calls run() when the add-in starts and stop() when it stops.
from . import commands, config
from .lib import ptAddInUtils as ptutil


def run(context):
    try:
        # Start the attach-debug server first (no-op unless the .debug marker
        # enables it) so breakpoints can bind during the rest of startup.
        _maybe_start_debug_server()

        # Runs commands.start() which first creates the shared UI access points,
        # then starts every command module defined in commands/__init__.py.
        commands.start()

    except Exception:
        ptutil.handle_error('run')


def _maybe_start_debug_server():
    """Start an in-process debugpy server when the ``.debug`` marker enables it.

    Inverts Fusion's VS Code-only Debug button: the add-in listens and an
    external DAP client (Zed, or a VS Code "attach" config) connects. Gated on
    config.WAIT_FOR_DEBUGGER (tied to the ``.debug`` marker) so it never runs in
    a shipped build.

    Non-fatal by design: if debugpy is missing or the server cannot start, log a
    warning and continue so the add-in still loads. See docs/dev/debugging.md.
    """
    if not config.WAIT_FOR_DEBUGGER:
        return
    try:
        import debugpy

        if not getattr(debugpy, '_fusion_listening', False):
            try:
                debugpy.listen(
                    ('127.0.0.1', config.DEBUGGER_PORT),
                    # Run the adapter inside Fusion's process — spawning
                    # sys.executable would make macOS launch a second Fusion.
                    in_process_debug_adapter=True,
                )
            except RuntimeError:
                # listen() was already called this session (e.g. Fusion's VS Code
                # Debug button injected its own debugpy). Safe to keep going.
                pass
            debugpy._fusion_listening = True
        if config.DEBUGGER_BLOCK_UNTIL_ATTACHED:
            debugpy.wait_for_client()
    except Exception:
        # The debugger is a developer convenience; never let it block startup.
        ptutil.log('PowerTools: debugpy attach server not started (continuing).')


def stop(context):
    try:
        # Remove all of the event handlers the add-in created.
        ptutil.clear_handlers()

        # Runs commands.stop() which stops every command module and then removes
        # the shared UI access points.
        commands.stop()

    except Exception:
        ptutil.handle_error('stop')
