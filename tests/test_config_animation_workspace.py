# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.
"""Unit tests for the Animation workspace/tab/panel lookups in config.py.

Fusion publishes none of these IDs, so config pins the ones observed on a live
build and keeps a display-name fallback behind each. The pinned IDs are what
these tests lock down — the Animation environment is internally the *Publisher*
environment (``Publisher3DEnvironment`` / ``PublisherViewPanel``), which is the
detail that is easy to lose again — together with the fallback paths, which are
otherwise only exercised on a build nobody has.

The Fusion collections are stubbed: they only need ``itemById`` plus iteration,
which is all config uses.
"""

import importlib
from pathlib import Path
from types import SimpleNamespace

PT_PKG = Path(__file__).resolve().parent.parent.name
config = importlib.import_module(f"{PT_PKG}.config")

# The workspace list as logged on Fusion 2704.1.36, trimmed to the entries that
# matter here: the real Animation environment plus a couple of decoys.
LIVE_WORKSPACES = (
    ("FusionSolidEnvironment", "Design"),
    ("FusionRenderEnvironment", "Render"),
    ("Publisher3DEnvironment", "Animation"),
    ("CAMEnvironment", "Manufacture"),
)


class FakeCollection:
    """A Fusion-style collection: iterable, with ``itemById``."""

    def __init__(self, items):
        self._items = list(items)

    def __iter__(self):
        return iter(self._items)

    def itemById(self, item_id):  # noqa: N802 - mirrors the Fusion API name
        for item in self._items:
            if item.id == item_id:
                return item
        return None


def make_workspaces(pairs):
    return FakeCollection(
        [SimpleNamespace(id=ws_id, name=name) for ws_id, name in pairs]
    )


def make_tab(tab_id, name, panel_pairs):
    return SimpleNamespace(
        id=tab_id,
        name=name,
        toolbarPanels=FakeCollection(
            [SimpleNamespace(id=p_id, name=p_name) for p_id, p_name in panel_pairs]
        ),
    )


def use_workspaces(monkeypatch, workspaces):
    """Point config's ``adsk.core.Application.get()`` at a stub UI."""
    ui = SimpleNamespace(workspaces=workspaces)
    app = SimpleNamespace(userInterface=ui)
    monkeypatch.setattr(
        config,
        "adsk",
        SimpleNamespace(
            core=SimpleNamespace(Application=SimpleNamespace(get=lambda: app))
        ),
    )


def test_resolves_publisher_environment_by_id(monkeypatch) -> None:
    """The pinned ID wins: Animation is internally Publisher3DEnvironment."""
    use_workspaces(monkeypatch, make_workspaces(LIVE_WORKSPACES))
    assert config.resolve_animation_workspace_id() == "Publisher3DEnvironment"


def test_falls_back_to_workspace_named_animation(monkeypatch) -> None:
    """A build that renumbers the workspace is still found by display name."""
    renumbered = [
        pair
        if pair[0] != "Publisher3DEnvironment"
        else ("Publisher4DEnvironment", "Animation")
        for pair in LIVE_WORKSPACES
    ]
    use_workspaces(monkeypatch, make_workspaces(renumbered))
    assert config.resolve_animation_workspace_id() == "Publisher4DEnvironment"


def test_returns_none_without_an_animation_workspace(monkeypatch) -> None:
    """No Animation environment means None, so the command skips its UI."""
    without = [pair for pair in LIVE_WORKSPACES if pair[1] != "Animation"]
    use_workspaces(monkeypatch, make_workspaces(without))
    assert config.resolve_animation_workspace_id() is None


def test_finds_animation_tab_by_id() -> None:
    """The Animation tab is picked by ID, not by position."""
    animation = make_tab("Animation", "ANIMATION", [("PublisherViewPanel", "View")])
    workspace = SimpleNamespace(
        toolbarTabs=FakeCollection([make_tab("ToolsTab", "TOOLS", []), animation])
    )
    assert config._find_animation_tab(workspace) is animation


def test_finds_animation_tab_by_name_when_id_differs() -> None:
    """A renumbered tab is matched on its display name, case-insensitively."""
    animation = make_tab("AnimTab2", "ANIMATION", [])
    workspace = SimpleNamespace(
        toolbarTabs=FakeCollection([make_tab("ToolsTab", "TOOLS", []), animation])
    )
    assert config._find_animation_tab(workspace) is animation


def test_falls_back_to_the_tab_carrying_the_view_panel() -> None:
    """With tab ID and name both unrecognised, the View panel locates the tab."""
    carrier = make_tab("Xyz", "MOTION", [("SomeViewPanel", "View")])
    workspace = SimpleNamespace(
        toolbarTabs=FakeCollection([make_tab("ToolsTab", "TOOLS", []), carrier])
    )
    assert config._find_animation_tab(workspace) is carrier


def test_anchor_panel_id_prefers_the_pinned_id() -> None:
    """The anchor is PublisherViewPanel, so our panel lands before Publish."""
    tab = make_tab(
        "Animation",
        "ANIMATION",
        [
            ("3DStoryboardPanel", "Storyboard"),
            ("PublisherViewPanel", "View"),
            ("PublishVideoPanel", "Publish"),
        ],
    )
    assert config._anchor_panel_id(tab) == "PublisherViewPanel"


def test_anchor_panel_id_falls_back_to_the_view_name() -> None:
    """A renumbered View panel is still matched by display name."""
    tab = make_tab(
        "Animation",
        "ANIMATION",
        [("PublisherViewPanel2", "View"), ("PublishVideoPanel", "Publish")],
    )
    assert config._anchor_panel_id(tab) == "PublisherViewPanel2"


def test_anchor_panel_id_is_empty_when_nothing_matches() -> None:
    """No anchor means the panel is appended rather than skipped."""
    tab = make_tab("Animation", "ANIMATION", [("PublishVideoPanel", "Publish")])
    assert config._anchor_panel_id(tab) == ""
