"""Unit tests for the DAG ordering in ``commands/bottomupupdate/entry.py``.

These tests target the two pure graph functions that decide the order in which
components are saved: ``traverse_assembly`` (builds the dependency tree) and
``sort_dag_bottom_up`` (post-order topological sort). Both operate on plain
objects, so lightweight fakes stand in for ``adsk.fusion`` components and
occurrences -- no Fusion runtime is required.

``entry`` is imported as ``PowerTools.commands.bottomupupdate.entry`` so its
``from ...lib``/``from ... import config`` relative imports resolve against the
pre-registered ``PowerTools`` package created in ``conftest.py``; the ``adsk.*``
API it touches at import time is served by the mock meta-path finder there.
"""

import importlib

entry = importlib.import_module("PowerTools.commands.bottomupupdate.entry")
traverse_assembly = entry.traverse_assembly
sort_dag_bottom_up = entry.sort_dag_bottom_up


class FakeComponent:
    """Minimal stand-in for an ``adsk.fusion.Component``.

    Exposes only the two members the DAG functions read: ``name`` and
    ``occurrences`` (each wrapping a child component).
    """

    def __init__(self, name: str, children: tuple["FakeComponent", ...] = ()):
        self.name = name
        self._children = list(children)

    @property
    def occurrences(self) -> list["FakeOccurrence"]:
        """Return one occurrence per direct child component."""
        return [FakeOccurrence(child) for child in self._children]


class FakeOccurrence:
    """Minimal stand-in for an ``adsk.fusion.Occurrence``."""

    def __init__(self, component: FakeComponent):
        self.component = component


def _order_of(root: FakeComponent) -> list[str]:
    """Build the tree from ``root`` and return the bottom-up name order."""
    assembly_dict: dict = {}
    traverse_assembly(root, assembly_dict)
    return sort_dag_bottom_up(assembly_dict)


def test_children_precede_parents_in_simple_tree():
    """Every child is saved before the parent that references it."""
    # Arrange: Bracket -> {Bushing, Pin}; Frame is a leaf sibling.
    bushing = FakeComponent("Bushing")
    pin = FakeComponent("Pin")
    bracket = FakeComponent("Bracket", (bushing, pin))
    frame = FakeComponent("Frame")
    root = FakeComponent("Root", (bracket, frame))

    # Act
    order = _order_of(root)

    # Assert: post-order, children before parent, siblings in traversal order.
    assert order == ["Bushing", "Pin", "Bracket", "Frame"]


def test_shared_subassembly_emitted_once_before_all_parents():
    """A diamond dependency appears exactly once, ahead of every parent."""
    # Arrange: both A and B reference the same shared leaf S.
    shared = FakeComponent("Shared")
    branch_a = FakeComponent("A", (shared,))
    branch_b = FakeComponent("B", (shared,))
    root = FakeComponent("Root", (branch_a, branch_b))

    # Act
    order = _order_of(root)

    # Assert: no duplicate, and the shared part precedes both consumers.
    assert order.count("Shared") == 1
    assert order.index("Shared") < order.index("A")
    assert order.index("Shared") < order.index("B")


def test_deep_shared_chain_keeps_dependency_order():
    """Nested diamonds still place every dependency before its dependents."""
    # Arrange: leaf feeds mid1 and mid2; both feed top1; top1 and leaf feed top2.
    leaf = FakeComponent("Leaf")
    mid1 = FakeComponent("Mid1", (leaf,))
    mid2 = FakeComponent("Mid2", (leaf,))
    top1 = FakeComponent("Top1", (mid1, mid2))
    top2 = FakeComponent("Top2", (top1, leaf))
    root = FakeComponent("Root", (top1, top2))

    # Act
    order = _order_of(root)

    # Assert: each name unique and every edge respected (dep before dependent).
    assert len(order) == len(set(order))
    edges = [
        ("Leaf", "Mid1"),
        ("Leaf", "Mid2"),
        ("Mid1", "Top1"),
        ("Mid2", "Top1"),
        ("Top1", "Top2"),
        ("Leaf", "Top2"),
    ]
    for dependency, dependent in edges:
        assert order.index(dependency) < order.index(dependent)


def test_cycle_is_broken_instead_of_recursing_forever():
    """A malformed cyclic graph terminates and emits each node once.

    ``traverse_assembly`` cannot produce a cycle, but the sort must still
    degrade gracefully if handed one, so the guard is exercised directly on
    hand-built nodes that reference each other.
    """
    # Arrange: node A <-> node B mutual reference.
    node_a = {"component": FakeComponent("A"), "children": {}}
    node_b = {"component": FakeComponent("B"), "children": {}}
    node_a["children"]["B"] = node_b
    node_b["children"]["A"] = node_a

    # Act
    order = sort_dag_bottom_up({"A": node_a})

    # Assert: it returns (no RecursionError) with each node exactly once.
    assert sorted(order) == ["A", "B"]
