"""Tests for recognising real geometry in a flattened outline.

A flat pattern is mostly made of things a CAD user expects to be real: a bolt
hole is a circle, a filleted corner is an arc, a machined edge is a line.
Emitting all of it as fitted splines is what a naive tracer does, and it is
worse to dimension, worse to machine from, and loses the design intent.

The other half of the job is knowing when to stop. A curve that is smooth but
not circular can always be covered by enough short arcs, and doing so produces
geometry nobody wants. These tests pin both directions.
"""

import importlib.util
import math
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
_MODULE_PATH = REPO_ROOT / "commands" / "flattensurface" / "flatten.py"
_spec = importlib.util.spec_from_file_location("fs_flatten_segments", _MODULE_PATH)
flatten = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(flatten)


def arc_points(cx, cy, radius, steps, start=0.0, end=2.0 * math.pi):
    return [
        (
            cx + radius * math.cos(start + (end - start) * k / steps),
            cy + radius * math.sin(start + (end - start) * k / steps),
        )
        for k in range(steps + 1)
    ]


def line_points(p0, p1, steps):
    return [
        (p0[0] + (p1[0] - p0[0]) * k / steps, p0[1] + (p1[1] - p0[1]) * k / steps)
        for k in range(steps + 1)
    ]


def kinds(segments):
    return [kind for kind, _points in segments]


# ---------------------------------------------------------------------------
# Fitting a circle
# ---------------------------------------------------------------------------
def test_a_circle_is_recovered_exactly():
    points = arc_points(3.0, -2.0, 0.5, 40)[:-1]

    cx, cy, radius = flatten.fit_circle(points)

    assert abs(cx - 3.0) < 1e-9
    assert abs(cy + 2.0) < 1e-9
    assert abs(radius - 0.5) < 1e-9


def test_a_circle_is_recovered_from_a_short_arc():
    points = arc_points(0.0, 0.0, 4.0, 8, 0.2, 0.9)

    cx, cy, radius = flatten.fit_circle(points)

    assert abs(cx) < 1e-6
    assert abs(cy) < 1e-6
    assert abs(radius - 4.0) < 1e-6


def test_a_straight_run_is_not_a_circle():
    # It fits one of enormous radius, and drawing that as an arc would be
    # wrong in a way no tolerance check would catch.
    assert flatten.fit_circle([(x * 0.5, 0.0) for x in range(9)]) is None


def test_a_circle_needs_three_points():
    assert flatten.fit_circle([(0.0, 0.0), (1.0, 1.0)]) is None


def test_circle_deviation_measures_the_worst_point():
    points = [(1.0, 0.0), (0.0, 1.0), (-1.0, 0.0), (0.0, 1.2)]

    assert abs(flatten.circle_deviation(points, 0.0, 0.0, 1.0) - 0.2) < 1e-12


# ---------------------------------------------------------------------------
# Real geometry is recognised
# ---------------------------------------------------------------------------
def test_a_hole_becomes_one_circle():
    points = arc_points(3.0, -2.0, 0.5, 40)[:-1]

    segments = flatten.segment_curve(points, 0.001, closed=True)

    assert kinds(segments) == ["circle"]


def test_a_rectangle_becomes_four_lines():
    corners = [(0.0, 0.0), (4.0, 0.0), (4.0, 2.0), (0.0, 2.0)]
    points = []
    for index, start in enumerate(corners):
        points += line_points(start, corners[(index + 1) % 4], 12)[:-1]

    segments = flatten.segment_curve(points, 0.001, closed=True)

    assert kinds(segments) == ["line"] * 4


def test_a_stadium_becomes_arcs_and_lines():
    # The shape this command is most often pointed at: an extruded profile with
    # a filleted end. Two arcs and two straight sides, not a blob of spline.
    radius, length = 1.0, 4.0
    points = arc_points(
        length, 0.0, radius, 20, -math.pi / 2, math.pi / 2
    ) + arc_points(0.0, 0.0, radius, 20, math.pi / 2, 3 * math.pi / 2)

    segments = flatten.segment_curve(points, 0.005, closed=True)

    assert kinds(segments) == ["arc", "line", "arc", "line"]


def test_a_single_straight_run_is_one_line():
    segments = flatten.segment_curve([(x * 0.5, 0.0) for x in range(9)], 0.001)

    assert kinds(segments) == ["line"]


def test_two_fillets_in_an_s_stay_arcs():
    # An ordinary S of two tangent fillets. Merging these would throw away real
    # geometry, so only longer runs of arcs are treated as an approximation.
    points = arc_points(0.0, 1.0, 1.0, 12, -math.pi / 2, 0.0) + arc_points(
        2.0, 0.0, 1.0, 12, math.pi, math.pi / 2
    )

    segments = flatten.segment_curve(points, 0.002)

    assert kinds(segments).count("arc") == 2
    assert "spline" not in kinds(segments)


# ---------------------------------------------------------------------------
# Knowing when to stop
# ---------------------------------------------------------------------------
def test_a_wavy_curve_stays_one_spline():
    # Every short chord of it fits a line within tolerance, so a greedy walk
    # would slice it into a string of tiny segments. It is one curve.
    points = [(k * 0.3, math.sin(k * 0.9) * 0.7) for k in range(20)]

    segments = flatten.segment_curve(points, 0.01)

    assert kinds(segments) == ["spline"]


def test_an_ellipse_stays_one_spline():
    # An ellipse can be covered by enough short arcs, each inside tolerance and
    # none of them the shape. A chain of them is worse geometry than one curve.
    points = [
        (3.0 * math.cos(2.0 * math.pi * k / 40), 1.2 * math.sin(2.0 * math.pi * k / 40))
        for k in range(40)
    ]

    segments = flatten.segment_curve(points, 0.005, closed=True)

    assert kinds(segments) == ["spline"]


def test_a_long_straight_edge_survives_being_sampled_twice():
    # A tessellator may leave a flat edge as a single long segment. It is real
    # geometry even though it covers only two points, which is why length is
    # tested as well as point count.
    points = arc_points(0.0, 0.0, 1.0, 20, math.pi / 2, 3 * math.pi / 2) + [(0.0, -1.0)]
    points.append((6.0, -1.0))
    points.append((6.0, 1.0))

    segments = flatten.segment_curve(points, 0.005)

    assert "line" in kinds(segments)


# ---------------------------------------------------------------------------
# Behaviour on the shapes the solver actually produces
# ---------------------------------------------------------------------------
def test_segments_cover_the_whole_chain_in_order():
    radius, length = 1.0, 4.0
    points = arc_points(
        length, 0.0, radius, 20, -math.pi / 2, math.pi / 2
    ) + arc_points(0.0, 0.0, radius, 20, math.pi / 2, 3 * math.pi / 2)

    segments = flatten.segment_curve(points, 0.005, closed=True)

    for before, after in zip(segments, segments[1:], strict=False):
        assert before[1][-1] == after[1][0]
    assert segments[0][1][0] == points[0]
    assert segments[-1][1][-1] == points[0]  # closed back onto itself


def test_every_segment_stays_within_tolerance():
    radius, length = 1.0, 4.0
    points = arc_points(
        length, 0.0, radius, 20, -math.pi / 2, math.pi / 2
    ) + arc_points(0.0, 0.0, radius, 20, math.pi / 2, 3 * math.pi / 2)
    tol = 0.005

    for kind, piece in flatten.segment_curve(points, tol, closed=True):
        if kind == "line":
            assert flatten.line_deviation(piece) <= tol
        elif kind in ("arc", "circle"):
            fit = flatten.fit_circle(piece)
            assert fit is not None
            assert flatten.circle_deviation(piece, *fit) <= tol


def test_a_degenerate_chain_yields_nothing():
    assert flatten.segment_curve([], 0.01) == []
    assert flatten.segment_curve([(0.0, 0.0)], 0.01) == []


def test_segmentation_is_quick_enough_for_a_dense_boundary():
    # The boundary of a fine mesh runs to a few hundred points, and this sits
    # in the commit path where the user is waiting.
    points = arc_points(0.0, 0.0, 5.0, 400)[:-1]

    segments = flatten.segment_curve(points, 0.01, closed=True)

    assert kinds(segments) == ["circle"]


def torus_patch(rows=26, cols=36, major=5.0, minor=1.5, usweep=1.2, vsweep=1.6):
    """A doubly curved section of a torus - the classic fillet surface."""
    coords, triangles = [], []
    for i in range(rows):
        v = -vsweep / 2.0 + vsweep * i / (rows - 1)
        for j in range(cols):
            u = -usweep / 2.0 + usweep * j / (cols - 1)
            ring = major + minor * math.cos(v)
            coords.append((ring * math.cos(u), ring * math.sin(u), minor * math.sin(v)))
    for i in range(rows - 1):
        for j in range(cols - 1):
            a = i * cols + j
            triangles.append((a, a + 1, a + cols + 1))
            triangles.append((a, a + cols + 1, a + cols))
    return coords, triangles


def outline_segments(meshes):
    """Segment the outer boundary the way the sketch writer does."""
    result = flatten.flatten_meshes(meshes)
    loop = [result.uvs[i] for i in result.boundary[0]]
    xs = [p[0] for p in loop]
    ys = [p[1] for p in loop]
    tol = max(max(xs) - min(xs), max(ys) - min(ys)) * 0.0015
    runs = flatten.split_at_corners(loop, closed=True)
    segments = []
    for run in runs:
        segments += flatten.segment_curve(run, tol, closed=(len(runs) == 1))
    return segments


def test_a_doubly_curved_patch_does_not_shatter_into_pieces():
    # A torus section has four boundary edges and no straight-and-circular
    # decomposition. Fitting primitives to the full tolerance chopped it into a
    # dozen chords that each happened to fit, and the outline came out faceted.
    segments = outline_segments([torus_patch()])

    assert len(segments) <= 6


def test_a_doubly_curved_outline_is_stable_across_mesh_density():
    # The worst symptom of fitting too eagerly was that refining the mesh made
    # the outline worse, because a finer chain offers more places to fit a
    # chord. The answer should barely move.
    counts = [
        len(outline_segments([torus_patch(rows, cols)]))
        for rows, cols in ((14, 20), (26, 36), (40, 56))
    ]

    assert max(counts) - min(counts) <= 1


def test_a_primitive_must_fit_far_better_than_tolerance():
    # The rule that separates the two cases: real geometry is exact, a chord
    # across a curve merely fits.
    curve = [(k * 0.25, (k * 0.25) ** 2 * 0.05) for k in range(24)]
    tol = 0.02

    for kind, piece in flatten.segment_curve(curve, tol):
        if kind == "line":
            assert flatten.line_deviation(piece) <= tol * flatten.PRIMITIVE_FIT_FRACTION


def test_geometry_that_really_is_exact_still_comes_through():
    # The control: the same tolerance, on a shape whose edges genuinely are
    # straight, still yields lines rather than splines.
    corners = [(0.0, 0.0), (4.0, 0.0), (4.0, 2.0), (0.0, 2.0)]
    points = []
    for index, start in enumerate(corners):
        points += line_points(start, corners[(index + 1) % 4], 12)[:-1]

    segments = flatten.segment_curve(points, 0.05, closed=True)

    assert kinds(segments) == ["line"] * 4
