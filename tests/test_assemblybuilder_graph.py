"""Unit tests for the Assembly Builder's Drawflow graph helpers.

``entry.py`` is imported under the ``adsk`` stub from ``conftest.py``; only the
``adsk``-free graph functions are exercised here. The graphs are built the way
Drawflow exports them: a ``node id -> node`` map where ``outputs`` /
``inputs`` carry ``connections`` of ``{"node": "<id>"}`` strings.

* ``test_blank_names_are_found_only_under_the_root`` -- the page binds the name
  field straight into ``data.name``, so a cleared field arrives as ``""`` and
  the key exists; the old ``dict.get`` default never applied and Fusion was
  asked to create a nameless component (review of #36 follow-up).
* ``test_shared_nodes_ignore_param_links`` -- a paramdoc link lands on the same
  input port as the structural parent, so counting raw parents would call every
  parameterised component shared.
"""

import importlib
from pathlib import Path

PT_PKG = Path(__file__).resolve().parent.parent.name
entry = importlib.import_module(f"{PT_PKG}.commands.assemblybuilder.entry")


def _node(kind, name, children=(), parents=(), cls="", extra=None):
    data = {"name": name}
    if extra:
        data.update(extra)
    return {
        "name": kind,
        "class": cls,
        "data": data,
        "inputs": {"input_1": {"connections": [{"node": str(p)} for p in parents]}},
        "outputs": {"output_1": {"connections": [{"node": str(c)} for c in children]}},
    }


def _graph(**nodes):
    return {str(k): v for k, v in nodes.items()}


def test_root_is_found_by_class_then_by_missing_inputs():
    by_class = _graph(
        **{
            "1": _node("root", "Top", children=[2], cls="is-root"),
            "2": _node("part", "Bolt", parents=[1]),
        }
    )
    assert entry.find_root_node_id(by_class) == 1

    no_class = _graph(
        **{
            "5": _node("paramdoc", "Params", children=[7]),
            "7": _node("assembly", "Top", children=[8], parents=[5]),
            "8": _node("part", "Bolt", parents=[7]),
        }
    )
    # 5 is a parameter source and never the root. 7's only parent is that
    # paramdoc, which is not structural, but the fallback counts raw input
    # connections, so nothing qualifies. The page always stamps the root with
    # `is-root`, which is why this limit of the fallback has not mattered.
    assert entry.find_root_node_id(no_class) is None


def test_blank_names_are_found_only_under_the_root():
    nodes = _graph(
        **{
            "1": _node("root", "Top", children=[2, 3], cls="is-root"),
            "2": _node("assembly", "", children=[4], parents=[1]),
            "3": _node("part", "   ", parents=[1]),
            "4": _node("part", "Bolt", parents=[2]),
            # Unreachable from the root: must not be reported.
            "9": _node("part", "", parents=[]),
            # Parameter sources are not components.
            "10": _node("paramdoc", "", children=[4]),
        }
    )
    assert entry.find_blank_name_nodes(nodes, 1) == [(2, "assembly"), (3, "part")]


def test_blank_names_handles_a_missing_name_key_and_shared_children():
    shared = _node("part", "", parents=[2, 3])
    nodes = _graph(
        **{
            "1": _node("root", "Top", children=[2, 3], cls="is-root"),
            "2": _node("assembly", "Left", children=[4], parents=[1]),
            "3": _node("assembly", "Right", children=[4], parents=[1]),
            "4": shared,
        }
    )
    del nodes["2"]["data"]["name"]
    # 2 has no name key at all; 4 is reached twice but reported once.
    assert entry.find_blank_name_nodes(nodes, 1) == [(2, "assembly"), (4, "part")]


def test_no_blank_names_returns_an_empty_list():
    nodes = _graph(
        **{
            "1": _node("root", "Top", children=[2], cls="is-root"),
            "2": _node("part", "Bolt", parents=[1]),
        }
    )
    assert entry.find_blank_name_nodes(nodes, 1) == []


def test_shared_nodes_ignore_param_links():
    nodes = _graph(
        **{
            "1": _node("root", "Top", children=[2, 3], cls="is-root"),
            "2": _node("assembly", "Left", children=[4], parents=[1]),
            "3": _node("assembly", "Right", children=[4], parents=[1]),
            "4": _node("part", "Bolt", parents=[2, 3, 5]),
            "5": _node("paramdoc", "Params", children=[4, 2]),
        }
    )
    assert entry.find_shared_nodes(nodes, 1) == {4}
    links = entry.collect_param_links(nodes)
    assert set(links) == {4, 2}
    assert links[4][0]["name"] == "paramdoc"
    assert entry.get_structural_child_ids(nodes, 1) == [2, 3]
    assert entry.get_structural_parent_ids(nodes, 4) == [2, 3]
