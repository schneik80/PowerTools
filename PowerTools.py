# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2022-2026 IMA LLC

# Consolidated PowerTools add-in entry point.
# Fusion calls run() when the add-in starts and stop() when it stops.
from . import commands
from .lib import ptAddInUtils as ptutil


def run(context):
    try:
        # Runs commands.start() which first creates the shared UI access points,
        # then starts every command module defined in commands/__init__.py.
        commands.start()

    except:
        ptutil.handle_error('run')


def stop(context):
    try:
        # Remove all of the event handlers the add-in created.
        ptutil.clear_handlers()

        # Runs commands.stop() which stops every command module and then removes
        # the shared UI access points.
        commands.stop()

    except:
        ptutil.handle_error('stop')
