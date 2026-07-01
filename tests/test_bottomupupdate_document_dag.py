"""Unit tests for the prototype document-level DAG.

``commands/bottomupupdate/document_dag.py`` has no relative or ``adsk`` imports,
so it is loaded directly from its file path -- no Fusion scaffolding needed. A
fake component/occurrence pair and an injected resolver stand in for the Fusion
API: each fake carries a ``doc_id`` (``None`` for internal/unsaved geometry) and
a ``name``.

These tests pin down how the document graph differs from the component-name
order in ``entry.py``: multi-component documents collapse to one node, internal
components fold into their owner, diamonds appear once, and same-named distinct
documents stay distinct (with the name-projection caveat made explicit).
"""

import importlib.util
from pathlib import Path

_MODULE_PATH = (
    Path(__file__).resolve().parent.parent
    / "commands" / "bottomupupdate" / "document_dag.py"
)
_spec = importlib.util.spec_from_file_location("pt_document_dag", _MODULE_PATH)
document_dag = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(document_dag)


class FakeComponent:
    """Stand-in for an ``adsk.fusion.Component`` with an owning document id."""

    def __init__(self, name, doc_id, children=()):
        self.name = name
        self.doc_id = doc_id  # None => internal / no own document
        self._children = list(children)

    @property
    def occurrences(self):
        """Return one occurrence per direct child component."""
        return [FakeOccurrence(child) for child in self._children]


class FakeOccurrence:
    """Stand-in for an ``adsk.fusion.Occurrence``."""

    def __init__(self, component):
        self.component = component


def _resolver(component):
    """Map a fake component to (doc_id, name), or None when it has no document."""
    if component.doc_id is None:
        return None
    return component.doc_id, component.name


def _order(root):
    """Return bottom-up document records for ``root`` using the fake resolver."""
    return document_dag.document_bottom_up_order(root, _resolver)


def test_multi_component_document_collapses_to_one_entry():
    """Several components in one document produce a single ordered node."""
    # Arrange: document A holds two internal components; the root references A.
    a_internal = FakeComponent("A_internal", doc_id="A")
    a_root = FakeComponent("A_root", doc_id="A", children=(a_internal,))
    root = FakeComponent("Root", doc_id="R", children=(a_root,))

    # Act
    order = _order(root)

    # Assert: one entry for document A (the component graph would emit two).
    assert [record["doc_id"] for record in order] == ["A"]


def test_internal_component_without_document_folds_into_owner():
    """An occurrence with no own document attributes its edges to the owner."""
    # Arrange: document X owns an internal (doc-less) component that references W.
    w_root = FakeComponent("W", doc_id="W")
    x_internal = FakeComponent("X_internal", doc_id=None, children=(w_root,))
    x_root = FakeComponent("X", doc_id="X", children=(x_internal,))
    root = FakeComponent("Root", doc_id="R", children=(x_root,))

    # Act
    nodes, root_doc_id = document_dag.build_document_dag(root, _resolver)
    order_ids = [record["doc_id"] for record in _order(root)]

    # Assert: no None node; the edge is X -> W; W is saved before X.
    assert None not in nodes
    assert set(nodes) == {"R", "X", "W"}
    assert "W" in nodes["X"]["children"]
    assert order_ids.index("W") < order_ids.index("X")


def test_shared_document_diamond_emitted_once_before_parents():
    """A document referenced by two parents appears once, ahead of both."""
    # Arrange: root references X and Y; both reference the same document Z.
    z = FakeComponent("Z", doc_id="Z")
    x = FakeComponent("X", doc_id="X", children=(z,))
    y = FakeComponent("Y", doc_id="Y", children=(z,))
    root = FakeComponent("Root", doc_id="R", children=(x, y))

    # Act
    order_ids = [record["doc_id"] for record in _order(root)]

    # Assert
    assert order_ids.count("Z") == 1
    assert order_ids.index("Z") < order_ids.index("X")
    assert order_ids.index("Z") < order_ids.index("Y")


def test_same_named_distinct_documents_stay_distinct():
    """Two documents sharing a component name remain two graph nodes.

    This is the collision the component-name graph would silently merge. The
    id-keyed graph keeps them apart; the name projection, however, yields a
    duplicate name -- the exact caveat that keeps the loop from getting the fix
    for free until it consumes ids.
    """
    # Arrange: documents P and Q both expose a component named "Bracket".
    bracket_p = FakeComponent("Bracket", doc_id="P")
    bracket_q = FakeComponent("Bracket", doc_id="Q")
    root = FakeComponent("Root", doc_id="R", children=(bracket_p, bracket_q))

    # Act
    order = _order(root)
    names = document_dag.document_bottom_up_names(root, _resolver)

    # Assert: two distinct document nodes, but a collided name projection.
    assert {record["doc_id"] for record in order} == {"P", "Q"}
    assert names == ["Bracket", "Bracket"]


def test_cycle_in_document_graph_terminates():
    """A hand-built cyclic document graph sorts without infinite recursion."""
    # Arrange: document A <-> document B mutual reference.
    node_a = {"doc_id": "A", "name": "A", "children": {}}
    node_b = {"doc_id": "B", "name": "B", "children": {}}
    node_a["children"]["B"] = node_b
    node_b["children"]["A"] = node_a
    nodes = {"R": {"doc_id": "R", "name": "R", "children": {"A": node_a}}, "A": node_a, "B": node_b}

    # Act
    order = document_dag.sort_document_dag_bottom_up(nodes, "R")

    # Assert: terminates, root excluded, each other node once.
    assert sorted(record["doc_id"] for record in order) == ["A", "B"]
