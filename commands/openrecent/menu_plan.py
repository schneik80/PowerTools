# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.

"""Open Recent — the adsk-free part of the flyout rebuild.

The flyout holds one button per recent document, addressed by *position*:
``PT_openrecent_item_0`` is always the newest entry, whatever document that is.
A rebuild therefore never needs to delete-and-recreate a definition — it
updates the definitions it keeps in place, adds the ones it is short of and
removes the tail it no longer needs. This module decides which ids fall in
which bucket, and what each kept button shows; ``entry.py`` applies that
through the Fusion API.

Why positional reuse matters: ``CommandDefinition.deleteMe()`` returns False
instead of raising when Fusion will not release the definition — observed when
the item's own command is in flight, because ``app.documents.open`` inside the
item's ``commandCreated`` fires ``documentActivated`` synchronously and that
triggers this very rebuild. Re-adding the surviving id then raised
``3 : a command definition with that id already exists`` and the whole rebuild
was abandoned. Reusing a definition that is already there side-steps the
question of whether it can be deleted.
"""

ITEM_ID_PREFIX = "PT_openrecent_item_"
EMPTY_ITEM_ID = "PT_openrecent_empty"

EMPTY_LABEL = "No recent documents"
EMPTY_TOOLTIP = "Recently used documents appear here as you open and work on them."

UNTITLED_LABEL = "Untitled"
GENERIC_TOOLTIP = "Recently used document"


def item_cmd_id(index: int) -> str:
    """The command-definition id of the button at *index* (0 = newest)."""
    return f"{ITEM_ID_PREFIX}{index}"


def item_label(item: dict) -> str:
    """The button text: the document name, or a placeholder for a blank one."""
    return item.get("name") or UNTITLED_LABEL


def item_tooltip(item: dict) -> str:
    """The tooltip: the Data Panel location, or generic text when unknown."""
    return item.get("location") or GENERIC_TOOLTIP


def menu_signature(items: list[dict]) -> tuple:
    """What the user can see of *items*; equal signatures need no rebuild.

    ``version`` is included so a re-saved document refreshes its tool-clip;
    ``thumbPath`` only as a presence flag, since the path itself is derived
    from the id and does not change.
    """
    return tuple(
        (
            it["dataFileId"],
            it.get("name", ""),
            it.get("location", ""),
            it.get("version", ""),
            bool(it.get("thumbPath")),
        )
        for it in items
    )


def plan_menu(item_count: int, limit: int) -> tuple[list[str], list[str]]:
    """Split the flyout's possible ids into (keep, remove) for *item_count* items.

    ``keep`` is the ids to show, in menu order; ``remove`` is every other id
    this flyout can ever own — the unused tail of item slots plus, when there
    are items, the empty-state placeholder. Removing the whole complement (not
    just the slots the previous build used) is what makes a rebuild recover
    from a half-finished predecessor without any record of it.
    """
    if item_count < 0:
        raise ValueError(f"item_count must be >= 0, got {item_count}")
    if item_count > limit:
        raise ValueError(f"item_count {item_count} exceeds the menu limit {limit}")
    keep = [item_cmd_id(i) for i in range(item_count)]
    remove = [item_cmd_id(i) for i in range(item_count, limit)]
    if item_count:
        remove.append(EMPTY_ITEM_ID)
    return keep, remove
