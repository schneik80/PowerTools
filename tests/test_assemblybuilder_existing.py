"""Unit tests for Assembly Builder's handling of components already in the design.

Assembly Builder used to refuse any document that already had child components,
which made the Assembly Palette's "Assembly Builder..." handoff a dead end: the
palette creates external components whose documents live only in memory until
the first save, and the Builder turned them away. Those occurrences are now
seeded into the graph as *locked* nodes -- shown so the hierarchy makes sense,
never created again, never re-parented.

These tests cover the pure logic: the launch predicate, the depth-first
snapshot that keys each occurrence by its index path, the reconciliation that
matches graph nodes back onto live occurrences at create time, and the shared
node detection that must ignore seeded nodes. ``entry`` is imported via the
``PowerTools.*`` scaffolding in ``conftest.py``.
"""

import importlib

import pytest

entry = importlib.import_module("PowerTools.commands.assemblybuilder.entry")


class FakeCollection:
    """Stand-in for an ObjectCollection exposing ``count`` and ``item(i)``."""

    def __init__(self, items=None):
        self._items = list(items or [])

    @property
    def count(self):
        return len(self._items)

    def item(self, index):
        return self._items[index]


class FakeDocument:
    """Stand-in for adsk.core.Document, carrying only a DataFile."""

    def __init__(self, data_file=None):
        self.dataFile = data_file


class FakeChildDesign:
    """Stand-in for the Design owned by an external component's document."""

    def __init__(self, intent, data_file=None):
        self.designIntent = intent
        self.parentDocument = FakeDocument(data_file)


class FakeComponent:
    """Stand-in for adsk.fusion.Component."""

    def __init__(self, name, intent, data_file=None):
        self.name = name
        self.parentDesign = FakeChildDesign(intent, data_file)


class FakeOccurrence:
    """Stand-in for adsk.fusion.Occurrence with a child collection."""

    def __init__(self, name, intent, data_file=None, children=None, referenced=True):
        self.component = FakeComponent(name, intent, data_file)
        self.childOccurrences = FakeCollection(children or [])
        self.isReferencedComponent = referenced


class FakeRootComponent:
    """Stand-in for the root component of the active design."""

    def __init__(self, occurrences=None, bodies=0, sketches=0):
        self.occurrences = FakeCollection(occurrences or [])
        self.bRepBodies = FakeCollection([object()] * bodies)
        self.sketches = FakeCollection([object()] * sketches)


class FakeDesign:
    """Stand-in for adsk.fusion.Design."""

    def __init__(self, root=None, intent=None):
        self.rootComponent = root or FakeRootComponent()
        self.designIntent = intent


# Intent constants resolve to distinct MagicMock attributes under the adsk stub
# in conftest.py; identity is all the code under test relies on.
PART = entry.INTENT_MAP["part"]
ASSEMBLY = entry.INTENT_MAP["assembly"]
HYBRID = entry.INTENT_MAP["hybrid"]


def _node(name, data=None, inputs=None, outputs=None):
    """Build one Drawflow node dict.

    Args:
        name: The node type ("root", "part", "assembly", "hybrid", "paramdoc").
        data: The node's data payload.
        inputs: Parent node ids feeding input_1.
        outputs: Child node ids fed from output_1.

    Returns:
        A node dict shaped like Drawflow's export.
    """
    in_conns = [{"node": str(i), "input": "output_1"} for i in inputs or []]
    out_conns = [{"node": str(o), "output": "input_1"} for o in outputs or []]
    return {
        "name": name,
        "class": "is-root" if name == "root" else "",
        "data": data or {},
        "inputs": {"input_1": {"connections": in_conns}},
        "outputs": {"output_1": {"connections": out_conns}},
    }


# ---------------------------------------------------------------------------
# _design_is_structure_only
# ---------------------------------------------------------------------------


def test_components_alone_do_not_block_the_launch():
    # Arrange: the shape the Assembly Palette leaves behind -- components, but
    # no geometry of the root's own.
    root = FakeRootComponent(occurrences=[FakeOccurrence("Bracket", PART)])
    design = FakeDesign(root)

    # Act / Assert
    assert entry._design_is_structure_only(design) is True
    assert entry._design_is_empty(design) is False


@pytest.mark.parametrize("bodies,sketches", [(1, 0), (0, 1), (2, 3)])
def test_root_geometry_blocks_the_launch(bodies, sketches):
    # Arrange
    design = FakeDesign(FakeRootComponent(bodies=bodies, sketches=sketches))

    # Act / Assert
    assert entry._design_is_structure_only(design) is False


# ---------------------------------------------------------------------------
# _snapshot_existing / _walk_existing
# ---------------------------------------------------------------------------


def test_snapshot_keys_each_occurrence_by_its_index_path():
    # Arrange: an assembly holding two parts, alongside a flat part.
    leaf_a = FakeOccurrence("Leaf A", PART)
    leaf_b = FakeOccurrence("Leaf B", PART)
    sub = FakeOccurrence("Sub", ASSEMBLY, children=[leaf_a, leaf_b])
    flat = FakeOccurrence("Bracket", PART)
    design = FakeDesign(FakeRootComponent(occurrences=[sub, flat]))

    # Act
    snapshot = entry._snapshot_existing(design)

    # Assert: depth-first, parents before their children.
    assert [e["path"] for e in snapshot] == [[0], [0, 0], [0, 1], [1]]
    assert [e["name"] for e in snapshot] == ["Sub", "Leaf A", "Leaf B", "Bracket"]
    assert [e["type"] for e in snapshot] == ["assembly", "part", "part", "part"]


def test_snapshot_marks_components_without_a_datafile_transient():
    # Arrange: one component still in memory, one already flushed to the cloud.
    root = FakeRootComponent(
        occurrences=[
            FakeOccurrence("Fresh", PART),
            FakeOccurrence("Saved", PART, data_file=object()),
        ]
    )

    # Act
    snapshot = entry._snapshot_existing(FakeDesign(root))

    # Assert
    assert [e["transient"] for e in snapshot] == [True, False]


def test_snapshot_does_not_descend_into_a_saved_referenced_assembly():
    # Arrange: a saved sub-assembly owns its own contents, and listing them
    # would flood the canvas with nodes this document cannot touch.
    buried = FakeOccurrence("Buried", PART)
    saved_sub = FakeOccurrence(
        "Saved Sub", ASSEMBLY, data_file=object(), children=[buried]
    )
    design = FakeDesign(FakeRootComponent(occurrences=[saved_sub]))

    # Act
    snapshot = entry._snapshot_existing(design)

    # Assert
    assert [e["name"] for e in snapshot] == ["Saved Sub"]


def test_snapshot_does_not_descend_into_a_part():
    # Arrange: a part node has no output port, so a child would be an orphan.
    child = FakeOccurrence("Hidden", PART)
    part = FakeOccurrence("Bracket", PART, children=[child])
    design = FakeDesign(FakeRootComponent(occurrences=[part]))

    # Act
    snapshot = entry._snapshot_existing(design)

    # Assert
    assert [e["name"] for e in snapshot] == ["Bracket"]


def test_snapshot_survives_an_occurrence_that_throws():
    # Arrange: Fusion property reads throw on detached objects.
    class Exploding:
        @property
        def component(self):
            raise RuntimeError("detached")

    root = FakeRootComponent(occurrences=[Exploding(), FakeOccurrence("Good", PART)])

    # Act
    snapshot = entry._snapshot_existing(FakeDesign(root))

    # Assert: the bad one is skipped, the good one still reported.
    assert [e["name"] for e in snapshot] == ["Good"]


# ---------------------------------------------------------------------------
# _root_node_type
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "intent,expected",
    [
        (HYBRID, "hybrid"),
        (ASSEMBLY, "assembly"),
        (PART, "assembly"),
        (None, "assembly"),
    ],
)
def test_root_node_type_never_reports_part(intent, expected):
    # Arrange / Act / Assert: the Builder only ever produces Assembly or Hybrid.
    assert entry._root_node_type(FakeDesign(intent=intent)) == expected


def test_root_node_type_without_a_design():
    assert entry._root_node_type(None) == "assembly"


# ---------------------------------------------------------------------------
# _resolve_existing_nodes
# ---------------------------------------------------------------------------


def _seeded_design():
    """Build a design with one assembly holding one part, plus a flat part.

    Returns:
        ``(design, sub_occurrence, leaf_occurrence, flat_occurrence)``.
    """
    leaf = FakeOccurrence("Leaf", PART)
    sub = FakeOccurrence("Sub", ASSEMBLY, children=[leaf])
    flat = FakeOccurrence("Bracket", PART)
    return FakeDesign(FakeRootComponent(occurrences=[sub, flat])), sub, leaf, flat


def test_resolve_matches_seeded_nodes_onto_live_occurrences():
    # Arrange
    design, sub, leaf, flat = _seeded_design()
    nodes = {
        "1": _node("root", {"name": "Doc"}, outputs=[2, 4]),
        "2": _node(
            "assembly", {"name": "Sub", "existingPath": [0]}, inputs=[1], outputs=[3]
        ),
        "3": _node("part", {"name": "Leaf", "existingPath": [0, 0]}, inputs=[2]),
        "4": _node("part", {"name": "Bracket", "existingPath": [1]}, inputs=[1]),
        "5": _node("part", {"name": "New Part"}, inputs=[2]),
    }

    # Act
    occurrences, ids, error = entry._resolve_existing_nodes(nodes, design)

    # Assert
    assert error == ""
    assert ids == {2, 3, 4}
    assert occurrences[2] is sub
    assert occurrences[3] is leaf
    assert occurrences[4] is flat
    assert 5 not in occurrences


def test_resolve_reports_a_renamed_component():
    # Arrange: the component was renamed in Fusion while the palette sat open.
    design, _sub, _leaf, _flat = _seeded_design()
    nodes = {
        "1": _node("root", {"name": "Doc"}, outputs=[2]),
        "2": _node("assembly", {"name": "Old Name", "existingPath": [0]}, inputs=[1]),
    }

    # Act
    occurrences, ids, error = entry._resolve_existing_nodes(nodes, design)

    # Assert
    assert error == entry._DESIGN_CHANGED_MSG
    assert occurrences == {}
    assert ids == set()


def test_resolve_reports_a_path_that_no_longer_exists():
    # Arrange: a component was deleted, so the recorded path leads nowhere.
    design, _sub, _leaf, _flat = _seeded_design()
    nodes = {
        "1": _node("root", {"name": "Doc"}, outputs=[2]),
        "2": _node("part", {"name": "Gone", "existingPath": [7]}, inputs=[1]),
    }

    # Act
    _occurrences, _ids, error = entry._resolve_existing_nodes(nodes, design)

    # Assert
    assert error == entry._DESIGN_CHANGED_MSG


def test_resolve_reports_a_malformed_path():
    # Arrange
    design, _sub, _leaf, _flat = _seeded_design()
    nodes = {"2": _node("part", {"name": "Bad", "existingPath": ["x"]})}

    # Act
    _occurrences, _ids, error = entry._resolve_existing_nodes(nodes, design)

    # Assert
    assert error == entry._DESIGN_CHANGED_MSG


def test_resolve_ignores_a_graph_with_no_seeded_nodes():
    # Arrange: the original flow -- an empty document, nothing to reconcile.
    nodes = {
        "1": _node("root", {"name": "Doc"}, outputs=[2]),
        "2": _node("part", {"name": "New Part"}, inputs=[1]),
    }

    # Act
    occurrences, ids, error = entry._resolve_existing_nodes(nodes, FakeDesign())

    # Assert
    assert (occurrences, ids, error) == ({}, set(), "")


# ---------------------------------------------------------------------------
# find_shared_nodes
# ---------------------------------------------------------------------------


def test_shared_detection_still_flags_a_genuinely_reused_node():
    # Arrange: node 4 hangs under both 2 and 3.
    nodes = {
        "1": _node("root", {"name": "Doc"}, outputs=[2, 3]),
        "2": _node("assembly", {"name": "A"}, inputs=[1], outputs=[4]),
        "3": _node("assembly", {"name": "B"}, inputs=[1], outputs=[4]),
        "4": _node("part", {"name": "Shared"}, inputs=[2, 3]),
    }

    # Act / Assert
    assert entry.find_shared_nodes(nodes, 1) == {4}
    assert entry.find_shared_nodes(nodes, 1, set()) == {4}


def test_seeded_nodes_are_never_counted_as_shared():
    # Arrange: a seeded node cannot gain a second parent, so counting it would
    # trip the save-required gate for a hierarchy the user never built.
    nodes = {
        "1": _node("root", {"name": "Doc"}, outputs=[2, 3]),
        "2": _node("assembly", {"name": "A"}, inputs=[1], outputs=[4]),
        "3": _node("assembly", {"name": "B"}, inputs=[1], outputs=[4]),
        "4": _node("part", {"name": "Seeded", "existingPath": [0]}, inputs=[2, 3]),
    }

    # Act / Assert
    assert entry.find_shared_nodes(nodes, 1, {4}) == set()


def test_a_param_link_into_a_seeded_node_is_not_a_second_parent():
    # Arrange: param-doc links land on the same input port as the parent.
    nodes = {
        "1": _node("root", {"name": "Doc"}, outputs=[2]),
        "2": _node("part", {"name": "Seeded", "existingPath": [0]}, inputs=[1, 3]),
        "3": _node("paramdoc", {"name": "Globals", "paramId": "x"}, outputs=[2]),
    }

    # Act / Assert
    assert entry.find_shared_nodes(nodes, 1) == set()
    assert entry.get_structural_parent_ids(nodes, 2) == [1]
