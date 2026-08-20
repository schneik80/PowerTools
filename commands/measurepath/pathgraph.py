# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.
#
# Pure connectivity/traversal core for the Measure Path command. Deliberately
# free of any `adsk` import so it can be unit tested outside Fusion: entry.py
# flattens Fusion topology into Seg records keyed by opaque strings, and every
# decision about what constitutes a deterministic chain is made here.
#
# Coordinates arriving here are plain (x, y, z) tuples in centimetres, already
# resolved to root/world space by the caller.

import heapq
from dataclasses import dataclass, field

# Endpoints closer together than this (centimetres) are treated as the same
# node. 1e-4 cm == 1 micron: tight enough not to fuse genuinely distinct
# vertices, loose enough to bridge a sketch point projected onto a body edge.
DEFAULT_WELD_TOL = 1e-4

KIND_EDGE = "edge"
KIND_SKETCH = "sketch"

# The homogeneity fallback: when the mixed graph is ambiguous, try an
# all-model-edge chain and then an all-sketch-curve chain. Accepted only if
# exactly one of them resolves, so we never guess between two valid answers.
HOMOGENEOUS_ORDER = (
    ("edges", frozenset({KIND_EDGE})),
    ("sketch", frozenset({KIND_SKETCH})),
)


@dataclass(frozen=True)
class Seg:
    """One traversable curve: a model edge or a sketch curve.

    Attributes:
        key: Opaque stable identifier supplied by the caller.
        a: Node index of one end.
        b: Node index of the other end.
        length: Arc length in centimetres.
        kind: KIND_EDGE or KIND_SKETCH.
    """

    key: str
    a: int
    b: int
    length: float
    kind: str

    def other(self, node):
        """Return the end of this segment that is not *node*."""
        return self.b if node == self.a else self.a


@dataclass
class Graph:
    """Undirected multigraph of Segs, indexed by node."""

    segs: dict = field(default_factory=dict)
    adj: dict = field(default_factory=dict)

    def add(self, seg):
        # A segment whose two ends welded to the same node is a closed loop. It
        # can never move the walk anywhere, so it is dropped rather than left to
        # masquerade as a branch candidate at its own node.
        if seg.a == seg.b:
            return
        if seg.key in self.segs:
            return
        self.segs[seg.key] = seg
        self.adj.setdefault(seg.a, []).append(seg)
        self.adj.setdefault(seg.b, []).append(seg)

    def at(self, node):
        return self.adj.get(node, ())


@dataclass
class WalkResult:
    """Outcome of a deterministic walk.

    Attributes:
        segs: Segments traversed, in order.
        length: Cumulative arc length in centimetres.
        node: Node the walk stopped on.
        reached: True if *node* is one of the requested end nodes.
        candidates: Viable continuations when the walk stopped at a fork;
            empty when the walk reached the end or hit a dead end.
    """

    segs: list
    length: float
    node: int
    reached: bool
    candidates: list


def _cell(point, tol):
    return (
        int(round(point[0] / tol)),
        int(round(point[1] / tol)),
        int(round(point[2] / tol)),
    )


def weld(points, tol=DEFAULT_WELD_TOL):
    """Assign a node index to each point, merging coincident ones.

    Uses a spatial hash on a grid of cell size *tol*, probing the 27 cells
    around each point so two points either side of a cell boundary still merge.

    Args:
        points: Sequence of (x, y, z) tuples in centimetres.
        tol: Weld tolerance in centimetres.

    Returns:
        A list of node indices parallel to *points*, plus a list giving the
        representative coordinate of each node, as (indices, coords).
    """
    if tol <= 0.0:
        raise ValueError("weld tolerance must be positive")

    buckets = {}
    indices = []
    coords = []
    tol_sq = tol * tol

    for point in points:
        base = _cell(point, tol)
        found = None
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    for node in buckets.get(
                        (base[0] + dx, base[1] + dy, base[2] + dz), ()
                    ):
                        existing = coords[node]
                        ddx = existing[0] - point[0]
                        ddy = existing[1] - point[1]
                        ddz = existing[2] - point[2]
                        if ddx * ddx + ddy * ddy + ddz * ddz <= tol_sq:
                            found = node
                            break
                    if found is not None:
                        break
                if found is not None:
                    break
            if found is not None:
                break

        if found is None:
            found = len(coords)
            coords.append(point)
            buckets.setdefault(base, []).append(found)

        indices.append(found)

    return indices, coords


def build(segs):
    """Build a Graph from an iterable of Segs."""
    graph = Graph()
    for seg in segs:
        graph.add(seg)
    return graph


def _allowed(seg, kinds):
    return kinds is None or seg.kind in kinds


def endpoints(segs, start_candidates):
    """Return (origin, terminus) node indices for an ordered chain.

    Both walk() and shortest() return segments in traversal order, but neither
    records which node the chain left from - and for a chain whose first segment
    is the start selection, both of its ends are candidates. So each candidate is
    tried and the one that chains consistently all the way through wins, which
    also rejects a mis-ordered list rather than returning a plausible wrong node.

    Args:
        segs: Segments in traversal order.
        start_candidates: Nodes the chain might have started from.

    Returns:
        (origin, terminus), or (None, None) if no candidate chains cleanly.
    """
    if not segs:
        return None, None
    for candidate in start_candidates:
        node = candidate
        for seg in segs:
            if node != seg.a and node != seg.b:
                node = None
                break
            node = seg.other(node)
        if node is not None:
            return candidate, node
    return None, None


def can_reach(graph, start, targets, blocked, kinds=None, via=None):
    """Return True if any node in *targets* is reachable from *start*.

    Args:
        graph: The Graph to search.
        start: Node to start from.
        targets: Container of acceptable destination nodes.
        blocked: Set of segment keys that may not be used.
        kinds: Optional set of allowed Seg.kind values.
        via: Optional segment that must be taken as the first step.
    """
    if via is not None:
        if via.key in blocked or not _allowed(via, kinds):
            return False
        origin = via.other(start)
        if origin in targets:
            return True
        used = set(blocked)
        used.add(via.key)
        start = origin
    else:
        if start in targets:
            return True
        used = set(blocked)

    seen = {start}
    stack = [start]
    while stack:
        node = stack.pop()
        for seg in graph.at(node):
            if seg.key in used or not _allowed(seg, kinds):
                continue
            nxt = seg.other(node)
            if nxt in targets:
                return True
            if nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    return False


def _arrive(taken, total, node, tail):
    """Close out a successful walk, counting the end segment.

    When the end selection is a curve or edge, the walk's targets are its two
    endpoints, so it finishes the moment it touches one of them and the segment
    itself would never be counted. Appending it here keeps the end selection
    symmetric with the start seed: both contribute their full length, and both
    appear as a row in the breakdown.

    Skipped when the segment is already in the chain, which is what happens when
    the same curve is both the start and the end selection.
    """
    if tail is not None and all(seg.key != tail.key for seg in taken):
        if node == tail.a or node == tail.b:
            taken = taken + [tail]
            total += tail.length
            node = tail.other(node)
    return WalkResult(taken, total, node, True, [])


def walk(graph, start, ends, kinds=None, choices=None, seed=None, tail=None):
    """Walk deterministically from *start* until forced to stop.

    At each node the continuations are the incident segments minus those
    already used. Candidates that cannot reach an end node are pruned first, so
    a fork down a dead end is not reported as ambiguity and a fork with exactly
    one viable branch is followed silently. This is what makes "keep chaining
    until the next real branch point" precise.

    Args:
        graph: The Graph to walk.
        start: Node to start from.
        ends: Container of acceptable destination nodes.
        kinds: Optional set of allowed Seg.kind values.
        choices: Segment keys to prefer when a genuine fork is reached, applied
            in order. Used to replay the user's branch picks.
        seed: Optional segment that must be taken as the first step, used when
            the start selection is a curve rather than a point.
        tail: Optional segment to append on arrival, used when the end selection
            is a curve rather than a point.

    Returns:
        A WalkResult.
    """
    picks = list(choices or ())
    used = set()
    taken = []
    total = 0.0
    node = start

    if seed is not None:
        # A seed the kind restriction forbids cannot start a valid chain of that
        # kind; counting it anyway would report a mixed chain as homogeneous.
        if not _allowed(seed, kinds):
            return WalkResult([], 0.0, start, False, [])
        used.add(seed.key)
        taken.append(seed)
        total += seed.length
        node = seed.other(start)

    if node in ends:
        return _arrive(taken, total, node, tail)

    while True:
        options = [
            seg
            for seg in graph.at(node)
            if seg.key not in used and _allowed(seg, kinds)
        ]

        if not options:
            return WalkResult(taken, total, node, False, [])

        if len(options) > 1:
            viable = [
                seg
                for seg in options
                if can_reach(graph, node, ends, used, kinds, via=seg)
            ]
            # Every branch is a dead end: report the fork rather than silently
            # wandering, so the caller can say where the trail went cold.
            if not viable:
                return WalkResult(taken, total, node, False, [])
            options = viable

        if len(options) == 1:
            step = options[0]
        else:
            step = None
            while picks and step is None:
                wanted = picks.pop(0)
                step = next((s for s in options if s.key == wanted), None)
            if step is None:
                return WalkResult(taken, total, node, False, options)

        used.add(step.key)
        taken.append(step)
        total += step.length
        node = step.other(node)

        if node in ends:
            return _arrive(taken, total, node, tail)


def shortest(graph, starts, ends, kinds=None, seed=None, tail=None):
    """Dijkstra over arc length.

    Args:
        graph: The Graph to search.
        starts: Container of acceptable origin nodes.
        ends: Container of acceptable destination nodes.
        kinds: Optional set of allowed Seg.kind values.
        seed: Optional segment that must be taken as the first step.
        tail: Optional segment to append on arrival. Its length is the same
            whichever end node is reached, so adding it afterwards does not
            change which route is cheapest.

    Returns:
        (segs, length) for the cheapest route, or (None, 0.0) if unreachable.
    """
    origins = []
    if seed is not None:
        # Traversing the start segment can leave from either of its ends, and
        # both cost the same. Considering only one of them would miss the
        # cheaper continuation whenever the better route leaves the other way.
        for node in dict.fromkeys((seed.a, seed.b)):
            if node in starts:
                origins.append((seed.length, seed.other(node), [seed]))
        if not origins:
            return None, 0.0
    else:
        origins = [(0.0, start, []) for start in starts]

    best = {}
    heap = []
    for counter, (cost, node, path) in enumerate(origins):
        # The counter keeps heapq from ever comparing the list payloads.
        heap.append((cost, counter, node, path))
        best[node] = cost
    heapq.heapify(heap)
    tiebreak = len(heap)

    while heap:
        cost, _, node, path = heapq.heappop(heap)
        if cost > best.get(node, float("inf")):
            continue
        if node in ends and (path or node in starts):
            if tail is not None and all(seg.key != tail.key for seg in path):
                if node == tail.a or node == tail.b:
                    return path + [tail], cost + tail.length
            return path, cost

        for seg in graph.at(node):
            if not _allowed(seg, kinds):
                continue
            if any(seg.key == used.key for used in path):
                continue
            nxt = seg.other(node)
            nxt_cost = cost + seg.length
            if nxt_cost < best.get(nxt, float("inf")) - 1e-12:
                best[nxt] = nxt_cost
                heapq.heappush(heap, (nxt_cost, tiebreak, nxt, path + [seg]))
                tiebreak += 1

    return None, 0.0


def traversal(segs, start_candidates):
    """Return (seg, entry_node) pairs for an ordered chain, in traversal order.

    Seg is deliberately undirected, so the sense of each step exists only as the
    node the chain arrived from. Anything drawing a direction needs that node,
    and re-deriving it means chaining forward from the origin endpoints() found.

    Args:
        segs: Segments in traversal order.
        start_candidates: Nodes the chain might have started from.

    Returns:
        A list of (seg, entry_node) pairs, empty when the chain does not chain
        cleanly from any candidate - better than guessing a sense the caller
        would then draw backwards.
    """
    origin, _ = endpoints(segs, start_candidates)
    if origin is None:
        return []
    node = origin
    pairs = []
    for seg in segs:
        pairs.append((seg, node))
        node = seg.other(node)
    return pairs


def resolve(graph, starts, ends, kinds_order, choices=None, seeds=None, tail=None):
    """Try to find a chain, escalating through the disambiguation rules.

    Order: a deterministic walk over the whole graph; then the same walk
    restricted to each kind in *kinds_order* in turn, accepting it only if
    exactly one restriction succeeds; otherwise return the furthest partial
    walk so the caller can raise a manipulator at the fork.

    Args:
        graph: The Graph to search.
        starts: Candidate origin nodes.
        ends: Candidate destination nodes.
        kinds_order: Sequence of (label, kinds) pairs to try for the
            homogeneity fallback, e.g. HOMOGENEOUS_ORDER.
        choices: Branch picks to replay, in order.
        seeds: Optional {start_node: seed_segment} forcing the first step.
        tail: Optional segment to append on arrival, when the end selection is
            itself a curve or edge.

    Returns:
        (WalkResult, how) where *how* is "direct", "chosen", "ambiguous", or
        the label of whichever homogeneity restriction succeeded.
    """
    seeds = seeds or {}
    picks = list(choices or ())
    best_partial = None

    for start in starts:
        result = walk(graph, start, ends, None, picks, seeds.get(start), tail)
        if result.reached:
            return result, "chosen" if picks else "direct"
        if best_partial is None or result.length > best_partial.length:
            best_partial = result

    # Only fall back to homogeneity when the user has not already started
    # steering; once there are picks to replay, an ambiguous result means we
    # need the next pick, not a different rule.
    if not picks:
        homogeneous = []
        for label, kinds in kinds_order:
            # A restriction the end segment itself violates can never produce a
            # valid chain, so skip it rather than report a total that silently
            # drops the end selection.
            if tail is not None and not _allowed(tail, kinds):
                continue
            for start in starts:
                result = walk(graph, start, ends, kinds, None, seeds.get(start), tail)
                if result.reached:
                    homogeneous.append((result, label))
                    break
        if len(homogeneous) == 1:
            return homogeneous[0]

    return best_partial, "ambiguous"
