"""Connectivity and traversal rules for Measure Path.

``pathgraph`` imports no ``adsk`` module, so it is loaded straight off disk and
exercised as plain Python. Everything the command decides about what counts as a
single deterministic chain is decided here, which is why these are the tests that
matter: the Fusion half only flattens topology into ``Seg`` records.

Three of these guard bugs that shipped in the first draft and produced a
plausible-looking wrong number rather than an error:

* the end selection's own length was dropped, because the walk stops on touching
  one of its endpoints (:func:`test_end_segment_length_is_counted`);
* Dijkstra considered only one of the two ways out of a start segment
  (:func:`test_shortest_tries_both_ends_of_a_start_segment`);
* a kind-restricted walk applied a seed or tail of the other kind, reporting a
  mixed chain as homogeneous (:func:`test_homogeneous_skips_restriction_the_tail_violates`).
"""

import importlib.util
import itertools
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
_MODULE_PATH = REPO_ROOT / "commands" / "measurepath" / "pathgraph.py"
_spec = importlib.util.spec_from_file_location("mp_pathgraph", _MODULE_PATH)
pathgraph = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pathgraph)

EDGE = pathgraph.KIND_EDGE
SKETCH = pathgraph.KIND_SKETCH
ORDER = pathgraph.HOMOGENEOUS_ORDER


def build(specs):
    """Build a graph from ``(key, point_a, point_b, length, kind)`` tuples.

    Welds the endpoints the way the command does, so node identity in a test is
    decided by coordinates rather than by hand-numbered indices.

    Args:
        specs: One tuple per segment.

    Returns:
        ``(graph, node_of)`` where ``node_of`` maps a point to its node index.
    """
    points = []
    for _, point_a, point_b, _, _ in specs:
        points.append(point_a)
        points.append(point_b)
    indices, _coords = pathgraph.weld(points)
    segs = [
        pathgraph.Seg(key, indices[2 * i], indices[2 * i + 1], length, kind)
        for i, (key, _, _, length, kind) in enumerate(specs)
    ]
    node_of = {}
    for position, point in enumerate(points):
        node_of[point] = indices[position]
    return pathgraph.build(segs), node_of


A = (0.0, 0.0, 0.0)
B = (1.0, 0.0, 0.0)
C = (2.0, 0.0, 0.0)
D = (3.0, 0.0, 0.0)

# A -1- B -2- C -4- D
CHAIN = (
    ("e1", A, B, 1.0, EDGE),
    ("e2", B, C, 2.0, EDGE),
    ("e3", C, D, 4.0, EDGE),
)


@pytest.fixture
def chain():
    return build(CHAIN)


E = (1.0, 1.0, 0.0)
F = (0.0, 1.0, 0.0)

# A unit square: A -q1- B -q2- E -q3- F -q4- back to A. A chain that comes back
# to the node it left is rare but reachable - pick a curve as Start and its own
# far endpoint as End - and traversal() has to keep its footing on one.
SQUARE = (
    ("q1", A, B, 1.0, EDGE),
    ("q2", B, E, 1.0, EDGE),
    ("q3", E, F, 1.0, EDGE),
    ("q4", F, A, 1.0, EDGE),
)


@pytest.fixture
def square():
    return build(SQUARE)


# --------------------------------------------------------------------------
# Welding
# --------------------------------------------------------------------------


def test_weld_merges_within_tolerance_and_splits_outside_it():
    tol = pathgraph.DEFAULT_WELD_TOL
    indices, coords = pathgraph.weld([A, (tol * 0.5, 0.0, 0.0), (tol * 10, 0.0, 0.0)])
    assert indices[0] == indices[1]
    assert indices[0] != indices[2]
    assert len(coords) == 2


def test_weld_merges_points_straddling_a_grid_cell_boundary():
    """The spatial hash must probe neighbouring cells, not just its own."""
    indices, _ = pathgraph.weld([(0.4999999, 0, 0), (0.5000001, 0, 0)], tol=1.0)
    assert indices[0] == indices[1]


def test_weld_rejects_a_non_positive_tolerance():
    with pytest.raises(ValueError):
        pathgraph.weld([A], tol=0.0)


def test_self_loop_is_not_a_branch_candidate():
    """A closed curve welds to one node and can never move a walk anywhere."""
    graph, node_of = build(
        (("loop", A, A, 6.28, SKETCH), ("s", A, B, 1.0, SKETCH)),
    )
    assert "loop" not in graph.segs
    result, how = pathgraph.resolve(graph, [node_of[A]], {node_of[B]}, ORDER)
    assert (how, result.reached, result.length) == ("direct", True, 1.0)


# --------------------------------------------------------------------------
# Deterministic walking
# --------------------------------------------------------------------------


def test_straight_chain_resolves_directly(chain):
    graph, node_of = chain
    result, how = pathgraph.resolve(graph, [node_of[A]], {node_of[D]}, ORDER)
    assert how == "direct"
    assert result.length == pytest.approx(7.0)
    assert [seg.key for seg in result.segs] == ["e1", "e2", "e3"]


def test_fork_with_two_reachable_ends_is_ambiguous():
    graph, node_of = build(
        (
            ("t", A, B, 1.0, EDGE),
            ("up", B, (2.0, 1.0, 0.0), 5.0, EDGE),
            ("down", B, (2.0, -1.0, 0.0), 9.0, EDGE),
        )
    )
    ends = {node_of[(2.0, 1.0, 0.0)], node_of[(2.0, -1.0, 0.0)]}
    result, how = pathgraph.resolve(graph, [node_of[A]], ends, ORDER)
    assert how == "ambiguous"
    assert result.length == pytest.approx(1.0)
    assert sorted(seg.key for seg in result.candidates) == ["down", "up"]


def test_fork_whose_other_arm_is_a_dead_end_needs_no_choice():
    """Pruning unreachable candidates is what stops needless prompting."""
    graph, node_of = build(
        (
            ("t", A, B, 1.0, EDGE),
            ("up", B, (2.0, 1.0, 0.0), 5.0, EDGE),
            ("down", B, (2.0, -1.0, 0.0), 9.0, EDGE),
        )
    )
    result, how = pathgraph.resolve(
        graph, [node_of[A]], {node_of[(2.0, 1.0, 0.0)]}, ORDER
    )
    assert (how, result.reached) == ("direct", True)
    assert result.length == pytest.approx(6.0)


def test_a_replayed_choice_steers_the_walk():
    graph, node_of = build(
        (
            ("t", A, B, 1.0, EDGE),
            ("up", B, (2.0, 1.0, 0.0), 5.0, EDGE),
            ("down", B, (2.0, -1.0, 0.0), 9.0, EDGE),
        )
    )
    ends = {node_of[(2.0, 1.0, 0.0)], node_of[(2.0, -1.0, 0.0)]}
    result, how = pathgraph.resolve(graph, [node_of[A]], ends, ORDER, choices=["down"])
    assert how == "chosen"
    assert [seg.key for seg in result.segs] == ["t", "down"]
    assert result.length == pytest.approx(10.0)


def test_disjoint_components_do_not_resolve(chain):
    graph, node_of = build(
        (("e1", A, B, 1.0, EDGE), ("far", (9.0, 9.0, 9.0), (9.0, 9.0, 8.0), 1.0, EDGE))
    )
    result, how = pathgraph.resolve(
        graph, [node_of[A]], {node_of[(9.0, 9.0, 9.0)]}, ORDER
    )
    assert (how, result.reached) == ("ambiguous", False)


# --------------------------------------------------------------------------
# Sketch / edge bridging and the homogeneity fallback
# --------------------------------------------------------------------------


def test_a_sketch_curve_bridges_to_an_edge_within_tolerance():
    near = (1.0 + pathgraph.DEFAULT_WELD_TOL * 0.5, 0.0, 0.0)
    graph, node_of = build((("s", A, B, 1.0, SKETCH), ("e", near, C, 1.0, EDGE)))
    result, _ = pathgraph.resolve(graph, [node_of[A]], {node_of[C]}, ORDER)
    assert result.reached
    assert result.length == pytest.approx(2.0)


def test_a_gap_wider_than_tolerance_does_not_bridge():
    graph, node_of = build(
        (("s", A, B, 1.0, SKETCH), ("e", (1.01, 0.0, 0.0), C, 1.0, EDGE))
    )
    result, _ = pathgraph.resolve(graph, [node_of[A]], {node_of[C]}, ORDER)
    assert not result.reached


def test_ambiguous_mixed_graph_falls_back_to_the_only_edge_chain():
    top = (0.0, 5.0, 0.0)
    graph, node_of = build(
        (
            ("edge", A, top, 5.0, EDGE),
            ("s1", A, (2.0, 2.0, 0.0), 3.0, SKETCH),
            ("s2", (2.0, 2.0, 0.0), top, 3.0, SKETCH),
            ("s3", A, (-2.0, 2.0, 0.0), 4.0, SKETCH),
            ("s4", (-2.0, 2.0, 0.0), top, 4.0, SKETCH),
        )
    )
    result, how = pathgraph.resolve(graph, [node_of[A]], {node_of[top]}, ORDER)
    assert how == "edges"
    assert [seg.key for seg in result.segs] == ["edge"]


def test_homogeneous_skips_restriction_the_tail_violates():
    """An edges-only chain cannot contain a sketch-curve end selection.

    Applying the restriction anyway reported a chain that silently omitted the
    end selection, which read as a valid total.
    """
    mid = (0.0, 5.0, 0.0)
    far = (0.0, 7.0, 0.0)
    graph, node_of = build(
        (
            ("edge", A, mid, 5.0, EDGE),
            ("s1", A, (2.0, 2.0, 0.0), 3.0, SKETCH),
            ("s2", (2.0, 2.0, 0.0), mid, 3.0, SKETCH),
            ("send", mid, far, 2.0, SKETCH),
        )
    )
    result, how = pathgraph.resolve(
        graph,
        [node_of[A]],
        {node_of[mid], node_of[far]},
        ORDER,
        tail=graph.segs["send"],
    )
    assert how == "sketch"
    assert "send" in [seg.key for seg in result.segs]


def test_a_seed_of_the_wrong_kind_fails_a_restricted_walk():
    graph, node_of = build((("s", A, B, 1.0, SKETCH), ("e", B, C, 1.0, EDGE)))
    result = pathgraph.walk(
        graph,
        node_of[A],
        {node_of[C]},
        kinds=frozenset({EDGE}),
        seed=graph.segs["s"],
    )
    assert not result.reached
    assert result.segs == []


# --------------------------------------------------------------------------
# Terminal selections contribute their own length
# --------------------------------------------------------------------------


def test_end_segment_length_is_counted(chain):
    """Picking an edge as the End must include that edge.

    The walk's targets are the end segment's two endpoints, so it finishes on
    touching one of them; without an explicit tail the segment was dropped from
    both the total and the breakdown.
    """
    graph, node_of = chain
    ends = {node_of[C], node_of[D]}
    result, _ = pathgraph.resolve(
        graph, [node_of[A]], ends, ORDER, tail=graph.segs["e3"]
    )
    assert result.length == pytest.approx(7.0)
    assert [seg.key for seg in result.segs] == ["e1", "e2", "e3"]


def test_start_segment_length_is_counted(chain):
    graph, node_of = chain
    seed = graph.segs["e1"]
    seeds = {node_of[A]: seed, node_of[B]: seed}
    result, _ = pathgraph.resolve(
        graph, [node_of[A], node_of[B]], {node_of[D]}, ORDER, seeds=seeds
    )
    assert result.length == pytest.approx(7.0)
    assert [seg.key for seg in result.segs] == ["e1", "e2", "e3"]


def test_a_segment_that_is_both_start_and_end_is_counted_once(chain):
    graph, node_of = chain
    seed = graph.segs["e1"]
    seeds = {node_of[A]: seed, node_of[B]: seed}
    result, _ = pathgraph.resolve(
        graph,
        [node_of[A], node_of[B]],
        {node_of[A], node_of[B]},
        ORDER,
        seeds=seeds,
        tail=seed,
    )
    assert result.length == pytest.approx(1.0)
    assert [seg.key for seg in result.segs] == ["e1"]


# --------------------------------------------------------------------------
# Shortest path
# --------------------------------------------------------------------------


def test_shortest_takes_the_cheap_arm_of_a_diamond():
    join = (5.0, 0.0, 0.0)
    graph, node_of = build(
        (
            ("long1", A, (1.0, 1.0, 0.0), 10.0, EDGE),
            ("long2", (1.0, 1.0, 0.0), join, 10.0, EDGE),
            ("short1", A, (1.0, -1.0, 0.0), 2.0, EDGE),
            ("short2", (1.0, -1.0, 0.0), join, 2.0, EDGE),
        )
    )
    segs, length = pathgraph.shortest(graph, [node_of[A]], {node_of[join]})
    assert length == pytest.approx(4.0)
    assert [seg.key for seg in segs] == ["short1", "short2"]


def test_shortest_tries_both_ends_of_a_start_segment():
    """Traversing a start segment can leave from either end, at the same cost.

    Considering only one of them took the 205 cm route over the 6 cm one.
    """
    graph, node_of = build(
        (
            ("mid", A, B, 5.0, EDGE),
            ("long1", B, (1.0, 9.0, 0.0), 100.0, EDGE),
            ("long2", (1.0, 9.0, 0.0), (9.0, 9.0, 0.0), 100.0, EDGE),
            ("short", A, (-1.0, 0.0, 0.0), 1.0, EDGE),
        )
    )
    segs, length = pathgraph.shortest(
        graph,
        [node_of[A], node_of[B]],
        {node_of[(-1.0, 0.0, 0.0)]},
        seed=graph.segs["mid"],
    )
    assert length == pytest.approx(6.0)
    assert sorted(seg.key for seg in segs) == ["mid", "short"]


def test_shortest_counts_seed_and_tail(chain):
    graph, node_of = chain
    segs, length = pathgraph.shortest(
        graph,
        [node_of[A], node_of[B]],
        {node_of[C], node_of[D]},
        seed=graph.segs["e1"],
        tail=graph.segs["e3"],
    )
    assert length == pytest.approx(7.0)
    assert [seg.key for seg in segs] == ["e1", "e2", "e3"]


def test_shortest_returns_nothing_when_unreachable():
    graph, node_of = build(
        (("e1", A, B, 1.0, EDGE), ("far", (9.0, 9.0, 9.0), (9.0, 9.0, 8.0), 1.0, EDGE))
    )
    segs, length = pathgraph.shortest(graph, [node_of[A]], {node_of[(9.0, 9.0, 9.0)]})
    assert segs is None
    assert length == 0.0


# --------------------------------------------------------------------------
# Chain terminals, used to place the Start / End labels
# --------------------------------------------------------------------------


def test_endpoints_finds_the_chain_terminals(chain):
    graph, node_of = chain
    segs = [graph.segs[key] for key in ("e1", "e2", "e3")]
    assert pathgraph.endpoints(segs, [node_of[A]]) == (node_of[A], node_of[D])


def test_endpoints_rejects_a_candidate_that_does_not_chain(chain):
    """A wrong origin must be rejected, not silently mis-chained."""
    graph, node_of = chain
    segs = [graph.segs[key] for key in ("e1", "e2", "e3")]
    assert pathgraph.endpoints(segs, [node_of[C], node_of[A]]) == (
        node_of[A],
        node_of[D],
    )
    assert pathgraph.endpoints(segs, [node_of[C]]) == (None, None)


def test_endpoints_of_an_empty_chain():
    assert pathgraph.endpoints([], [0]) == (None, None)


def test_endpoints_of_a_chain_that_doubles_back():
    """The terminus is not simply the furthest node, which is why it is walked."""
    corner = (2.0, 2.0, 0.0)
    back = (0.5, 0.0, 0.0)
    graph, node_of = build(
        (
            ("a", A, C, 2.0, EDGE),
            ("b", C, corner, 2.0, EDGE),
            ("c", corner, back, 2.5, EDGE),
        )
    )
    segs = [graph.segs[key] for key in ("a", "b", "c")]
    assert pathgraph.endpoints(segs, [node_of[A]]) == (node_of[A], node_of[back])


# --------------------------------------------------------------------------
# Traversal sense, used to point the per-segment direction cones
# --------------------------------------------------------------------------


def test_traversal_reports_the_node_each_segment_is_entered_from(chain):
    graph, node_of = chain
    segs = [graph.segs[key] for key in ("e1", "e2", "e3")]
    pairs = pathgraph.traversal(segs, [node_of[A]])
    assert [(seg.key, node) for seg, node in pairs] == [
        ("e1", node_of[A]),
        ("e2", node_of[B]),
        ("e3", node_of[C]),
    ]


def test_traversal_of_a_circuit_runs_all_the_way_round(square):
    """A circuit's origin and terminus are the same node, which must not stall it."""
    graph, node_of = square
    segs = [graph.segs[key] for key in ("q1", "q2", "q3", "q4")]
    assert [node for _seg, node in pathgraph.traversal(segs, [node_of[A]])] == [
        node_of[A],
        node_of[B],
        node_of[E],
        node_of[F],
    ]


def test_traversal_of_an_unchainable_list_is_empty(chain):
    """No sense at all beats a plausible wrong one drawn as arrows."""
    graph, node_of = chain
    segs = [graph.segs[key] for key in ("e1", "e2", "e3")]
    assert pathgraph.traversal(segs, [node_of[C]]) == []
    assert pathgraph.traversal([], [node_of[A]]) == []


# --------------------------------------------------------------------------
# The invariant the dialog depends on
# --------------------------------------------------------------------------


def test_total_always_equals_the_sum_of_the_breakdown():
    """The Length field and the Segments table are read from one chain.

    Brute-forced over every start, end, seed and tail combination on a mixed
    graph: the reported total must equal the sum of the rows, and no segment may
    appear twice. This is what stops a total that disagrees with its breakdown.
    """
    mid = (1.5, 3.0, 0.0)
    graph, _node_of = build(
        (
            ("e1", A, B, 1.0, EDGE),
            ("e2", B, C, 2.0, EDGE),
            ("e3", C, D, 4.0, EDGE),
            ("s1", A, mid, 8.0, SKETCH),
            ("s2", mid, D, 8.0, SKETCH),
        )
    )
    nodes = sorted(
        {seg.a for seg in graph.segs.values()} | {seg.b for seg in graph.segs.values()}
    )
    candidates = [None, *graph.segs.values()]
    checked = 0

    for origin, target in itertools.permutations(nodes, 2):
        for tail in candidates:
            for seed in candidates:
                if seed is not None and origin not in (seed.a, seed.b):
                    continue
                seeds = {origin: seed} if seed is not None else {}

                result, _how = pathgraph.resolve(
                    graph, [origin], {target}, ORDER, seeds=seeds, tail=tail
                )
                if result is not None:
                    checked += 1
                    assert result.length == pytest.approx(
                        sum(seg.length for seg in result.segs)
                    )
                    keys = [seg.key for seg in result.segs]
                    assert len(set(keys)) == len(keys)

                segs, length = pathgraph.shortest(
                    graph, [origin], {target}, seed=seed, tail=tail
                )
                if segs is not None:
                    checked += 1
                    assert length == pytest.approx(sum(seg.length for seg in segs))
                    keys = [seg.key for seg in segs]
                    assert len(set(keys)) == len(keys)

    assert checked > 200, f"expected broad coverage, only checked {checked}"
