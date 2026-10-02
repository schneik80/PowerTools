"""Which workspace each electronics Power Tools panel goes on.

The workspaces below are the ones Fusion reported on ADSKMVG91G2F5W,
pre-production 2706.0.116, 2026-10-02 -- including the misspelled
``...Environement`` ids and the "PCB" workspace, which shares the 3D PCB's
``DesignProductType`` and must not be mistaken for it.
"""

from types import SimpleNamespace as NS

from PowerTools.commands import _electronics_panels as ep

LIVE = [
    NS(id="FusionSolidEnvironment", name="DESIGN", productType="DesignProductType"),
    NS(id="PCBEnvironment", name="PCB", productType="DesignProductType"),
    NS(id="PCB3DEnvironment", name="3D PCB", productType="DesignProductType"),
    NS(
        id="PCBDesignEnvironement",
        name="Electronics Design",
        productType="ElectronProjectDocProductType",
    ),
    NS(
        id="SchEditorEnvironement",
        name="Schematic Editor",
        productType="ElectronSchDocProductType",
    ),
    NS(
        id="BoardLayoutEnvironement",
        name="PCB Editor",
        productType="ElectronPcbDocProductType",
    ),
]

PLACE = {p.key: p for p in ep.PLACES}


def test_every_place_resolves_on_the_live_workspace_list():
    picked = {key: ep.pick_workspace(LIVE, place).id for key, place in PLACE.items()}
    assert picked == {
        "project": "PCBDesignEnvironement",
        "schematic": "SchEditorEnvironement",
        "board": "BoardLayoutEnvironement",
        "pcb3d": "PCB3DEnvironment",
    }


def test_product_type_wins_when_the_id_is_renamed():
    renamed = [
        NS(id="SchEditorEnvironment", name="X", productType="ElectronSchDocProductType")
    ]
    assert ep.pick_workspace(renamed, PLACE["schematic"]) is renamed[0]


def test_display_name_is_the_last_resort_for_the_3d_pcb():
    renamed = [NS(id="Pcb3dEnv", name="3d pcb", productType="DesignProductType")]
    assert ep.pick_workspace(renamed, PLACE["pcb3d"]) is renamed[0]


def test_nothing_matches_on_a_build_without_electronics():
    assert ep.pick_workspace(LIVE[:2], PLACE["pcb3d"]) is None
    assert ep.pick_workspace([], PLACE["board"]) is None


def test_the_project_panel_sits_on_the_workspace_not_a_tab():
    assert PLACE["project"].tab_ids == ()
    assert all(PLACE[k].tab_ids for k in ("schematic", "board", "pcb3d"))


def test_a_workspace_whose_properties_raise_is_skipped():
    class Raises:
        def __getattr__(self, name):
            raise RuntimeError("adapter")

    assert ep.pick_workspace([Raises(), *LIVE], PLACE["board"]).id == (
        "BoardLayoutEnvironement"
    )
