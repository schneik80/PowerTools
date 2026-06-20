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
