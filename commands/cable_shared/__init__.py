# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.
"""Shared modules for the Cable command family.

Serves Define Wires, Route Wire, Update Wire, and Wire Report (the same
shape as ``commands/partnumber_shared``): ``schema`` is the single source
of truth for the PowerTools.Cable attribute schema, ``routing`` holds the
pure sizing/payload math, and ``builder`` is the Fusion-side wire and
cable construction. Not a command folder - the registry only loads keys it
lists, so this package has no entry.py.
"""
