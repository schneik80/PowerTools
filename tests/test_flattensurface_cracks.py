"""Tests for the two reasons a patch of planes and cylinders shows strain.

A plane and a cylinder are each developable, and joining them edge to edge
keeps them developable, so a shape built only from those should flatten with no
strain at all. Two separate things break that expectation, and they need very
different answers:

* neighbouring faces meshed differently along a shared edge leave the patch
  hinged rather than joined. That is a defect, it is repairable, and it is
  repaired here;
* three or more faces meeting at a point hold real curvature. No flattening can
  remove it, so the only honest response is to report it.

These pin both, and pin that the repair for the first never quietly disposes of
the second.
"""

import importlib.util
import math
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
_MODULE_PATH = REPO_ROOT / "commands" / "flattensurface" / "flatten.py"
_spec = importlib.util.spec_from_file_location("fs_flatten_cracks", _MODULE_PATH)
flatten = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(flatten)


def swept(profile, zs):
    """Sweep a 2D profile along z into a (coords, triangles) mesh."""
    coords = [(x, y, z) for z in zs for x, y in profile]
    width = len(profile)
    triangles = []
    for row in range(len(zs) - 1):
        for column in range(width - 1):
            a = row * width + column
            triangles.append((a, a + 1, a + width + 1))
            triangles.append((a, a + width + 1, a + width))
    return coords, triangles


def split_panel(left_rows, right_rows):
    """One flat rectangle as two faces, each sampled its own way.

    This is what independent per-face tessellation does to a shared edge: the
    finer face puts nodes partway along the coarser face's triangles, where
    welding cannot reach them.
    """

    def rows(count):
        return [k / (count - 1) for k in range(count)]

    return [
        swept([(0.0, 0.0), (0.5, 0.0), (1.0, 0.0)], rows(left_rows)),
        swept([(1.0, 0.0), (1.5, 0.0), (2.0, 0.0)], rows(right_rows)),
    ]


def stadium(z_flat=None, z_round=None):
    """An extruded rounded rectangle: two planes and two half cylinders."""
    fine = [0.0, 1.0, 2.0, 3.0, 4.0]
    z_flat = fine if z_flat is None else z_flat
    z_round = fine if z_round is None else z_round
    radius, length = 1.0, 3.0

    def arc(cx, cy, start, end, steps):
        return [
            (
                cx + radius * math.cos(start + (end - start) * k / steps),
                cy + radius * math.sin(start + (end - start) * k / steps),
            )
            for k in range(steps + 1)
        ]

    def line(p0, p1, steps):
        return [
            (p0[0] + (p1[0] - p0[0]) * k / steps, p0[1] + (p1[1] - p0[1]) * k / steps)
            for k in range(steps + 1)
        ]

    return [
        swept(line((0.0, -radius), (length, -radius), 6), z_flat),
        swept(arc(length, 0.0, -math.pi / 2, math.pi / 2, 10), z_round),
        swept(line((length, radius), (0.0, radius), 6), z_flat),
        swept(arc(0.0, 0.0, math.pi / 2, 3 * math.pi / 2, 10), z_round),
    ]


def box_corner(n=5):
    """Three planes meeting at one vertex: 3 x 90 degrees, not a full turn."""

    def quad(origin, u, v):
        coords = []
        for i in range(n + 1):
            for j in range(n + 1):
                s, t = i / n, j / n
                coords.append(tuple(origin[k] + u[k] * s + v[k] * t for k in range(3)))
        triangles = []
        for i in range(n):
            for j in range(n):
                a = i * (n + 1) + j
                triangles.append((a, a + 1, a + n + 2))
                triangles.append((a, a + n + 2, a + n + 1))
        return coords, triangles

    return [
        quad((0, 0, 0), (2, 0, 0), (0, 2, 0)),
        quad((0, 0, 0), (0, 2, 0), (0, 0, 2)),
        quad((0, 0, 0), (0, 0, 2), (2, 0, 0)),
    ]


def flat_grid(rows, cols, step=1.0):
    coords = [(j * step, i * step, 0.0) for i in range(rows) for j in range(cols)]
    triangles = []
    for i in range(rows - 1):
        for j in range(cols - 1):
            a = i * cols + j
            triangles.append((a, a + 1, a + cols + 1))
            triangles.append((a, a + cols + 1, a + cols))
    return coords, triangles


# ---------------------------------------------------------------------------
# The expectation itself
# ---------------------------------------------------------------------------
def test_planes_and_cylinders_joined_flatten_with_no_strain():
    result = flatten.flatten_meshes(stadium())

    assert result.stats.mean_abs_strain < 1e-6
    assert result.stats.bent_points == 0
    assert result.stats.cracks_stitched == 0


# ---------------------------------------------------------------------------
# Cracks: repairable
# ---------------------------------------------------------------------------
def test_unevenly_meshed_faces_leave_a_phantom_hole():
    # Welding joins the two faces at only the nodes that happen to coincide.
    # The rest of the shared edge stays a free rim on both sides, showing up as
    # a second boundary loop - which the sketch would draw as a hole that is not
    # in the model - and dragging the patch off disc topology altogether.
    verts, tris, _source = flatten.weld_meshes(split_panel(3, 5))

    assert len(flatten.boundary_loops(tris)) == 2
    assert flatten.euler_characteristic(len(verts), tris) == -1


def test_stitching_closes_the_phantom_hole():
    verts, tris, source = flatten.weld_meshes(split_panel(3, 5))

    tris, _source, stitched = flatten.stitch_cracks(verts, tris, source, 5e-3)

    assert stitched == 2
    assert len(flatten.boundary_loops(tris)) == 1
    assert flatten.euler_characteristic(len(verts), tris) == 1


def test_flattening_stitches_cracks_without_being_asked():
    result = flatten.flatten_meshes(split_panel(3, 5))

    assert result.stats.cracks_stitched == 2
    assert result.stats.mean_abs_strain < 1e-9
    assert len(result.boundary) == 1


def test_stitching_a_closed_tube_of_planes_and_cylinders():
    # The stadium is a closed tube, so this runs stitching and the seam cut
    # together. Unstitched, this patch flattens at about 14 percent strain.
    result = flatten.flatten_meshes(stadium(z_flat=[0.0, 2.0, 4.0]))

    assert result.stats.cracks_stitched == 8
    assert result.stats.mean_abs_strain < 1e-6
    assert result.stats.bent_points == 0


def test_stitching_preserves_area_and_triangle_sources():
    verts, tris, source = flatten.weld_meshes(split_panel(3, 5))
    before = sum(flatten._triangle_frame(*[verts[i] for i in t])[3] for t in tris)

    tris, source, _n = flatten.stitch_cracks(verts, tris, source, 5e-3)
    after = sum(flatten._triangle_frame(*[verts[i] for i in t])[3] for t in tris)

    assert abs(after - before) < 1e-12
    assert len(source) == len(tris)
    assert set(source) == {0, 1}


def test_stitching_leaves_a_sound_mesh_alone():
    verts, tris, source = flatten.weld_meshes(split_panel(5, 5))

    stitched_tris, stitched_source, count = flatten.stitch_cracks(
        verts, tris, source, 5e-3
    )

    assert count == 0
    assert stitched_tris == tris
    assert stitched_source == source


# ---------------------------------------------------------------------------
# Curvature: not repairable, so reported
# ---------------------------------------------------------------------------
def test_a_box_corner_holds_exactly_ninety_degrees_of_curvature():
    # Three faces meeting at a point enclose 270 degrees, so 90 are missing.
    # That shortfall is curvature no flattening can remove, which is why the
    # dialog has to say so rather than let it read as a defect.
    result = flatten.flatten_meshes(box_corner())

    assert result.stats.bent_points == 1
    assert abs(math.degrees(result.stats.worst_defect) - 90.0) < 1e-6
    assert result.stats.mean_abs_strain > 0.01


def test_real_curvature_is_reported_not_stitched_away():
    # The control on the repair: stitching must not quietly reshape the mesh
    # around a corner and make genuine curvature disappear.
    result = flatten.flatten_meshes(box_corner())

    assert result.stats.cracks_stitched == 0
    assert result.stats.bent_points == 1


def test_developable_shapes_report_no_curvature():
    for label, meshes in (
        ("stadium", stadium()),
        ("flat", [flat_grid(5, 5)]),
    ):
        verts, tris, _source = flatten.weld_meshes(meshes)
        defects = flatten.angle_defects(verts, tris)
        worst = max((abs(value) for value in defects.values()), default=0.0)
        assert math.degrees(worst) < 1e-6, label


def test_angle_defect_ignores_the_rim():
    # Boundary vertices are meant to fall short of a full turn; counting them
    # would report curvature on every flat patch there is.
    coords, triangles = flat_grid(4, 4)

    defects = flatten.angle_defects(coords, triangles)

    assert len(defects) == 4  # the interior of a 4x4 grid
    assert all(abs(value) < 1e-12 for value in defects.values())


# ---------------------------------------------------------------------------
# A hole is not an open end
# ---------------------------------------------------------------------------
def ring(rows=8, cols=32, inner=1.0, outer=3.0, wave=0.0, waves=3, dome=0.0):
    """An annulus, optionally formed so it no longer lies flat."""
    coords, triangles = [], []
    for i in range(rows):
        fraction = i / (rows - 1)
        radius = inner + (outer - inner) * fraction
        for j in range(cols):
            angle = 2.0 * math.pi * j / cols
            z = wave * math.sin(waves * angle) * fraction + dome * fraction * fraction
            coords.append((radius * math.cos(angle), radius * math.sin(angle), z))
    for i in range(rows - 1):
        for j in range(cols):
            a = i * cols + j
            b = i * cols + (j + 1) % cols
            triangles.append((a, b, b + cols))
            triangles.append((a, b + cols, a + cols))
    return coords, triangles


def open_tube(rows=10, cols=24, radius=2.0, height=6.0):
    coords, triangles = [], []
    for i in range(rows):
        for j in range(cols):
            angle = 2.0 * math.pi * j / cols
            coords.append(
                (
                    radius * math.cos(angle),
                    radius * math.sin(angle),
                    height * i / (rows - 1),
                )
            )
    for i in range(rows - 1):
        for j in range(cols):
            a = i * cols + j
            b = i * cols + (j + 1) % cols
            triangles.append((a, b, b + cols))
            triangles.append((a, b + cols, a + cols))
    return coords, triangles


def test_a_hole_rim_turns_through_a_full_circle():
    verts, tris, _source = flatten.weld_meshes([ring()])
    loops = flatten.boundary_loops(tris)

    turnings = [abs(flatten.boundary_turning(verts, tris, loop)) for loop in loops]

    assert len(turnings) == 2
    for turning in turnings:
        assert abs(turning - 2.0 * math.pi) < 0.2


def test_a_tube_end_barely_turns_at_all():
    # It is a geodesic: the surface carries straight on past it.
    verts, tris, _source = flatten.weld_meshes([open_tube()])
    loops = flatten.boundary_loops(tris)

    for loop in loops:
        assert abs(flatten.boundary_turning(verts, tris, loop)) < 0.2


def test_a_formed_ring_keeps_its_hole():
    # The failure this guards. A formed boss with a bore is an annulus exactly
    # as a tube is, and cutting it gained a little accuracy while unrolling the
    # pattern into a spiral - unusable, and not obviously wrong at a glance.
    result = flatten.flatten_meshes([ring(wave=0.6)])

    assert result.stats.seams_cut == 0
    assert len(result.boundary) == 2


def test_a_deeply_formed_ring_still_keeps_its_hole():
    # Deep enough that cutting would measurably reduce the strain, which is
    # exactly when the old rule gave the hole away.
    result = flatten.flatten_meshes([ring(wave=0.9, dome=0.5)])

    assert result.stats.seams_cut == 0
    assert len(result.boundary) == 2
    assert result.stats.mean_abs_strain > 0.005


def test_a_domed_ring_keeps_its_hole():
    result = flatten.flatten_meshes([ring(dome=0.8)])

    assert result.stats.seams_cut == 0
    assert len(result.boundary) == 2


def test_a_tube_is_still_cut():
    # The control: erring towards keeping holes must not stop a tube opening.
    result = flatten.flatten_meshes([open_tube()])

    assert result.stats.seams_cut == 1
    assert len(result.boundary) == 1
    assert result.stats.mean_abs_strain < 1e-6


def test_a_cone_wall_is_still_cut():
    coords, triangles = [], []
    rows, cols = 10, 24
    for i in range(rows):
        fraction = i / (rows - 1)
        radius = 1.0 + 2.0 * fraction
        for j in range(cols):
            angle = 2.0 * math.pi * j / cols
            coords.append(
                (radius * math.cos(angle), radius * math.sin(angle), 4.0 * fraction)
            )
    for i in range(rows - 1):
        for j in range(cols):
            a = i * cols + j
            b = i * cols + (j + 1) % cols
            triangles.append((a, b, b + cols))
            triangles.append((a, b + cols, a + cols))

    result = flatten.flatten_meshes([(coords, triangles)])

    assert result.stats.seams_cut == 1
    assert result.stats.mean_abs_strain < 1e-6


def test_rings_a_hole_needs_two_boundaries():
    # A disc has one boundary and is never a candidate for either treatment.
    verts, tris, _source = flatten.weld_meshes([flat_grid(5, 5)])

    assert flatten.rings_a_hole(verts, tris) is False
