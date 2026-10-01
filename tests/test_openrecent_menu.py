"""Open Recent's flyout rebuild: positional, in-place, and safe to interrupt.

The failure this pins (issue: "_rebuild_menu adds a command definition whose id
already exists", macOS pre-production 2706.0.97, 2026-09-30): a user clicks a
recent item; its ``commandCreated`` opens the document; ``documentActivated``
fires synchronously inside that click and rebuilds the menu; the old rebuild
deleted every definition and re-added it, but ``CommandDefinition.deleteMe()``
returned False for the one whose command was in flight, and
``addButtonDefinition`` on that id raised ``3 : a command definition with that
id already exists``. The rebuild was abandoned with half the menu gone.

Two layers are tested. ``commands/_menu_plan`` is pure (rule 13), shared with
Favorites (``tests/test_favorites_menu.py``), and decides which slots to keep
and remove; the cases here use Open Recent's ``SLOTS``. ``entry`` is driven against a fake ``commandDefinitions`` /
``ToolbarControls`` pair that behaves like Fusion on the two points that
matter: a duplicate id raises, and ``deleteMe()`` on a locked id returns False
and leaves the object in place.
"""

import importlib
from types import SimpleNamespace

import pytest

entry = importlib.import_module("PowerTools.commands.openrecent.entry")
menu_plan = importlib.import_module("PowerTools.commands._menu_plan")

SLOTS = entry.SLOTS
ITEM = SLOTS.item_cmd_id
EMPTY = entry.EMPTY_ITEM_ID
LIMIT = entry.MENU_LIMIT


# ---------------------------------------------------------------------------
# _menu_plan (pure), with Open Recent's slots and text
# ---------------------------------------------------------------------------


def test_slots_are_open_recents_ids():
    assert SLOTS == menu_plan.MenuSlots("PT_openrecent_item_", LIMIT, EMPTY)
    assert ITEM(0) == "PT_openrecent_item_0"
    assert SLOTS.all_ids() == [ITEM(i) for i in range(LIMIT)] + [EMPTY]


def test_plan_keeps_a_prefix_of_slots_and_removes_the_whole_complement():
    keep, remove = SLOTS.plan_menu(3)
    assert keep == [ITEM(0), ITEM(1), ITEM(2)]
    assert remove == [ITEM(i) for i in range(3, LIMIT)] + [EMPTY]


def test_plan_for_no_items_removes_every_slot_but_not_the_placeholder():
    keep, remove = SLOTS.plan_menu(0)
    assert keep == []
    assert remove == [ITEM(i) for i in range(LIMIT)]
    assert EMPTY not in remove


def test_plan_at_the_limit_removes_only_the_placeholder():
    keep, remove = SLOTS.plan_menu(LIMIT)
    assert len(keep) == LIMIT
    assert remove == [EMPTY]


def test_plan_rejects_counts_outside_the_slot_range():
    with pytest.raises(ValueError):
        SLOTS.plan_menu(LIMIT + 1)
    with pytest.raises(ValueError):
        SLOTS.plan_menu(-1)


def test_signature_tracks_version_and_thumbnail_presence_only():
    base = {"dataFileId": "a", "name": "A", "location": "Hub > P", "version": "3"}
    assert entry.menu_signature([base]) == entry.menu_signature([dict(base)])
    resaved = dict(base, version="4")
    assert entry.menu_signature([resaved]) != entry.menu_signature([base])
    with_thumb = dict(base, thumbPath="/tmp/x.png")
    other_thumb = dict(base, thumbPath="/tmp/y.png")
    assert entry.menu_signature([with_thumb]) != entry.menu_signature([base])
    assert entry.menu_signature([with_thumb]) == entry.menu_signature([other_thumb])


def test_label_and_tooltip_fall_back_when_the_item_is_sparse():
    assert entry.item_label({"name": ""}) == entry.UNTITLED_LABEL
    assert entry.item_label({"name": "Valve"}) == "Valve"
    assert entry.item_tooltip({}) == entry.GENERIC_TOOLTIP
    assert entry.item_tooltip({"location": "Hub > P"}) == "Hub > P"


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
        self.toolClipFilename = ""
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


def _item(n, **extra):
    return {"dataFileId": f"urn:{n}", "name": n, "location": f"Hub > {n}", **extra}


@pytest.fixture
def menu(monkeypatch):
    """A fresh entry module state wired to the fakes; returns a driver."""
    defs = FakeDefs()
    controls = FakeControls(defs.locked)
    handlers: list[tuple[object, object]] = []  # (commandCreated event, callback)
    items_box = {"items": []}

    def add_handler(event, callback, *, name=None, local_handlers=None):
        handlers.append((event, callback))
        (local_handlers if local_handlers is not None else []).append(callback)

    monkeypatch.setattr(entry, "ui", SimpleNamespace(commandDefinitions=defs))
    monkeypatch.setattr(entry, "_dropdown", SimpleNamespace(controls=controls))
    monkeypatch.setattr(entry, "local_handlers", [])
    monkeypatch.setattr(entry, "_last_signature", None)
    monkeypatch.setattr(entry, "_owned_ids", set())
    monkeypatch.setattr(entry, "_item_targets", {})
    monkeypatch.setattr(entry, "_leftover_ids", set())
    monkeypatch.setattr(entry, "_active_data_file_id", lambda: "")
    monkeypatch.setattr(
        entry,
        "recents",
        SimpleNamespace(list_recent=lambda **kw: list(items_box["items"])),
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

    def rebuild(items):
        items_box["items"] = items
        entry._rebuild_menu()

    return SimpleNamespace(
        defs=defs, controls=controls, handlers=handlers, rebuild=rebuild
    )


# ---------------------------------------------------------------------------
# entry._rebuild_menu
# ---------------------------------------------------------------------------


def test_first_build_creates_one_definition_and_control_per_item_in_order(menu):
    menu.rebuild([_item("a"), _item("b"), _item("c")])
    assert menu.defs.adds == [ITEM(0), ITEM(1), ITEM(2)]
    assert menu.controls.ids() == [ITEM(0), ITEM(1), ITEM(2)]
    assert menu.defs.defs[ITEM(1)].name == "b"
    assert menu.defs.defs[ITEM(1)].tooltip == "Hub > b"
    assert entry._item_targets[ITEM(2)] == ("urn:c", "c")
    assert len(menu.handlers) == 3


def test_unchanged_list_is_a_no_op(menu):
    items = [_item("a"), _item("b")]
    menu.rebuild(items)
    adds_before = (list(menu.defs.adds), list(menu.controls.adds))
    menu.rebuild([dict(i) for i in items])
    assert (menu.defs.adds, menu.controls.adds) == adds_before
    assert len(menu.handlers) == 2


def test_the_logged_sequence_reuses_the_in_flight_definition_instead_of_re_adding(
    menu,
):
    """Click item 1 -> documents.open -> documentActivated -> rebuild while
    PT_openrecent_item_1 cannot be deleted. The list shifts (the opened
    document is now active and excluded), and the rebuild must still finish."""
    menu.rebuild([_item("a"), _item("b"), _item("c"), _item("d")])
    menu.defs.locked.add(ITEM(1))  # its command is in flight

    # "b" was opened: it leaves the list, "x" is newest.
    menu.rebuild([_item("x"), _item("a"), _item("c"), _item("d")])

    assert menu.defs.adds == [ITEM(i) for i in range(4)]  # no second add
    assert menu.defs.defs[ITEM(1)].name == "a"
    assert menu.defs.defs[ITEM(1)].tooltip == "Hub > a"
    assert entry._item_targets[ITEM(1)] == ("urn:a", "a")
    assert menu.controls.ids() == [ITEM(i) for i in range(4)]
    assert len(menu.handlers) == 4  # one handler per definition, ever
    assert entry._leftover_ids == set()


def test_growing_appends_in_order_and_shrinking_removes_the_tail(menu):
    menu.rebuild([_item("a"), _item("b")])
    menu.rebuild([_item("n"), _item("a"), _item("b"), _item("c")])
    assert menu.controls.ids() == [ITEM(i) for i in range(4)]
    assert [menu.defs.defs[ITEM(i)].name for i in range(4)] == ["n", "a", "b", "c"]

    menu.rebuild([_item("n"), _item("a")])
    assert menu.controls.ids() == [ITEM(0), ITEM(1)]
    assert set(menu.defs.defs) == {ITEM(0), ITEM(1)}
    assert set(entry._item_targets) == {ITEM(0), ITEM(1)}


def test_empty_list_shows_a_disabled_placeholder_that_later_items_replace(menu):
    menu.rebuild([_item("a")])
    menu.rebuild([])
    assert menu.controls.ids() == [EMPTY]
    assert menu.controls.itemById(EMPTY).isEnabled is False
    assert set(menu.defs.defs) == {EMPTY}
    assert entry._item_targets == {}

    menu.rebuild([_item("b")])
    assert menu.controls.ids() == [ITEM(0)]
    assert EMPTY not in menu.defs.defs


def test_a_rebuild_that_raises_midway_is_retried_on_the_next_event(menu):
    menu.controls.fail_on.add(ITEM(2))
    items = [_item("a"), _item("b"), _item("c")]
    with pytest.raises(RuntimeError):
        menu.rebuild(items)
    assert entry._last_signature is None  # not recorded as complete
    assert menu.controls.ids() == [ITEM(0), ITEM(1)]

    menu.controls.fail_on.clear()
    menu.rebuild(items)  # same signature: must not take the fast path
    assert menu.controls.ids() == [ITEM(0), ITEM(1), ITEM(2)]
    assert entry._last_signature == entry.menu_signature(items)
    assert menu.defs.adds == [ITEM(0), ITEM(1), ITEM(2)]  # slot 2 added once


def test_a_foreign_definition_is_recreated_or_else_adopted_once(menu):
    """Left by an unclean reload: its handler belongs to a dead module."""
    stale = menu.defs.addButtonDefinition(ITEM(0), "old", "old tip")
    menu.defs.addButtonDefinition(ITEM(1), "old1", "old tip")
    menu.defs.locked.add(ITEM(1))  # this one Fusion will not release
    menu.defs.adds.clear()

    menu.rebuild([_item("a"), _item("b")])

    assert menu.defs.adds == [ITEM(0)]  # recreated
    assert menu.defs.defs[ITEM(0)] is not stale
    assert menu.defs.defs[ITEM(1)].name == "b"  # adopted, renamed in place
    assert len(menu.handlers) == 2
    assert entry._owned_ids == {ITEM(0), ITEM(1)}


def test_a_slot_that_refuses_deletion_is_retried_despite_an_unchanged_list(menu):
    menu.rebuild([_item("a"), _item("b"), _item("c")])
    menu.defs.locked.add(ITEM(2))
    menu.controls.locked.add(ITEM(2))

    shorter = [_item("a"), _item("b")]
    menu.rebuild(shorter)
    assert ITEM(2) in menu.defs.defs  # could not go yet
    assert entry._leftover_ids == {ITEM(2)}

    menu.defs.locked.clear()
    menu.rebuild(shorter)  # same signature, but leftovers force a pass
    assert ITEM(2) not in menu.defs.defs
    assert menu.controls.ids() == [ITEM(0), ITEM(1)]
    assert entry._leftover_ids == set()


def test_a_click_opens_whatever_the_slot_shows_now(menu, monkeypatch):
    opened = []
    monkeypatch.setattr(entry, "_open_recent", lambda df, name: opened.append(df))
    menu.rebuild([_item("a"), _item("b")])
    slot1_def = menu.defs.defs[ITEM(1)]
    created = next(cb for ev, cb in menu.handlers if ev is slot1_def.commandCreated)

    created(None)
    menu.rebuild([_item("n"), _item("a"), _item("b")])
    created(None)  # same handler, slot now shows "a"
    assert opened == ["urn:b", "urn:a"]

    menu.rebuild([])
    created(None)  # slot gone: ignored, no exception
    assert opened == ["urn:b", "urn:a"]


def test_clear_items_sweeps_the_whole_id_range_and_forgets_targets(menu):
    menu.rebuild([_item("a"), _item("b")])
    # Something an earlier, untracked build left behind.
    menu.defs.addButtonDefinition(ITEM(7), "ghost", "")
    menu.defs.addButtonDefinition(EMPTY, "ghost", "")

    entry._clear_items()

    assert menu.defs.defs == {}
    assert menu.controls.ids() == []
    assert entry._item_targets == {}
    assert entry._owned_ids == set()
