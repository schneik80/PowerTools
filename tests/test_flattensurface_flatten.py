"""Tests for the Flatten Surface solver.

``flatten`` imports no ``adsk`` module, so it is loaded straight off disk and
exercised as plain Python. The cases that matter are the ones with an answer
known in advance:

* a developable surface (a rolled cylinder patch) must come back with
  essentially zero strain, because it can be flattened without stretching;
* a spherical cap cannot, and the sign of its strain is fixed by geometry -
  a dome's rim has more material to shed than its centre;
* a flat patch fed back through the solver must not move at all.

Those three pin the solver's correctness far better than any assertion about
its internals.
"""

import importlib.util
import math
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
_MODULE_PATH = REPO_ROOT / "commands" / "flattensurface" / "flatten.py"
_spec = importlib.util.spec_from_file_location("fs_flatten", _MODULE_PATH)
flatten = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(flatten)


def grid_mesh(rows, cols, point_at):
    """Build a triangulated grid mesh from a parametric point function.

    Args:
        rows: Number of samples in the first parameter.
        cols: Number of samples in the second parameter.
        point_at: Callable taking (i, j) and returning an (x, y, z) tuple.

    Returns:
        A (coords, triangles) pair in the shape :func:`weld_meshes` expects.
    """
    coords = []
    for i in range(rows):
        for j in range(cols):
            coords.append(point_at(i, j))
    triangles = []
    for i in range(rows - 1):
        for j in range(cols - 1):
            a = i * cols + j
            b = a + 1
            c = a + cols
            d = c + 1
            triangles.append((a, b, d))
            triangles.append((a, d, c))
    return coords, triangles


def flat_patch(rows=5, cols=5, step=1.0):
    """A plane patch in z = 0."""
    return grid_mesh(rows, cols, lambda i, j: (j * step, i * step, 0.0))


def cylinder_patch(rows=6, cols=9, radius=3.0, height=4.0, sweep=1.2):
    """A patch rolled onto a cylinder: curved, but developable."""

    def point(i, j):
        angle = -sweep / 2.0 + sweep * j / (cols - 1)
        return (
            radius * math.sin(angle),
            height * i / (rows - 1),
            radius * math.cos(angle),
        )

    return grid_mesh(rows, cols, point)


def sphere_cap(rows=6, cols=6, radius=5.0, extent=0.6):
    """A cap cut from a sphere: doubly curved, so it cannot flatten cleanly."""

    def point(i, j):
        u = -extent + 2.0 * extent * j / (cols - 1)
        v = -extent + 2.0 * extent * i / (rows - 1)
        rho = math.sqrt(u * u + v * v)
        if rho < 1e-12:
            return (0.0, 0.0, radius)
        theta = rho
        return (
            radius * math.sin(theta) * u / rho,
            radius * math.sin(theta) * v / rho,
            radius * math.cos(theta),
        )

    return grid_mesh(rows, cols, point)


def test_weld_merges_coincident_nodes_across_meshes():
    left = ([(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)], [(0, 1, 2)])
    right = ([(1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (1.0, 1.0, 0.0)], [(0, 2, 1)])

    verts, tris, source = flatten.weld_meshes([left, right])

    assert len(verts) == 4
    assert len(tris) == 2
    assert source == [0, 1]


def test_weld_drops_triangles_that_collapse():
    mesh = (
        [(0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (1.0, 0.0, 0.0)],
        [(0, 1, 2)],
    )

    verts, tris, _source = flatten.weld_meshes([mesh])

    assert len(verts) == 2
    assert tris == []


def test_weld_rejects_non_positive_tolerance():
    try:
        flatten.weld_meshes([flat_patch()], tol=0.0)
    except ValueError:
        return
    raise AssertionError("expected ValueError for a zero weld tolerance")


def test_split_islands_separates_disconnected_selections():
    left = flat_patch(3, 3)
    right_coords, right_tris = flat_patch(3, 3)
    shifted = ([(x + 50.0, y, z) for x, y, z in right_coords], right_tris)

    verts, tris, _source = flatten.weld_meshes([left, shifted])
    islands = flatten.split_islands(len(verts), tris)

    assert len(islands) == 2


def test_cg_solves_a_small_system():
    rows = [{0: 4.0, 1: 1.0}, {0: 1.0, 1: 3.0}]

    solution = flatten.solve_cg(rows, [1.0, 2.0])

    assert abs(solution[0] - 1.0 / 11.0) < 1e-9
    assert abs(solution[1] - 7.0 / 11.0) < 1e-9


def test_flat_patch_flattens_without_distortion():
    result = flatten.flatten_meshes([flat_patch()])

    assert result.stats.flipped == 0
    assert abs(result.stats.max_strain) < 1e-6
    assert abs(result.stats.min_strain) < 1e-6
    assert abs(result.stats.area_2d - result.stats.area_3d) < 1e-6


def test_cylinder_patch_is_developable_so_strain_stays_near_zero():
    result = flatten.flatten_meshes([cylinder_patch()])

    assert result.stats.flipped == 0
    assert result.stats.mean_abs_strain < 5e-3
    assert max(abs(value) for value in result.strain) < 1e-2


def test_cylinder_patch_preserves_area():
    result = flatten.flatten_meshes([cylinder_patch()])

    assert abs(result.stats.area_2d - result.stats.area_3d) < 1e-3


def test_sphere_cap_cannot_flatten_cleanly():
    result = flatten.flatten_meshes([sphere_cap()])

    # A dome has more surface near its rim than a disc of the same radius, so
    # flattening it has to move material: the rim and the centre cannot both
    # keep their size. Anything close to zero here means the solver is not
    # measuring distortion at all.
    assert result.stats.max_strain - result.stats.min_strain > 1e-3


def test_relaxation_reduces_area_distortion_on_a_sphere_cap():
    conformal = flatten.flatten_meshes([sphere_cap()], relax=False)
    relaxed = flatten.flatten_meshes([sphere_cap()], relax=True)

    assert relaxed.stats.mean_abs_strain <= conformal.stats.mean_abs_strain


def test_two_faces_weld_into_a_single_island():
    left = grid_mesh(4, 4, lambda i, j: (j * 1.0, i * 1.0, 0.0))
    right = grid_mesh(4, 4, lambda i, j: (3.0 + j * 1.0, i * 1.0, 0.0))

    result = flatten.flatten_meshes([left, right])

    assert result.stats.islands == 1
    assert result.seams, "the shared edge should be reported as a seam"


def test_seam_chain_follows_the_shared_edge():
    left = grid_mesh(4, 4, lambda i, j: (j * 1.0, i * 1.0, 0.0))
    right = grid_mesh(4, 4, lambda i, j: (3.0 + j * 1.0, i * 1.0, 0.0))
    verts, tris, source = flatten.weld_meshes([left, right])

    chains = flatten.seam_chains(tris, source)

    assert len(chains) == 1
    assert len(chains[0]) == 4
    # Every vertex on the seam is on the join line x == 3.
    for index in chains[0]:
        assert abs(verts[index][0] - 3.0) < 1e-9


def test_edges_meshed_at_different_densities_weld_only_where_nodes_coincide():
    # Fusion meshes each face separately, so a shared edge can arrive with a
    # different number of nodes on each side. Only coincident nodes weld, which
    # leaves the two faces joined at those points alone. The command guards
    # against this by capping the triangle side length so densities stay
    # comparable; this test pins what happens when they do not.
    dense = grid_mesh(5, 3, lambda i, j: (j * 1.5, i * 1.0, 0.0))
    sparse = grid_mesh(2, 3, lambda i, j: (3.0 + j * 1.5, i * 4.0, 0.0))

    verts, tris, _source = flatten.weld_meshes([dense, sparse])

    shared = [i for i, p in enumerate(verts) if abs(p[0] - 3.0) < 1e-9]
    # The dense side contributes five nodes on the join, the sparse side two,
    # and only the two corners land on top of each other.
    assert len(shared) == 5
    islands = flatten.split_islands(len(verts), tris)
    assert len(islands) == 1, "the corners still hold the two faces together"


def test_disconnected_islands_are_laid_out_without_overlapping():
    left = flat_patch(3, 3)
    right_coords, right_tris = flat_patch(3, 3)
    shifted = ([(x + 50.0, y, z) for x, y, z in right_coords], right_tris)

    result = flatten.flatten_meshes([left, shifted], island_gap=1.0)

    assert result.stats.islands == 2
    islands = flatten.split_islands(len(result.verts), result.tris)
    spans = []
    for triangle_indices in islands:
        members = {c for i in triangle_indices for c in result.tris[i]}
        xs = [result.uvs[i][0] for i in members]
        spans.append((min(xs), max(xs)))
    spans.sort()
    assert spans[0][1] <= spans[1][0] + 1e-9


def test_boundary_loop_of_a_grid_walks_its_perimeter():
    _coords, triangles = flat_patch(4, 4)
    loops = flatten.boundary_loops(triangles)

    assert len(loops) == 1
    # A 4x4 grid has 16 nodes, 4 of them interior.
    assert len(loops[0]) == 12


def test_boundary_loops_find_a_hole():
    coords, triangles = flat_patch(5, 5)
    # Drop the two triangles covering the middle square to punch a hole.
    centre = {(1 * 5 + 1), (1 * 5 + 2), (2 * 5 + 1), (2 * 5 + 2)}
    kept = [t for t in triangles if not set(t) <= centre]

    loops = flatten.boundary_loops(kept)

    assert len(loops) == 2
    assert sorted(len(loop) for loop in loops) == [4, 16]
    assert len(coords) == 25


def test_flatten_reports_outer_boundary_first():
    coords, triangles = flat_patch(5, 5)
    centre = {(1 * 5 + 1), (1 * 5 + 2), (2 * 5 + 1), (2 * 5 + 2)}
    kept = [t for t in triangles if not set(t) <= centre]

    result = flatten.flatten_meshes([(coords, kept)])

    assert len(result.boundary) == 2
    assert len(result.boundary[0]) == 16


def test_triangle_sigmas_report_a_known_scale():
    verts = [(0.0, 0.0, 0.0), (2.0, 0.0, 0.0), (0.0, 2.0, 0.0)]
    tris = [(0, 1, 2)]
    uvs = [(0.0, 0.0), (4.0, 0.0), (0.0, 4.0)]

    (sigma1, sigma2) = flatten.triangle_sigmas(verts, tris, uvs)[0]

    assert abs(sigma1 - 2.0) < 1e-9
    assert abs(sigma2 - 2.0) < 1e-9


def test_vertex_strain_reads_a_uniform_scale_as_stretch():
    verts = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)]
    tris = [(0, 1, 2)]
    uvs = [(0.0, 0.0), (1.1, 0.0), (0.0, 1.1)]
    sigmas = flatten.triangle_sigmas(verts, tris, uvs)

    strain, stats = flatten.vertex_strain(verts, tris, uvs, sigmas)

    assert all(abs(value - 0.1) < 1e-9 for value in strain)
    assert abs(stats.mean_abs_strain - 0.1) < 1e-9
    assert stats.flipped == 0


def test_vertex_strain_counts_inverted_triangles():
    verts = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)]
    tris = [(0, 1, 2)]
    uvs = [(0.0, 0.0), (0.0, 1.0), (1.0, 0.0)]
    sigmas = flatten.triangle_sigmas(verts, tris, uvs)

    _strain, stats = flatten.vertex_strain(verts, tris, uvs, sigmas)

    assert stats.flipped == 1


def test_colour_ramp_is_diverging_around_zero():
    neutral = flatten.strain_to_rgba(0.0, 0.05)
    shrink = flatten.strain_to_rgba(-0.05, 0.05)
    stretch = flatten.strain_to_rgba(0.05, 0.05)

    assert shrink[2] > shrink[0], "compression should read blue"
    assert stretch[0] > stretch[2], "stretch should read red"
    assert abs(neutral[0] - neutral[2]) < 10, "no distortion should read neutral"
    assert all(0 <= channel <= 255 for channel in neutral + shrink + stretch)


def test_colour_ramp_clamps_beyond_the_limit():
    assert flatten.strain_to_rgba(9.0, 0.05) == flatten.strain_to_rgba(0.05, 0.05)
    assert flatten.strain_to_rgba(-9.0, 0.05) == flatten.strain_to_rgba(-0.05, 0.05)


def test_colour_ramp_survives_a_zero_limit():
    assert flatten.strain_to_rgba(0.0, 0.0)[3] == 255


def test_strain_limit_trims_a_lone_outlier():
    values = [0.001] * 99 + [5.0]

    assert flatten.strain_limit(values, percentile=0.02) < 1.0


def test_strain_limit_is_symmetric():
    assert abs(flatten.strain_limit([-0.3, 0.0, 0.1], percentile=0.0) - 0.3) < 1e-12


def test_simplify_drops_collinear_points():
    points = [(float(i), 0.0) for i in range(10)]

    assert flatten.simplify_loop(points, 0.01) == [(0.0, 0.0), (9.0, 0.0)]


def test_simplify_keeps_a_corner():
    points = [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0), (2.0, 1.0), (2.0, 2.0)]

    kept = flatten.simplify_loop(points, 0.01)

    assert (2.0, 0.0) in kept
    assert len(kept) == 3


def test_simplify_respects_its_tolerance():
    points = [(0.0, 0.0), (1.0, 0.5), (2.0, 0.0)]

    assert len(flatten.simplify_loop(points, 0.1)) == 3
    assert len(flatten.simplify_loop(points, 1.0)) == 2


def test_simplify_never_reduces_a_loop_below_a_triangle():
    points = [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0), (3.0, 0.0)]

    kept = flatten.simplify_loop(points, 10.0, closed=True)

    assert len(kept) >= 3


def test_simplify_leaves_short_chains_alone():
    points = [(0.0, 0.0), (1.0, 1.0)]

    assert flatten.simplify_loop(points, 0.5) == points


def test_simplify_thins_a_real_boundary_substantially():
    result = flatten.flatten_meshes([sphere_cap(rows=12, cols=12)])
    loop = [result.uvs[i] for i in result.boundary[0]]
    size = max(uv[0] for uv in result.uvs) - min(uv[0] for uv in result.uvs)

    kept = flatten.simplify_loop(loop, size * 0.002, closed=True)

    assert 4 <= len(kept) < len(loop)


def test_empty_selection_returns_an_empty_result():
    result = flatten.flatten_meshes([])

    assert result.tris == []
    assert result.uvs == []
    assert result.stats.triangles == 0
