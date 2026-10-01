"""Favorites' dropdown rebuild: positional, in-place, and safe to interrupt.

The hazard this pins (issue #33, found by review after Open Recent's #29):
Favorites rebuilt its ``PTAT_fav_<i>`` buttons by deleting every definition
and adding them again, and its items navigate from ``commandCreated``. A
navigation that lands in another hub fires ``documentActivated`` synchronously
inside the clicked item's own command; the hub-change rebuild then tried to
delete the definition whose command was in flight, ``deleteMe()`` returned
False without raising, and ``addButtonDefinition`` on that id raised ``3 : a
command definition with that id already exists`` -- the rebuild abandoned with
the menu half-built.

Two layers are tested. ``commands/_menu_plan`` is pure (rule 13), shared with
Open Recent (``tests/test_openrecent_menu.py``), and decides which slots to
keep and remove; the cases here use Favorites' ``SLOTS``, which has no
empty-state placeholder. ``entry`` is driven against a fake
``commandDefinitions`` / ``ToolbarControls`` pair that behaves like Fusion on
the two points that matter: a duplicate id raises, and ``deleteMe()`` on a
locked id returns False and leaves the object in place. The fakes mirror the
Open Recent test's on purpose -- the two commands must stay on one rule.
"""

import importlib
from types import SimpleNamespace

import pytest

entry = importlib.import_module("PowerTools.commands.favorites.entry")
menu_plan = importlib.import_module("PowerTools.commands._menu_plan")

SLOTS = entry.SLOTS
ITEM = SLOTS.item_cmd_id
LIMIT = entry.MENU_LIMIT
FIXED = [entry.CMD_ADD_ID, entry.CMD_EDIT_ID, "separator"]


# ---------------------------------------------------------------------------
# _menu_plan (pure), with Favorites' slots
# ---------------------------------------------------------------------------


def test_slots_are_favorites_ids_without_a_placeholder():
    assert SLOTS == menu_plan.MenuSlots("PTAT_fav_", LIMIT)
    assert SLOTS.empty_id == ""
    assert ITEM(0) == "PTAT_fav_0"
    assert SLOTS.all_ids() == [ITEM(i) for i in range(LIMIT)]


def test_plan_keeps_a_prefix_of_slots_and_removes_the_whole_complement():
    keep, remove = SLOTS.plan_menu(3)
    assert keep == [ITEM(0), ITEM(1), ITEM(2)]
    assert remove == [ITEM(i) for i in range(3, LIMIT)]


def test_plan_for_no_items_removes_every_slot_and_adds_no_placeholder():
    keep, remove = SLOTS.plan_menu(0)
    assert keep == []
    assert remove == [ITEM(i) for i in range(LIMIT)]
    assert "" not in remove


def test_plan_at_the_limit_removes_nothing():
    keep, remove = SLOTS.plan_menu(LIMIT)
    assert len(keep) == LIMIT
    assert remove == []


def test_plan_rejects_counts_outside_the_slot_range():
    with pytest.raises(ValueError):
        SLOTS.plan_menu(LIMIT + 1)
    with pytest.raises(ValueError):
        SLOTS.plan_menu(-1)


def test_shared_item_text_falls_back_on_missing_or_blank():
    assert menu_plan.item_text({}, "display", "Unknown") == "Unknown"
    assert menu_plan.item_text({"display": ""}, "display", "Unknown") == "Unknown"
    assert menu_plan.item_text({"display": "A > B"}, "display", "Unknown") == "A > B"


def test_shared_signature_compares_values_and_presence():
    sig = menu_plan.menu_signature
    base = {"urn": "u", "display": "A", "thumb": "/x.png"}
    assert sig([base], ("urn", "display"), ("thumb",)) == (("u", "A", True),)
    assert sig([{"urn": "u"}], ("urn", "display")) == (("u", ""),)
    assert sig([], ("urn",)) == ()


# ---------------------------------------------------------------------------
# Fakes for the Fusion surface entry.py touches
# ---------------------------------------------------------------------------


class FakeDef:
    def __init__(self, owner, cmd_id, name, tooltip, resource_folder):
        self._owner = owner
        self.id = cmd_id
        self.name = name
        self.tooltip = tooltip
        self.resourceFolder = resource_folder
        self.commandCreated = object()  # identity only; handlers are recorded

    def deleteMe(self):
        if self.id in self._owner.locked:
            return False  # Fusion: refuses, does not raise
        self._owner.defs.pop(self.id, None)
        return True


class FakeDefs:
    def __init__(self):
        self.defs: dict[str, FakeDef] = {}
        self.locked: set[str] = set()
        self.adds: list[str] = []

    def itemById(self, cmd_id):
        return self.defs.get(cmd_id)

    def addButtonDefinition(self, cmd_id, name, tooltip, resource_folder=""):
        if cmd_id in self.defs:
            raise RuntimeError("3 : a command definition with that id already exists")
        d = FakeDef(self, cmd_id, name, tooltip, resource_folder)
        self.defs[cmd_id] = d
        self.adds.append(cmd_id)
        return d


class FakeControl:
    def __init__(self, owner, cmd_def):
        self._owner = owner
        self.id = cmd_def.id
        self.definition = cmd_def
        self.isEnabled = True

    def deleteMe(self):
        if self.id in self._owner.locked:
            return False
        self._owner.items = [c for c in self._owner.items if c.id != self.id]
        return True


class FakeControls:
    def __init__(self, locked):
        self.items: list[FakeControl] = []
        self.locked = locked
        self.adds: list[str] = []
        self.fail_on: set[str] = set()

    @property
    def count(self):
        return len(self.items)

    def item(self, i):
        return self.items[i]

    def itemById(self, cmd_id):
        return next((c for c in self.items if c.id == cmd_id), None)

    def addCommand(self, cmd_def, position_id="", is_before=True):
        if cmd_def.id in self.fail_on:
            raise RuntimeError("addCommand failed")
        if self.itemById(cmd_def.id):
            raise RuntimeError("a control with that id already exists")
        ctrl = FakeControl(self, cmd_def)
        if position_id:
            idx = next(i for i, c in enumerate(self.items) if c.id == position_id)
            self.items.insert(idx if is_before else idx + 1, ctrl)
        else:
            self.items.append(ctrl)
        self.adds.append(cmd_def.id)
        return ctrl

    def ids(self):
        return [c.id for c in self.items]

    def item_ids(self):
        """The dynamic part of the dropdown, below the fixed Add / Edit rows."""
        return [c.id for c in self.items if c.id not in FIXED]


def _fav(n, **extra):
    return {"name": n, "display": f"Hub > {n}", "urn": f"urn:{n}", **extra}


@pytest.fixture
def menu(monkeypatch):
    """A fresh entry module state wired to the fakes; returns a driver.

    ``hubs`` maps a hub id to that hub's favorites list; ``_load_favorites`` is
    replaced to read the active hub's entry, so ``switch_hub`` goes through
    the real ``_on_hub_changed`` and ``rebuild`` through ``_rebuild_menu``.
    """
    defs = FakeDefs()
    controls = FakeControls(defs.locked)
    for fixed_id in FIXED:  # Add, Edit, separator sit above the items
        controls.addCommand(SimpleNamespace(id=fixed_id))
    controls.adds.clear()
    handlers: list[tuple[object, object]] = []  # (commandCreated event, callback)
    navigated: list[str] = []
    hubs: dict[str, list[dict]] = {"A": []}

    def add_handler(event, callback, *, name=None, local_handlers=None):
        handlers.append((event, callback))
        (local_handlers if local_handlers is not None else []).append(callback)

    monkeypatch.setattr(entry, "ui", SimpleNamespace(commandDefinitions=defs))
    monkeypatch.setattr(
        entry, "app", SimpleNamespace(executeTextCommand=navigated.append)
    )
    monkeypatch.setattr(
        entry, "_favorites_dropdown", SimpleNamespace(controls=controls)
    )
    monkeypatch.setattr(entry, "local_handlers", [])
    monkeypatch.setattr(entry, "_owned_ids", set())
    monkeypatch.setattr(entry, "_item_targets", {})
    monkeypatch.setattr(entry, "_leftover_ids", set())
    monkeypatch.setattr(entry, "_active_hub_id", "A")
    monkeypatch.setattr(
        entry, "_load_favorites", lambda: list(hubs.get(entry._active_hub_id, []))
    )
    monkeypatch.setattr(
        entry,
        "ptutil",
        SimpleNamespace(
            add_handler=add_handler,
            log=lambda *a, **k: None,
            handle_error=lambda *a, **k: None,
        ),
    )

    def rebuild(favorites):
        hubs[entry._active_hub_id] = favorites
        entry._rebuild_menu()

    def switch_hub(hub_id, favorites):
        hubs[hub_id] = favorites
        entry._on_hub_changed(hub_id)

    def click(slot):
        cmd_def = defs.defs[ITEM(slot)]
        created = next(cb for ev, cb in handlers if ev is cmd_def.commandCreated)
        created(None)
        return created

    return SimpleNamespace(
        defs=defs,
        controls=controls,
        handlers=handlers,
        navigated=navigated,
        hubs=hubs,
        rebuild=rebuild,
        switch_hub=switch_hub,
        click=click,
    )


# ---------------------------------------------------------------------------
# entry._rebuild_menu
# ---------------------------------------------------------------------------


def test_first_build_creates_one_definition_and_control_per_item_in_order(menu):
    menu.rebuild([_fav("a"), _fav("b"), _fav("c")])
    assert menu.defs.adds == [ITEM(0), ITEM(1), ITEM(2)]
    assert menu.controls.ids() == FIXED + [ITEM(0), ITEM(1), ITEM(2)]
    assert menu.defs.defs[ITEM(1)].name == "Hub > b"
    assert menu.defs.defs[ITEM(1)].tooltip == "Navigate to Hub > b in Fusion Hub"
    assert entry._item_targets[ITEM(2)] == ("urn:c", "Hub > c")
    assert len(menu.handlers) == 3


def test_an_entry_without_a_display_gets_the_unknown_location_label(menu):
    menu.rebuild([{"urn": "urn:x"}])
    assert menu.defs.defs[ITEM(0)].name == entry.UNKNOWN_LOCATION_LABEL
    assert entry._item_targets[ITEM(0)] == ("urn:x", entry.UNKNOWN_LOCATION_LABEL)


def test_rebuilding_the_same_list_reuses_every_slot_in_place(menu):
    """No fast path exists (a rebuild runs only on a hub change or after Add /
    Edit), so the guarantee is reuse: nothing is re-added, no second handler."""
    items = [_fav("a"), _fav("b")]
    menu.rebuild(items)
    adds_before = (list(menu.defs.adds), list(menu.controls.adds))
    menu.rebuild([dict(i) for i in items])
    assert (menu.defs.adds, menu.controls.adds) == adds_before
    assert len(menu.handlers) == 2
    assert menu.controls.item_ids() == [ITEM(0), ITEM(1)]


def test_a_navigation_that_switches_hub_mid_click_reuses_the_in_flight_slot(menu):
    """The #33 sequence: click slot 1 in hub A; its commandCreated navigates;
    the navigation lands in hub B and fires documentActivated synchronously,
    so the hub-change rebuild runs *inside* slot 1's own command and Fusion
    will not delete that definition. Hub B has fewer favorites; the rebuild
    must still finish with slot 1 showing B's second entry."""
    menu.rebuild([_fav("a"), _fav("b"), _fav("c"), _fav("d")])

    def navigate_into_hub_b(text_command):
        menu.navigated.append(text_command)
        menu.defs.locked.add(ITEM(1))  # its command is in flight
        menu.controls.locked.add(ITEM(1))
        menu.switch_hub("B", [_fav("p"), _fav("q")])

    entry.app.executeTextCommand = navigate_into_hub_b
    created = menu.click(1)

    assert menu.navigated == ["Dashboard.ShowInLocation urn:b"]
    assert entry._active_hub_id == "B"
    assert menu.defs.adds == [ITEM(i) for i in range(4)]  # no second add
    assert menu.defs.defs[ITEM(1)].name == "Hub > q"
    assert menu.defs.defs[ITEM(1)].tooltip == "Navigate to Hub > q in Fusion Hub"
    assert entry._item_targets == {
        ITEM(0): ("urn:p", "Hub > p"),
        ITEM(1): ("urn:q", "Hub > q"),
    }
    assert menu.controls.item_ids() == [ITEM(0), ITEM(1)]
    assert set(menu.defs.defs) == {ITEM(0), ITEM(1)}
    assert len(menu.handlers) == 4  # one handler per definition, ever
    assert entry._leftover_ids == set()

    # The same handler now serves hub B's entry.
    entry.app.executeTextCommand = menu.navigated.append
    created(None)
    assert menu.navigated[-1] == "Dashboard.ShowInLocation urn:q"


def test_growing_appends_in_order_and_shrinking_removes_the_tail(menu):
    menu.rebuild([_fav("a"), _fav("b")])
    menu.rebuild([_fav("a"), _fav("b"), _fav("c"), _fav("d")])
    assert menu.controls.item_ids() == [ITEM(i) for i in range(4)]
    assert [menu.defs.defs[ITEM(i)].name for i in range(4)] == [
        "Hub > a",
        "Hub > b",
        "Hub > c",
        "Hub > d",
    ]

    menu.rebuild([_fav("a"), _fav("b")])
    assert menu.controls.ids() == FIXED + [ITEM(0), ITEM(1)]
    assert set(menu.defs.defs) == {ITEM(0), ITEM(1)}
    assert set(entry._item_targets) == {ITEM(0), ITEM(1)}


def test_an_empty_hub_removes_every_item_and_keeps_the_fixed_rows(menu):
    menu.rebuild([_fav("a"), _fav("b")])
    menu.switch_hub("B", [])
    assert menu.controls.ids() == FIXED
    assert menu.defs.defs == {}
    assert entry._item_targets == {}


def test_a_rebuild_that_raises_midway_is_retried_on_the_next_event(menu):
    menu.controls.fail_on.add(ITEM(2))
    items = [_fav("a"), _fav("b"), _fav("c")]
    with pytest.raises(RuntimeError):
        menu.rebuild(items)
    assert menu.controls.item_ids() == [ITEM(0), ITEM(1)]

    menu.controls.fail_on.clear()
    menu.rebuild(items)
    assert menu.controls.item_ids() == [ITEM(0), ITEM(1), ITEM(2)]
    assert menu.defs.adds == [ITEM(0), ITEM(1), ITEM(2)]  # slot 2 added once
    assert len(menu.handlers) == 3


def test_a_foreign_definition_is_recreated_or_else_adopted_once(menu):
    """Left by an unclean reload: its handler belongs to a dead module."""
    stale = menu.defs.addButtonDefinition(ITEM(0), "old", "old tip")
    menu.defs.addButtonDefinition(ITEM(1), "old1", "old tip")
    menu.defs.locked.add(ITEM(1))  # this one Fusion will not release
    menu.defs.adds.clear()

    menu.rebuild([_fav("a"), _fav("b")])

    assert menu.defs.adds == [ITEM(0)]  # recreated
    assert menu.defs.defs[ITEM(0)] is not stale
    assert menu.defs.defs[ITEM(1)].name == "Hub > b"  # adopted, renamed in place
    assert len(menu.handlers) == 2
    assert entry._owned_ids == {ITEM(0), ITEM(1)}


def test_a_slot_that_refuses_deletion_is_retried_on_the_next_rebuild(menu):
    menu.rebuild([_fav("a"), _fav("b"), _fav("c")])
    menu.defs.locked.add(ITEM(2))
    menu.controls.locked.add(ITEM(2))

    shorter = [_fav("a"), _fav("b")]
    menu.rebuild(shorter)
    assert ITEM(2) in menu.defs.defs  # could not go yet
    assert ITEM(2) in menu.controls.ids()
    assert entry._leftover_ids == {ITEM(2)}
    assert ITEM(2) not in entry._item_targets  # a click on it is ignored

    menu.defs.locked.clear()
    menu.controls.locked.clear()
    menu.rebuild(shorter)
    assert ITEM(2) not in menu.defs.defs
    assert menu.controls.item_ids() == [ITEM(0), ITEM(1)]
    assert entry._leftover_ids == set()


def test_a_click_navigates_to_whatever_the_slot_shows_now(menu):
    menu.rebuild([_fav("a"), _fav("b")])
    created = menu.click(1)
    assert menu.navigated == ["Dashboard.ShowInLocation urn:b"]

    menu.rebuild([_fav("n"), _fav("a"), _fav("b")])
    created(None)  # same handler, slot 1 now shows "a"
    assert menu.navigated == [
        "Dashboard.ShowInLocation urn:b",
        "Dashboard.ShowInLocation urn:a",
    ]

    menu.rebuild([])
    created(None)  # slot gone: ignored, no exception
    assert len(menu.navigated) == 2


def test_a_failed_navigation_shows_the_message_and_does_not_raise(menu):
    shown = []
    entry.ui.messageBox = lambda text, title: shown.append((text, title))

    def boom(_):
        raise RuntimeError("no such location")

    entry.app.executeTextCommand = boom
    menu.rebuild([_fav("a")])
    menu.click(0)
    assert shown == [
        (
            "Unable to navigate to 'Hub > a'.\n\nThe location may no longer exist.",
            "Favorites",
        )
    ]


def test_a_list_over_the_limit_shows_the_first_slots_only(menu):
    menu.rebuild([_fav(str(i)) for i in range(LIMIT + 5)])
    assert menu.controls.item_ids() == [ITEM(i) for i in range(LIMIT)]
    assert menu.defs.defs[ITEM(LIMIT - 1)].name == f"Hub > {LIMIT - 1}"


def test_clear_items_sweeps_the_whole_id_range_and_forgets_targets(menu):
    menu.rebuild([_fav("a"), _fav("b")])
    # Something an earlier, untracked build left behind.
    menu.defs.addButtonDefinition(ITEM(7), "ghost", "")
    menu.controls.addCommand(menu.defs.defs[ITEM(7)])

    entry._clear_items()

    assert menu.defs.defs == {}
    assert menu.controls.ids() == FIXED  # the fixed rows are stop()'s to remove
    assert entry._item_targets == {}
    assert entry._owned_ids == set()
