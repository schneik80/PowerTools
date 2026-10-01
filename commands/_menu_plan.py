# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.

"""Positional flyout rebuilds -- the adsk-free rule shared by the dynamic menus.

A flyout that lists a changing set of things (recent documents, favourite
locations) holds one button per entry, addressed by *position*: slot 0 is
always the first entry, whatever that entry is right now. A rebuild therefore
never deletes and recreates a definition -- it updates the definitions it keeps
in place, adds the ones it is short of and removes the tail it no longer
needs. This module decides which ids fall in which bucket; each command's
``entry.py`` applies that through the Fusion API with the same four moves
(``_ensure_definition`` / ``_ensure_control`` / ``_remove_item`` /
``_clear_items``) and one ``commandCreated`` handler per definition that reads
its slot's current target at click time.

Why positional reuse matters: ``CommandDefinition.deleteMe()`` returns False
instead of raising when Fusion will not release the definition -- observed when
the item's own command is in flight, because the work done inside the item's
``commandCreated`` (``app.documents.open``, a hub-switching navigation) fires
``documentActivated`` synchronously and that triggers this very rebuild.
Re-adding the surviving id then raised ``3 : a command definition with that id
already exists`` and the whole rebuild was abandoned (issue #29, Open Recent;
issue #34, Favorites). Reusing a definition that is already there side-steps
the question of whether it can be deleted.

Used by ``commands/openrecent/entry.py`` and ``commands/favorites/entry.py``;
tested by ``tests/test_openrecent_menu.py`` and ``tests/test_favorites_menu.py``.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class MenuSlots:
    """The id range one flyout owns.

    ``prefix`` + index is a slot's command-definition id; ``limit`` is how many
    slots exist (the menu never shows more); ``empty_id``, when given, is the
    id of a disabled placeholder shown instead of an empty menu.
    """

    prefix: str
    limit: int
    empty_id: str = ""

    def item_cmd_id(self, index: int) -> str:
        """The command-definition id of the button at *index* (0 = first)."""
        return f"{self.prefix}{index}"

    def all_ids(self) -> list[str]:
        """Every id this flyout can ever own, whatever an earlier build tracked."""
        ids = [self.item_cmd_id(i) for i in range(self.limit)]
        if self.empty_id:
            ids.append(self.empty_id)
        return ids

    def plan_menu(self, item_count: int) -> tuple[list[str], list[str]]:
        """Split the flyout's ids into (keep, remove) for *item_count* items.

        ``keep`` is the ids to show, in menu order; ``remove`` is every other
        id this flyout can ever own -- the unused tail of item slots plus,
        when there are items, the empty-state placeholder. Removing the whole
        complement (not just the slots the previous build used) is what makes
        a rebuild recover from a half-finished predecessor without any record
        of it.
        """
        if item_count < 0:
            raise ValueError(f"item_count must be >= 0, got {item_count}")
        if item_count > self.limit:
            raise ValueError(
                f"item_count {item_count} exceeds the menu limit {self.limit}"
            )
        keep = [self.item_cmd_id(i) for i in range(item_count)]
        remove = [self.item_cmd_id(i) for i in range(item_count, self.limit)]
        if item_count and self.empty_id:
            remove.append(self.empty_id)
        return keep, remove


def item_text(item: dict, key: str, fallback: str) -> str:
    """A button's text from ``item[key]``, or *fallback* when missing or blank."""
    return item.get(key) or fallback


def menu_signature(items: list[dict], keys: tuple[str, ...], presence_keys=()) -> tuple:
    """What the user can see of *items*; equal signatures need no rebuild.

    *keys* are compared by value (missing -> ``""``); *presence_keys* only as
    a flag, for fields whose value is derived and cannot change on its own
    (a thumbnail path keyed by the document id).
    """
    return tuple(
        tuple(it.get(k, "") for k in keys)
        + tuple(bool(it.get(k)) for k in presence_keys)
        for it in items
    )
