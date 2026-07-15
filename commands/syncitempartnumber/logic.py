# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.
"""Pure, Fusion-free helpers for the Sync Item to Part Number command.

Kept separate from ``entry.py`` so the enablement decision and value
normalization can be unit-tested without a live Fusion runtime (see
``tests/test_syncitempartnumber_enablement.py``). The only dependency is the
``is_fusion_auto_pn`` predicate from the shared ``partnumber_shared.intent``
module, which flags Fusion's auto-generated ``YYYY-MM-DD-HH-MM-SS-mmm``
placeholder part numbers.
"""

from __future__ import annotations

from ..partnumber_shared.intent import is_fusion_auto_pn


def normalize_item(item_number: str) -> str:
    """Normalize a Fusion Manage item number for comparison (strip only)."""
    return item_number.strip() if item_number else ""


def normalize_pn(part_number: str) -> str:
    """Normalize a part number for comparison.

    Strips surrounding whitespace and treats Fusion's auto-generated timestamp
    placeholder as "no meaningful part number" (empty), so an item number is
    considered a real change against a placeholder.
    """
    if not part_number:
        return ""
    part_number = part_number.strip()
    return "" if is_fusion_auto_pn(part_number) else part_number


def needs_sync(item_number: str, part_number: str) -> bool:
    """Return True when a sync is actually needed for a component.

    True only when an Item Number exists AND it differs from the (normalized)
    Part Number. When there is no Item Number, or it already matches the Part
    Number, no sync is needed and ``command_execute`` reports that instead of
    changing anything. (The button itself is enabled whenever a design is
    active; this predicate governs what execute does.)
    """
    item = normalize_item(item_number)
    return bool(item) and item != normalize_pn(part_number)
