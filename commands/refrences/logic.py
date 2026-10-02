# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.
"""Document References -- pure logic, no ``adsk`` import."""

from __future__ import annotations


def unique_by_id(*groups) -> list:
    """Every item of *groups*, in order, keeping the first of each ``id``.

    A drawing's Uses list merges two sources that can name the same design --
    the cloud's ``DataFile.childReferences`` and the open document's
    ``documentReferences`` -- so each design must appear once. Duck-typed: an
    item is anything with an ``id``; one whose ``id`` cannot be read, or is
    empty, is dropped, since it could be neither deduplicated nor opened.
    """
    seen: set = set()
    merged: list = []
    for group in groups:
        for item in group or []:
            try:
                item_id = item.id
            except Exception:
                continue
            if not item_id or item_id in seen:
                continue
            seen.add(item_id)
            merged.append(item)
    return merged
