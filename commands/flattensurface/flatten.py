# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.
#
# Pure flattening core for the Flatten Surface command. Deliberately free of any
# `adsk` import so it can be unit tested outside Fusion: entry.py tessellates the
# selected faces into plain coordinate/index tuples, calls flatten_meshes(), and
# then only draws and writes what comes back.
#
# Coordinates arriving here are (x, y, z) tuples in centimetres, already resolved
# to root/world space by the caller. Everything returned is centimetres too.
#
# The pipeline is the standard one for fabrication flattening: weld the selected
# faces into one patch, lay it out with a least-squares conformal map (LSCM), then
# relax that layout as-rigid-as-possible (ARAP) so the error is spread between
# angle and area instead of piling up in area alone. Distortion is read back from
# the singular values of each triangle's 3D-to-2D Jacobian. Background, sources
# and the algorithm survey behind these choices: docs/dev/Flatten Surface
# research.md.

import math
from dataclasses import dataclass, field

# Mesh nodes closer together than this (centimetres) are the same vertex. Fusion
# tessellates each face independently, so the shared edge between two selected
# faces arrives as two coincident rows of nodes; welding them is what turns a
# selection into a single connected patch rather than a pile of loose triangles.
DEFAULT_WELD_TOL = 1e-4

# Cotangent weights go negative on obtuse triangles, which can make the ARAP
# system indefinite and stall the solver. Clamping to a small positive floor
# keeps it symmetric positive definite at the cost of a little accuracy on badly
# shaped triangles.
MIN_COTAN = 1e-3

DEFAULT_ARAP_ITERATIONS = 10
DEFAULT_CG_TOLERANCE = 1e-10
DEFAULT_ISLAND_GAP = 0.5

# Turn above which a boundary vertex counts as a corner rather than a point on
# a curve. Successive segments of a tessellated smooth edge turn by a few
# degrees; anything approaching this is a real corner of the pattern.
DEFAULT_CORNER_DEGREES = 32.0

# Mean strain above which a non-disc patch is worth trying to slit open. Below
# it the patch is already lying flat well enough that a cut would only add a
# gratuitous slit - a flat washer is the case that matters here.
CUT_WORTH_TRYING = 0.005

# Angle defect above which an interior vertex counts as a genuine corner. A
# tessellated smooth surface lands within rounding of zero; a place where three
# faces meet is tens of degrees out.
MIN_DEFECT_DEGREES = 0.5

# Narrowest colour range worth drawing, as strain. The scale otherwise
# stretches to fit whatever is in the data, so a surface that flattens
# exactly - every value a rounding artefact around 1e-7 - would be painted
# in full-saturation red and blue. Nothing below a tenth of a percent means
# anything to any material, so that is where the scale stops shrinking.
MIN_STRAIN_LIMIT = 0.001

# A straight run fits a circle too, one of enormous radius. Any fit whose
# radius exceeds this many times the run's own span is treated as the line it
# really is, which keeps a flat edge from being drawn as a vast shallow arc.
MAX_ARC_RADIUS_SPANS = 1000.0

# What it takes for a fitted line or arc to count as part of the shape rather
# than a chord across a smooth curve: either it covers this many chain points,
# or it reaches this many times the typical spacing around it. Without the
# second test a straight edge the tessellator left as one long segment would
# be mistaken for a sliver.
MIN_PRIMITIVE_POINTS = 4
MIN_PRIMITIVE_SPANS = 3.0

# Arcs in an unbroken row above this many are approximating something that is
# not circular at all, and become one spline instead. Two in a row is left
# alone, being an ordinary S of two fillets.
MAX_CHAINED_ARCS = 3

# Passes allowed when stitching cracks. Splitting one triangle can expose the
# next T-junction along, so it takes a few rounds to settle; the cap is only
# there so a pathological mesh cannot loop forever.
MAX_STITCH_PASSES = 6

# Crack stitching works to a looser tolerance than welding. Two faces meeting
# along a straight edge agree exactly, but along an arc each approximates the
# curve its own way, so their points sit near the other's chords rather than
# on them.
_STITCH_TOL_FACTOR = 50.0

# Triangles smaller than this (cm^2) carry no usable frame, so they are skipped
# when assembling the solver systems and reported as degenerate instead.
MIN_TRIANGLE_AREA = 1e-12

# Moreland's smooth cool-warm diverging map, sampled at nine stops. Blue is
# compression, near-white is no distortion, red is stretch - the same convention
# the Boundary First Flattening viewer uses. Deliberately not a rainbow ramp:
# non-monotonic lightness invents edges that are not in the data.
_COOLWARM = (
    (0.000, (59, 76, 192)),
    (0.125, (98, 130, 234)),
    (0.250, (141, 176, 254)),
    (0.375, (184, 208, 249)),
    (0.500, (221, 221, 221)),
    (0.625, (245, 196, 173)),
    (0.750, (244, 154, 123)),
    (0.875, (222, 96, 77)),
    (1.000, (180, 4, 38)),
)


@dataclass
class FlattenStats:
    """Summary of one flattening run, for the dialog and the report.

    Attributes:
        vertices: Welded vertex count.
        triangles: Triangle count.
        islands: Number of disconnected patches laid out side by side.
        area_3d: Total surface area in cm^2.
        area_2d: Total flattened area in cm^2.
        min_strain: Most negative signed area strain (compression).
        min_vertex: Vertex index carrying *min_strain*.
        max_strain: Most positive signed area strain (stretch).
        max_vertex: Vertex index carrying *max_strain*.
        mean_abs_strain: Area-weighted mean of absolute strain.
        flipped: Triangles whose 2D winding is inverted; non-zero means the
            layout folded over itself and the pattern is not trustworthy.
        degenerate: Triangles too small to measure, skipped by the solver.
        seams_cut: Patches slit open to make them flattenable, as a closed tube
            has to be.
        cracks_stitched: Gaps closed where neighbouring faces were tessellated
            differently along a shared edge.
        bent_points: Interior vertices holding real curvature, where three or
            more faces meet. Any of these means some distortion is unavoidable.
        worst_defect: Largest angle defect at any interior vertex, in radians.
    """

    vertices: int = 0
    triangles: int = 0
    islands: int = 0
    seams_cut: int = 0
    cracks_stitched: int = 0
    bent_points: int = 0
    worst_defect: float = 0.0
    area_3d: float = 0.0
    area_2d: float = 0.0
    min_strain: float = 0.0
    min_vertex: int = -1
    max_strain: float = 0.0
    max_vertex: int = -1
    mean_abs_strain: float = 0.0
    flipped: int = 0
    degenerate: int = 0


@dataclass
class FlattenResult:
    """A flattened patch and everything drawn or reported from it.

    Attributes:
        verts: Welded 3D coordinates in centimetres.
        tris: Triangles as (i, j, k) index tuples into *verts*.
        uvs: Flattened 2D coordinates in centimetres, parallel to *verts*.
        strain: Signed area strain per vertex, parallel to *verts*.
        boundary: Boundary loops as vertex index lists, outer loop first and
            hole loops after it.
        seams: Interior edges between two different selected faces, chained
            into polylines of vertex indices.
        stats: Summary of the run.
    """

    verts: list = field(default_factory=list)
    tris: list = field(default_factory=list)
    uvs: list = field(default_factory=list)
    strain: list = field(default_factory=list)
    boundary: list = field(default_factory=list)
    seams: list = field(default_factory=list)
    stats: FlattenStats = field(default_factory=FlattenStats)


def _cell(point: tuple[float, float, float], tol: float) -> tuple[int, int, int]:
    return (
        int(round(point[0] / tol)),
        int(round(point[1] / tol)),
        int(round(point[2] / tol)),
    )


def weld_meshes(
    meshes: list[tuple[list, list]], tol: float = DEFAULT_WELD_TOL
) -> tuple[list, list, list]:
    """Merge per-face meshes into one vertex-shared mesh.

    Uses a spatial hash on a grid of cell size *tol*, probing the 27 cells around
    each node so two nodes either side of a cell boundary still merge.

    Args:
        meshes: One (coords, triangles) pair per selected face, where coords is
            a list of (x, y, z) tuples in centimetres and triangles is a list of
            (i, j, k) index tuples into that face's own coords.
        tol: Weld tolerance in centimetres. Must be positive.

    Returns:
        ``(verts, tris, tri_source)`` where verts holds the merged coordinates,
        tris indexes into it, and tri_source[t] is the index of the mesh that
        contributed triangle t.

    Raises:
        ValueError: If *tol* is not positive.
    """
    if tol <= 0.0:
        raise ValueError("weld tolerance must be positive")

    buckets: dict = {}
    verts: list = []
    tris: list = []
    tri_source: list = []
    tol_sq = tol * tol

    for source, (coords, triangles) in enumerate(meshes):
        remap = []
        for point in coords:
            base = _cell(point, tol)
            found = None
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for dz in (-1, 0, 1):
                        for node in buckets.get(
                            (base[0] + dx, base[1] + dy, base[2] + dz), ()
                        ):
                            existing = verts[node]
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
                found = len(verts)
                verts.append((float(point[0]), float(point[1]), float(point[2])))
                buckets.setdefault(base, []).append(found)
            remap.append(found)

        for a, b, c in triangles:
            ra, rb, rc = remap[a], remap[b], remap[c]
            # A triangle whose corners welded together spans no area and would
            # only feed zeroes into the solver.
            if ra == rb or rb == rc or ra == rc:
                continue
            tris.append((ra, rb, rc))
            tri_source.append(source)

    return verts, tris, tri_source


def split_islands(vert_count: int, tris: list) -> list:
    """Group triangles into connected components.

    A selection of faces that do not touch cannot be flattened as one patch, so
    each component is solved on its own and the pieces are laid out side by side.

    Args:
        vert_count: Number of vertices the triangles index into.
        tris: Triangles as (i, j, k) index tuples.

    Returns:
        A list of triangle-index lists, one per component, ordered by the first
        triangle each component contains.
    """
    parent = list(range(vert_count))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b, c in tris:
        for u, v in ((a, b), (b, c)):
            ru, rv = find(u), find(v)
            if ru != rv:
                parent[rv] = ru

    groups: dict = {}
    for index, (a, _b, _c) in enumerate(tris):
        groups.setdefault(find(a), []).append(index)
    return list(groups.values())


def _triangle_frame(
    p1: tuple, p2: tuple, p3: tuple
) -> tuple[float, float, float, float]:
    """Return (x2, x3, y3, area) for a triangle laid flat in its own plane.

    The first corner sits at the origin and the second on the local x axis, so
    x1, y1 and y2 are zero by construction and are not returned.
    """
    e1 = (p2[0] - p1[0], p2[1] - p1[1], p2[2] - p1[2])
    x2 = math.sqrt(e1[0] * e1[0] + e1[1] * e1[1] + e1[2] * e1[2])
    if x2 <= 0.0:
        return 0.0, 0.0, 0.0, 0.0
    ux, uy, uz = e1[0] / x2, e1[1] / x2, e1[2] / x2

    w = (p3[0] - p1[0], p3[1] - p1[1], p3[2] - p1[2])
    x3 = w[0] * ux + w[1] * uy + w[2] * uz
    nx = w[0] - x3 * ux
    ny = w[1] - x3 * uy
    nz = w[2] - x3 * uz
    y3 = math.sqrt(nx * nx + ny * ny + nz * nz)
    return x2, x3, y3, 0.5 * x2 * y3


def _matvec(rows: list, x: list) -> list:
    out = [0.0] * len(x)
    for i, row in enumerate(rows):
        total = 0.0
        for j, value in row.items():
            total += value * x[j]
        out[i] = total
    return out


def solve_cg(
    rows: list,
    rhs: list,
    x0: list | None = None,
    tol: float = DEFAULT_CG_TOLERANCE,
    max_iter: int = 0,
) -> list:
    """Solve a sparse symmetric positive definite system.

    Jacobi-preconditioned conjugate gradient. Fusion's Python has no numpy, so
    this is the whole linear algebra budget: both LSCM and every ARAP iteration
    come through here.

    Args:
        rows: Matrix as one dict per row, mapping column index to value.
        rhs: Right-hand side, same length as *rows*.
        x0: Optional starting guess; warm-starting an ARAP iteration from the
            previous one cuts the iteration count sharply.
        tol: Convergence threshold on the squared residual norm.
        max_iter: Iteration cap; defaults to twice the system size.

    Returns:
        The solution vector.
    """
    n = len(rhs)
    if n == 0:
        return []
    if max_iter <= 0:
        max_iter = max(4 * n, 50)

    inverse_diagonal = []
    for i, row in enumerate(rows):
        d = row.get(i, 0.0)
        inverse_diagonal.append(1.0 / d if d > 0.0 else 1.0)

    x = list(x0) if x0 is not None else [0.0] * n
    ax = _matvec(rows, x)
    r = [rhs[i] - ax[i] for i in range(n)]
    z = [r[i] * inverse_diagonal[i] for i in range(n)]
    p = list(z)
    rz = sum(r[i] * z[i] for i in range(n))

    for _ in range(max_iter):
        if sum(value * value for value in r) <= tol:
            break
        ap = _matvec(rows, p)
        denominator = sum(p[i] * ap[i] for i in range(n))
        if abs(denominator) < 1e-300:
            break
        alpha = rz / denominator
        for i in range(n):
            x[i] += alpha * p[i]
            r[i] -= alpha * ap[i]
        z = [r[i] * inverse_diagonal[i] for i in range(n)]
        rz_next = sum(r[i] * z[i] for i in range(n))
        if abs(rz) < 1e-300:
            break
        beta = rz_next / rz
        for i in range(n):
            p[i] = z[i] + beta * p[i]
        rz = rz_next

    return x


def _farthest_pair(verts: list, indices: list) -> tuple[int, int]:
    """Pick two well-separated vertices to pin, by two-pass farthest point."""
    first = indices[0]
    best = first
    best_distance = -1.0
    for index in indices:
        p, q = verts[index], verts[first]
        d = (p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 + (p[2] - q[2]) ** 2
        if d > best_distance:
            best_distance = d
            best = index
    second = best
    best = second
    best_distance = -1.0
    for index in indices:
        p, q = verts[index], verts[second]
        d = (p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 + (p[2] - q[2]) ** 2
        if d > best_distance:
            best_distance = d
            best = index
    return second, best


def lscm(verts: list, tris: list, local: list) -> list:
    """Lay a patch flat with a least-squares conformal map.

    Minimises the Cauchy-Riemann residual over the patch, which preserves angles
    and pushes all the error into area - exactly the quantity the strain map
    shows. Two pinned vertices remove the similarity null space; the result is
    then scaled so the flattened area matches the surface area.

    Args:
        verts: All welded 3D coordinates in centimetres.
        tris: Triangles of this island as (i, j, k) index tuples into *verts*.
        local: Vertex indices belonging to this island.

    Returns:
        One (u, v) tuple per entry of *local*, in the same order.
    """
    slot = {index: position for position, index in enumerate(local)}
    count = len(local)
    if count < 3:
        return [(0.0, 0.0)] * count

    pin_a, pin_b = _farthest_pair(verts, local)
    if pin_a == pin_b:
        pin_b = local[1] if local[0] == pin_a else local[0]
    pa, pb = verts[pin_a], verts[pin_b]
    span = math.sqrt((pa[0] - pb[0]) ** 2 + (pa[1] - pb[1]) ** 2 + (pa[2] - pb[2]) ** 2)
    pinned = {slot[pin_a]: (0.0, 0.0), slot[pin_b]: (span, 0.0)}

    # Unknowns are the free vertices' u and v, interleaved.
    free = [position for position in range(count) if position not in pinned]
    column = {position: 2 * order for order, position in enumerate(free)}
    size = 2 * len(free)
    if size == 0:
        return [pinned.get(position, (0.0, 0.0)) for position in range(count)]

    rows: list = [dict() for _ in range(size)]
    rhs = [0.0] * size

    def accumulate(entries: list, constant: float) -> None:
        """Fold one least-squares residual row into the normal equations."""
        for col_i, coeff_i in entries:
            target = rows[col_i]
            for col_j, coeff_j in entries:
                target[col_j] = target.get(col_j, 0.0) + coeff_i * coeff_j
            rhs[col_i] -= coeff_i * constant

    for a, b, c in tris:
        x2, x3, y3, area = _triangle_frame(verts[a], verts[b], verts[c])
        if area <= MIN_TRIANGLE_AREA:
            continue
        # Gradient coefficients of a linear function over the flattened
        # triangle, scaled so each residual carries its triangle's area weight.
        weight = 1.0 / (2.0 * math.sqrt(area))
        d_y = ((0.0 - y3) * weight, (y3 - 0.0) * weight, (0.0 - 0.0) * weight)
        d_x = ((x3 - x2) * weight, (0.0 - x3) * weight, (x2 - 0.0) * weight)
        corners = (slot[a], slot[b], slot[c])

        # The two Cauchy-Riemann residuals: du/dx - dv/dy and du/dy + dv/dx.
        for coeff_u, coeff_v, sign in ((d_y, d_x, -1.0), (d_x, d_y, 1.0)):
            entries = []
            constant = 0.0
            for corner, cu, cv in zip(corners, coeff_u, coeff_v, strict=True):
                pin = pinned.get(corner)
                if pin is None:
                    base = column[corner]
                    entries.append((base, cu))
                    entries.append((base + 1, sign * cv))
                else:
                    constant += cu * pin[0] + sign * cv * pin[1]
            accumulate(entries, constant)

    solution = solve_cg(rows, rhs)

    uvs = [(0.0, 0.0)] * count
    for position in range(count):
        pin = pinned.get(position)
        if pin is not None:
            uvs[position] = pin
        else:
            base = column[position]
            uvs[position] = (solution[base], solution[base + 1])
    return uvs


def _cotangent_rows(verts: list, tris: list, slot: dict, count: int) -> list:
    """Assemble the clamped cotangent Laplacian for one island."""
    rows: list = [dict() for _ in range(count)]
    for a, b, c in tris:
        weights = _triangle_cotangents(verts[a], verts[b], verts[c])
        corners = (slot[a], slot[b], slot[c])
        # Weight k belongs to the edge opposite corner k.
        for k, weight in enumerate(weights):
            i = corners[(k + 1) % 3]
            j = corners[(k + 2) % 3]
            rows[i][i] = rows[i].get(i, 0.0) + weight
            rows[j][j] = rows[j].get(j, 0.0) + weight
            rows[i][j] = rows[i].get(j, 0.0) - weight
            rows[j][i] = rows[j].get(i, 0.0) - weight
    return rows


def _triangle_cotangents(p1: tuple, p2: tuple, p3: tuple) -> tuple[float, float, float]:
    """Cotangent of each corner angle, clamped positive, indexed by corner."""
    points = (p1, p2, p3)
    out = []
    for k in range(3):
        at = points[k]
        u = points[(k + 1) % 3]
        v = points[(k + 2) % 3]
        e1 = (u[0] - at[0], u[1] - at[1], u[2] - at[2])
        e2 = (v[0] - at[0], v[1] - at[1], v[2] - at[2])
        dot = e1[0] * e2[0] + e1[1] * e2[1] + e1[2] * e2[2]
        cx = e1[1] * e2[2] - e1[2] * e2[1]
        cy = e1[2] * e2[0] - e1[0] * e2[2]
        cz = e1[0] * e2[1] - e1[1] * e2[0]
        cross = math.sqrt(cx * cx + cy * cy + cz * cz)
        out.append(max(dot / cross, MIN_COTAN) if cross > 0.0 else MIN_COTAN)
    return out[0], out[1], out[2]


def arap_relax(
    verts: list,
    tris: list,
    local: list,
    uvs: list,
    iterations: int = DEFAULT_ARAP_ITERATIONS,
) -> list:
    """Relax a conformal layout toward an as-rigid-as-possible one.

    Alternates a local step - fit the best rotation to each triangle in closed
    form - with a global step that re-solves the cotangent Laplacian against
    those rotations. This trades a little angle accuracy for markedly less area
    distortion, which is what a cut pattern wants.

    Args:
        verts: All welded 3D coordinates in centimetres.
        tris: Triangles of this island as (i, j, k) index tuples into *verts*.
        local: Vertex indices belonging to this island.
        uvs: Starting layout, one (u, v) per entry of *local*.
        iterations: Local/global sweeps to run.

    Returns:
        The relaxed layout, one (u, v) per entry of *local*.
    """
    count = len(local)
    if count < 3 or iterations <= 0:
        return uvs

    slot = {index: position for position, index in enumerate(local)}
    rows = _cotangent_rows(verts, tris, slot, count)

    # The Laplacian is singular by one translation per axis, so pin a vertex to
    # the origin. Dropping its column as well keeps the system symmetric, and is
    # only consistent because the pinned value is zero; the caller re-anchors the
    # island's position afterwards, so which point sits at the origin is moot.
    pin = 0
    for row in rows:
        row.pop(pin, None)
    rows[pin] = {pin: 1.0}

    frames = []
    for a, b, c in tris:
        x2, x3, y3, area = _triangle_frame(verts[a], verts[b], verts[c])
        cot = _triangle_cotangents(verts[a], verts[b], verts[c])
        frames.append(
            (
                (slot[a], slot[b], slot[c]),
                ((0.0, 0.0), (x2, 0.0), (x3, y3)),
                cot,
                area,
            )
        )

    current = list(uvs)
    for _ in range(iterations):
        rhs_u = [0.0] * count
        rhs_v = [0.0] * count

        for corners, flat, cot, area in frames:
            if area <= MIN_TRIANGLE_AREA:
                continue
            # Local step: the rotation closest to this triangle's current map.
            s00 = s01 = s10 = s11 = 0.0
            for k in range(3):
                i = (k + 1) % 3
                j = (k + 2) % 3
                weight = cot[k]
                dx = flat[i][0] - flat[j][0]
                dy = flat[i][1] - flat[j][1]
                du = current[corners[i]][0] - current[corners[j]][0]
                dv = current[corners[i]][1] - current[corners[j]][1]
                s00 += weight * du * dx
                s01 += weight * du * dy
                s10 += weight * dv * dx
                s11 += weight * dv * dy
            angle = math.atan2(s10 - s01, s00 + s11)
            cos_a, sin_a = math.cos(angle), math.sin(angle)

            # Global step right-hand side: rotate each edge and accumulate.
            for k in range(3):
                i = (k + 1) % 3
                j = (k + 2) % 3
                weight = cot[k]
                dx = flat[i][0] - flat[j][0]
                dy = flat[i][1] - flat[j][1]
                rx = weight * (cos_a * dx - sin_a * dy)
                ry = weight * (sin_a * dx + cos_a * dy)
                rhs_u[corners[i]] += rx
                rhs_u[corners[j]] -= rx
                rhs_v[corners[i]] += ry
                rhs_v[corners[j]] -= ry

        rhs_u[pin] = 0.0
        rhs_v[pin] = 0.0

        # Warm-starting from the previous sweep, shifted so the pin sits at the
        # origin, keeps each solve to a handful of iterations.
        shift = current[pin]
        next_u = solve_cg(rows, rhs_u, [uv[0] - shift[0] for uv in current])
        next_v = solve_cg(rows, rhs_v, [uv[1] - shift[1] for uv in current])
        current = [(next_u[i], next_v[i]) for i in range(count)]

    return current


def triangle_sigmas(verts: list, tris: list, uvs: list) -> list:
    """Singular values of each triangle's 3D-to-2D Jacobian.

    Every distortion measure falls out of these: sigma1 * sigma2 is the area
    ratio, sigma1 / sigma2 is the shear. Computed in closed form from the metric
    tensor, which is why no matrix library is needed.

    Args:
        verts: Welded 3D coordinates in centimetres.
        tris: Triangles as (i, j, k) index tuples.
        uvs: Flattened coordinates parallel to *verts*.

    Returns:
        One (sigma1, sigma2) tuple per triangle, sigma1 >= sigma2. Degenerate
        triangles yield (0.0, 0.0).
    """
    out = []
    for a, b, c in tris:
        x2, x3, y3, area = _triangle_frame(verts[a], verts[b], verts[c])
        if area <= MIN_TRIANGLE_AREA:
            out.append((0.0, 0.0))
            continue
        # Jacobian J solves J @ [3D edges in the local frame] = [2D edges].
        u1 = (uvs[b][0] - uvs[a][0], uvs[b][1] - uvs[a][1])
        u2 = (uvs[c][0] - uvs[a][0], uvs[c][1] - uvs[a][1])
        determinant = x2 * y3
        i00, i01 = 1.0 / x2, -x3 / determinant
        i11 = 1.0 / y3
        j00 = u1[0] * i00
        j01 = u1[0] * i01 + u2[0] * i11
        j10 = u1[1] * i00
        j11 = u1[1] * i01 + u2[1] * i11

        m00 = j00 * j00 + j10 * j10
        m01 = j00 * j01 + j10 * j11
        m11 = j01 * j01 + j11 * j11
        root = math.sqrt(max((m00 - m11) ** 2 + 4.0 * m01 * m01, 0.0))
        sigma1 = math.sqrt(max((m00 + m11 + root) * 0.5, 0.0))
        sigma2 = math.sqrt(max((m00 + m11 - root) * 0.5, 0.0))
        out.append((sigma1, sigma2))
    return out


def signed_area_2d(p1: tuple, p2: tuple, p3: tuple) -> float:
    """Signed area of a 2D triangle; negative means inverted winding."""
    return 0.5 * ((p2[0] - p1[0]) * (p3[1] - p1[1]) - (p3[0] - p1[0]) * (p2[1] - p1[1]))


def vertex_strain(
    verts: list, tris: list, uvs: list, sigmas: list
) -> tuple[list, FlattenStats]:
    """Spread per-triangle area strain onto vertices and summarise it.

    Strain is ``sqrt(sigma1 * sigma2) - 1``: the length-equivalent form of the
    area ratio, so 0.03 reads as three percent stretch. Vertices average their
    incident triangles weighted by area, which is what makes the colour map read
    smoothly instead of showing every sliver.

    Args:
        verts: Welded 3D coordinates in centimetres.
        tris: Triangles as (i, j, k) index tuples.
        uvs: Flattened coordinates parallel to *verts*.
        sigmas: Per-triangle singular values from :func:`triangle_sigmas`.

    Returns:
        ``(strain, stats)`` with one strain value per vertex.
    """
    totals = [0.0] * len(verts)
    weights = [0.0] * len(verts)
    stats = FlattenStats(vertices=len(verts), triangles=len(tris))
    abs_total = 0.0
    area_total = 0.0

    for index, (a, b, c) in enumerate(tris):
        _x2, _x3, _y3, area = _triangle_frame(verts[a], verts[b], verts[c])
        flat_area = signed_area_2d(uvs[a], uvs[b], uvs[c])
        stats.area_3d += area
        stats.area_2d += abs(flat_area)
        if area <= MIN_TRIANGLE_AREA:
            stats.degenerate += 1
            continue
        if flat_area < 0.0:
            stats.flipped += 1
        sigma1, sigma2 = sigmas[index]
        value = math.sqrt(max(sigma1 * sigma2, 0.0)) - 1.0
        for corner in (a, b, c):
            totals[corner] += value * area
            weights[corner] += area
        abs_total += abs(value) * area
        area_total += area

    strain = [
        totals[i] / weights[i] if weights[i] > 0.0 else 0.0 for i in range(len(verts))
    ]
    if area_total > 0.0:
        stats.mean_abs_strain = abs_total / area_total
    if strain:
        stats.min_vertex = min(range(len(strain)), key=lambda i: strain[i])
        stats.max_vertex = max(range(len(strain)), key=lambda i: strain[i])
        stats.min_strain = strain[stats.min_vertex]
        stats.max_strain = strain[stats.max_vertex]
    return strain, stats


def boundary_loops(tris: list) -> list:
    """Chain the patch's boundary edges into closed loops.

    A boundary edge is a directed triangle edge whose opposite is not used by
    any other triangle, so the loops come out consistently oriented.

    Args:
        tris: Triangles as (i, j, k) index tuples.

    Returns:
        A list of loops, each a list of vertex indices in order.
    """
    directed = set()
    for a, b, c in tris:
        directed.add((a, b))
        directed.add((b, c))
        directed.add((c, a))

    remaining: dict = {}
    for a, b in sorted(directed):
        if (b, a) not in directed:
            remaining.setdefault(a, []).append(b)

    loops = []
    for start in sorted(remaining):
        while remaining.get(start):
            loop = [start]
            current = start
            while True:
                outgoing = remaining.get(current)
                if not outgoing:
                    break
                following = outgoing.pop(0)
                if not outgoing:
                    del remaining[current]
                if following == start:
                    break
                loop.append(following)
                current = following
            if len(loop) >= 3:
                loops.append(loop)
    return loops


def _chain_edges(edges: list) -> list:
    """Chain undirected edges into polylines, open chains first."""
    adjacency: dict = {}
    for a, b in edges:
        adjacency.setdefault(a, []).append(b)
        adjacency.setdefault(b, []).append(a)

    unused = {tuple(sorted(edge)) for edge in edges}
    chains = []
    ends = sorted(v for v, n in adjacency.items() if len(n) != 2)

    def walk(start: int) -> list:
        chain = [start]
        current = start
        while True:
            step = None
            for neighbour in sorted(adjacency.get(current, ())):
                key = tuple(sorted((current, neighbour)))
                if key in unused:
                    step = neighbour
                    unused.discard(key)
                    break
            if step is None:
                return chain
            chain.append(step)
            current = step

    for start in ends:
        while any(
            tuple(sorted((start, n))) in unused for n in adjacency.get(start, ())
        ):
            chain = walk(start)
            if len(chain) >= 2:
                chains.append(chain)

    while unused:
        start = next(iter(sorted(unused)))[0]
        chain = walk(start)
        if len(chain) >= 2:
            chains.append(chain)
    return chains


def angle_defects(verts: list, tris: list) -> dict:
    """Curvature held at each interior vertex, as 2*pi minus the angles there.

    This is what says whether a patch can lay flat at all. A vertex whose
    incident angles sum to a full turn is intrinsically flat, and a patch that
    is flat at every interior vertex flattens exactly - which is why a plane, a
    cylinder, and any number of them joined edge to edge come out with no strain
    at all. Where three or more faces meet at a point the angles fall short of a
    full turn, and that shortfall is curvature no algorithm can flatten away. A
    box corner holds exactly 90 degrees of it.

    Boundary vertices are excluded: they are meant to fall short of a full turn.

    Args:
        verts: Coordinates the triangles index into.
        tris: Triangles as (i, j, k) index tuples.

    Returns:
        Interior vertex index -> defect in radians. Positive is a cone point,
        negative a saddle, and near-zero means locally flattenable.
    """
    total: dict = {}
    for a, b, c in tris:
        for vertex, first, second in ((a, b, c), (b, c, a), (c, a, b)):
            origin = verts[vertex]
            u = [verts[first][k] - origin[k] for k in range(3)]
            v = [verts[second][k] - origin[k] for k in range(3)]
            nu = math.sqrt(sum(value * value for value in u))
            nv = math.sqrt(sum(value * value for value in v))
            if nu <= 0.0 or nv <= 0.0:
                continue
            cosine = sum(u[k] * v[k] for k in range(3)) / (nu * nv)
            total[vertex] = total.get(vertex, 0.0) + math.acos(
                max(-1.0, min(1.0, cosine))
            )

    on_edge = {index for edge in _boundary_edges(tris) for index in edge}
    return {
        vertex: 2.0 * math.pi - angle
        for vertex, angle in total.items()
        if vertex not in on_edge
    }


def _boundary_edges(tris: list) -> list:
    """Edges used by exactly one triangle, so the rim of the patch."""
    counts: dict = {}
    for a, b, c in tris:
        for i, j in ((a, b), (b, c), (c, a)):
            key = (i, j) if i < j else (j, i)
            counts[key] = counts.get(key, 0) + 1
    return [edge for edge, count in counts.items() if count == 1]


def _points_on_edge(verts: list, start: int, end: int, candidates: list, tol: float):
    """Candidate vertices lying along the segment, ordered from start to end."""
    origin, finish = verts[start], verts[end]
    span = [finish[k] - origin[k] for k in range(3)]
    length_sq = sum(value * value for value in span)
    if length_sq <= 0.0:
        return []

    found = []
    for vertex in candidates:
        if vertex in (start, end):
            continue
        point = verts[vertex]
        offset = [point[k] - origin[k] for k in range(3)]
        position = sum(offset[k] * span[k] for k in range(3)) / length_sq
        if not 0.0 < position < 1.0:
            continue
        gap = sum((offset[k] - position * span[k]) ** 2 for k in range(3))
        if gap <= tol * tol:
            found.append((position, vertex))
    found.sort()
    return [vertex for _position, vertex in found]


def stitch_cracks(
    verts: list, tris: list, tri_source: list, tol: float
) -> tuple[list, list, int]:
    """Close gaps left where neighbouring faces were meshed differently.

    Fusion tessellates each face on its own, so two faces sharing an edge can
    sample it differently. Welding then joins them only at whatever nodes happen
    to land in the same place, leaving the rest of the edge as a pair of free
    rims with one side's vertices stranded partway along the other's triangles.
    Nothing downstream notices - the patch still reports as one connected island
    with no flipped triangles and matching areas - but it is hinged rather than
    joined, and it flattens into a mess.

    Each stranded vertex is welded in by re-cutting the triangle that spans it.
    Adding points along the edges of a triangle leaves a convex polygon, so a
    fan from an untouched corner always retriangulates it correctly.

    Args:
        verts: Coordinates the triangles index into.
        tris: Triangles as (i, j, k) index tuples.
        tri_source: Source face per triangle, kept in step with *tris*.
        tol: How far off the line a vertex may sit and still count as on it. A
            shared straight edge gives exact hits, but two faces approximate a
            shared arc differently, so their points sit near each other rather
            than on top of each other.

    Returns:
        ``(tris, tri_source, stitched)`` with *stitched* counting the gaps
        closed.
    """
    tris = list(tris)
    tri_source = list(tri_source)
    stitched = 0

    for _pass in range(MAX_STITCH_PASSES):
        boundary = _boundary_edges(tris)
        if not boundary:
            break
        loose = sorted({index for edge in boundary for index in edge})
        owner: dict = {}
        for index, (a, b, c) in enumerate(tris):
            for i, j in ((a, b), (b, c), (c, a)):
                owner[(i, j) if i < j else (j, i)] = index

        rebuilt: dict = {}
        for start, end in boundary:
            extra = _points_on_edge(verts, start, end, loose, tol)
            if not extra:
                continue
            index = owner.get((start, end))
            if index is None or index in rebuilt:
                continue
            rebuilt[index] = (start, end, extra)

        if not rebuilt:
            break

        for index, (start, end, extra) in rebuilt.items():
            triangle = tris[index]
            apex = next(corner for corner in triangle if corner not in (start, end))
            # Keep the winding: walk the edge the way this triangle already does.
            order = list(triangle)
            forward = order[(order.index(start) + 1) % 3] == end
            chain = [start, *extra, end] if forward else [end, *reversed(extra), start]
            fan = [
                (apex, chain[step], chain[step + 1]) for step in range(len(chain) - 1)
            ]
            tris[index] = fan[0]
            source = tri_source[index]
            for piece in fan[1:]:
                tris.append(piece)
                tri_source.append(source)
            stitched += len(extra)

    return tris, tri_source, stitched


def euler_characteristic(vertex_count: int, tris: list) -> int:
    """V - E + F for a patch: 1 for a disc, 0 for a tube or a washer.

    Anything other than 1 cannot be laid flat as it stands, though that does not
    always mean it needs cutting - a flat washer is a 0 and is already flat.
    """
    return vertex_count - len(mesh_edges(tris)) + len(tris)


def _half_edge_maps(tris: list) -> tuple[dict, dict]:
    """Index triangles by the directed edges leaving and arriving at each corner."""
    out_tri: dict = {}
    in_tri: dict = {}
    for index, (a, b, c) in enumerate(tris):
        for vertex, out, into in ((a, b, c), (b, c, a), (c, a, b)):
            out_tri[(vertex, out)] = index
            in_tri[(vertex, into)] = index
    return out_tri, in_tri


def _corner(tris: list, index: int, vertex: int) -> tuple[int, int]:
    """The out and in neighbours of *vertex* within triangle *index*."""
    a, b, c = tris[index]
    if vertex == a:
        return b, c
    if vertex == b:
        return c, a
    return a, b


def _shortest_vertex_path(tris: list, sources: set, targets: set) -> list:
    """Fewest-edges path across the mesh from any source to any target."""
    adjacency: dict = {}
    for a, b, c in tris:
        for i, j in ((a, b), (b, c), (c, a)):
            adjacency.setdefault(i, set()).add(j)
            adjacency.setdefault(j, set()).add(i)

    previous: dict = {}
    seen = set(sources)
    frontier = sorted(sources)
    while frontier:
        following = []
        for vertex in frontier:
            if vertex in targets:
                path = [vertex]
                while path[-1] in previous:
                    path.append(previous[path[-1]])
                path.reverse()
                return path
            for neighbour in sorted(adjacency.get(vertex, ())):
                if neighbour not in seen:
                    seen.add(neighbour)
                    previous[neighbour] = vertex
                    following.append(neighbour)
        frontier = following
    return []


def cut_to_disk(verts: list, tris: list) -> tuple[list, list]:
    """Slit a tube open along a seam so it can be laid flat.

    A closed tube has no flat form at all - the paper-towel-roll problem. One
    cut from one open end to the other turns it into a disc, which then flattens
    exactly, because a tube is developable once slit.

    The seam is the shortest run of mesh edges between the two boundaries. Every
    vertex along it is duplicated, and the triangles on one side of the seam are
    moved onto the duplicates, which opens the surface without moving or losing
    any geometry.

    Args:
        verts: Coordinates the triangles index into.
        tris: Triangles of one connected patch.

    Returns:
        ``(verts, tris)`` with the seam opened. Both are returned unchanged when
        the patch has fewer than two boundaries to cut between, which is the
        case for a disc (nothing to do) and for a closed shell such as a sphere
        (a single cut would not open it).
    """
    loops = boundary_loops(tris)
    if len(loops) < 2:
        return list(verts), list(tris)

    path = _shortest_vertex_path(tris, set(loops[0]), set(loops[1]))
    if len(path) < 2:
        return list(verts), list(tris)

    out_tri, in_tri = _half_edge_maps(tris)
    new_verts = list(verts)
    new_tris = list(tris)

    for position, vertex in enumerate(path):
        before = path[position - 1] if position > 0 else None
        after = path[position + 1] if position + 1 < len(path) else None

        # Take the side of the seam lying to the left of the path's direction of
        # travel. Anchoring on the directed edge keeps that choice the same at
        # every vertex, so the seam opens along one clean line.
        if after is not None:
            start = out_tri.get((vertex, after))
            stop = out_tri.get((vertex, before)) if before is not None else None
            side = _fan_forward(new_tris, out_tri, vertex, start, stop)
        else:
            start = in_tri.get((vertex, before))
            side = _fan_backward(new_tris, in_tri, vertex, start)

        if not side or len(side) == len(_incident(new_tris, vertex)):
            # The whole fan on one side means no real split here; duplicating
            # would only orphan the original vertex.
            continue

        duplicate = len(new_verts)
        new_verts.append(verts[vertex])
        for index in side:
            new_tris[index] = tuple(
                duplicate if corner == vertex else corner for corner in new_tris[index]
            )

    return new_verts, new_tris


def _incident(tris: list, vertex: int) -> list:
    return [index for index, tri in enumerate(tris) if vertex in tri]


def _fan_forward(tris: list, out_tri: dict, vertex: int, start, stop) -> list:
    """Rotate around *vertex* from *start*, stopping before *stop*."""
    if start is None:
        return []
    found = []
    current = start
    for _ in range(len(tris)):
        if current is None or current == stop:
            break
        found.append(current)
        _out, into = _corner(tris, current, vertex)
        current = out_tri.get((vertex, into))
        if current == start:
            break
    return found


def _fan_backward(tris: list, in_tri: dict, vertex: int, start) -> list:
    """Rotate the other way around *vertex* from *start* until the fan ends."""
    if start is None:
        return []
    found = []
    current = start
    for _ in range(len(tris)):
        if current is None:
            break
        found.append(current)
        out, _into = _corner(tris, current, vertex)
        current = in_tri.get((vertex, out))
        if current == start:
            break
    return found


def _convex_hull(points: list) -> list:
    """Andrew's monotone chain hull, counter-clockwise."""
    ordered = sorted(set(points))
    if len(ordered) < 3:
        return ordered

    def build(sequence):
        chain = []
        for point in sequence:
            while len(chain) >= 2:
                (x1, y1), (x2, y2) = chain[-2], chain[-1]
                if (x2 - x1) * (point[1] - y1) - (y2 - y1) * (point[0] - x1) > 0.0:
                    break
                chain.pop()
            chain.append(point)
        return chain

    lower = build(ordered)
    upper = build(reversed(ordered))
    return lower[:-1] + upper[:-1]


def tightest_box_angle(points: list) -> float:
    """Angle at which *points* occupy the smallest axis-aligned box.

    A conformal map fixes orientation arbitrarily, so a rectangular panel
    routinely lands at an angle. Squaring it up costs nothing and makes the
    pattern far easier to measure, nest and cut.

    Uses the rotating-calipers result that a minimal bounding box always has a
    side flush with an edge of the convex hull, so only the hull edges need
    testing rather than a sweep of arbitrary angles.

    Args:
        points: (u, v) tuples.

    Returns:
        The angle in radians to rotate *points* by, clockwise, to square them up.
    """
    hull = _convex_hull(points)
    if len(hull) < 3:
        return 0.0

    best_area = None
    best_angle = 0.0
    best_extent = (0.0, 0.0)
    for index, (x1, y1) in enumerate(hull):
        x2, y2 = hull[(index + 1) % len(hull)]
        angle = math.atan2(y2 - y1, x2 - x1)
        cos_a, sin_a = math.cos(-angle), math.sin(-angle)
        xs = [x * cos_a - y * sin_a for x, y in hull]
        ys = [x * sin_a + y * cos_a for x, y in hull]
        extent = (max(xs) - min(xs), max(ys) - min(ys))
        area = extent[0] * extent[1]
        if best_area is None or area < best_area:
            best_area = area
            best_angle = angle
            best_extent = extent

    # Four rotations give the same box, so settle on the landscape one. Which
    # of them comes out of the hull walk is an accident of vertex order, and a
    # pattern that lands portrait one time and landscape the next is a nuisance
    # to nest and to compare.
    if best_extent[1] > best_extent[0]:
        best_angle += math.pi / 2.0
    return best_angle


def rotate_points(points: list, angle: float) -> list:
    """Rotate (u, v) tuples clockwise by *angle* radians."""
    cos_a, sin_a = math.cos(-angle), math.sin(-angle)
    return [(x * cos_a - y * sin_a, x * sin_a + y * cos_a) for x, y in points]


def mesh_edges(tris: list) -> list:
    """List every edge of the triangulation once.

    Shared edges appear in two triangles, so drawing the wireframe straight from
    the triangle list would draw most of it twice.

    Args:
        tris: Triangles as (i, j, k) index tuples.

    Returns:
        Sorted (low, high) vertex index pairs.
    """
    edges = set()
    for a, b, c in tris:
        for i, j in ((a, b), (b, c), (c, a)):
            edges.add((i, j) if i < j else (j, i))
    return sorted(edges)


def seam_chains(tris: list, tri_source: list) -> list:
    """Find the interior edges where two different selected faces meet.

    These are the panel seam lines: real features of the flat pattern, drawn as
    construction geometry so the outline stays unambiguous.

    Args:
        tris: Triangles as (i, j, k) index tuples.
        tri_source: Source face index per triangle, from :func:`weld_meshes`.

    Returns:
        A list of polylines, each a list of vertex indices.
    """
    edge_sources: dict = {}
    for index, (a, b, c) in enumerate(tris):
        source = tri_source[index]
        for i, j in ((a, b), (b, c), (c, a)):
            key = (i, j) if i < j else (j, i)
            edge_sources.setdefault(key, []).append(source)

    seams = [
        edge
        for edge, sources in sorted(edge_sources.items())
        if len(sources) == 2 and sources[0] != sources[1]
    ]
    return _chain_edges(seams)


def strain_to_rgba(value: float, limit: float, alpha: int = 255) -> tuple:
    """Map a signed strain to a diverging blue-white-red colour.

    Args:
        value: Signed area strain; negative compresses, positive stretches.
        limit: Symmetric clip, so -limit is fully blue and +limit fully red.
        alpha: Alpha channel to attach.

    Returns:
        An (r, g, b, a) tuple of 0-255 integers.
    """
    if limit <= 0.0:
        position = 0.5
    else:
        position = (value + limit) / (2.0 * limit)
    position = min(1.0, max(0.0, position))

    # Deliberately ragged: each stop is paired with the one after it.
    for (t0, c0), (t1, c1) in zip(_COOLWARM, _COOLWARM[1:], strict=False):
        if position <= t1:
            span = t1 - t0
            f = 0.0 if span <= 0.0 else (position - t0) / span
            return (
                round(c0[0] + f * (c1[0] - c0[0])),
                round(c0[1] + f * (c1[1] - c0[1])),
                round(c0[2] + f * (c1[2] - c0[2])),
                alpha,
            )
    last = _COOLWARM[-1][1]
    return (last[0], last[1], last[2], alpha)


def strain_limit(strain: list, percentile: float = 0.02) -> float:
    """Choose a symmetric colour range, ignoring a tail of outliers.

    One bad sliver would otherwise wash the whole map out to neutral, so the
    extremes are trimmed before taking the larger magnitude.

    The range never shrinks below :data:`MIN_STRAIN_LIMIT`. Without that floor a
    surface that flattens exactly would still fill the whole map: its strain is
    solver residue of about 1e-7, and a scale fitted to that renders noise as
    though it were a saddle.

    Args:
        strain: Per-vertex strain values.
        percentile: Fraction trimmed from each end, 0 to 0.5.

    Returns:
        A positive limit, or 0.0 when there is nothing to show.
    """
    if not strain:
        return 0.0
    ordered = sorted(strain)
    cut = min(int(len(ordered) * percentile), (len(ordered) - 1) // 2)
    low = ordered[cut]
    high = ordered[len(ordered) - 1 - cut]
    return max(abs(low), abs(high), MIN_STRAIN_LIMIT)


def is_measurable(stats) -> bool:
    """Whether a run found any distortion worth showing.

    Used to keep an exact flatten from being dressed up as a strained one: no
    colour worth reading, and no worst-spot markers, because the worst spot on a
    surface with no distortion is wherever the arithmetic happened to land.
    """
    return (
        max(abs(stats.min_strain), abs(stats.max_strain), stats.mean_abs_strain)
        >= MIN_STRAIN_LIMIT
    )


def _normalise(verts: list, tris: list, local: list, uvs: list) -> list:
    """Fix mirroring and scale so the layout matches the surface it came from."""
    slot = {index: position for position, index in enumerate(local)}
    signed = 0.0
    area_3d = 0.0
    area_2d = 0.0
    for a, b, c in tris:
        pa, pb, pc = uvs[slot[a]], uvs[slot[b]], uvs[slot[c]]
        value = signed_area_2d(pa, pb, pc)
        signed += value
        area_2d += abs(value)
        area_3d += _triangle_frame(verts[a], verts[b], verts[c])[3]

    # LSCM is free to hand back a mirrored layout; a mirrored cut pattern is a
    # real defect, so flip it back before anything downstream sees it.
    if signed < 0.0:
        uvs = [(u, -v) for u, v in uvs]
    if area_2d > 0.0 and area_3d > 0.0:
        scale = math.sqrt(area_3d / area_2d)
        uvs = [(u * scale, v * scale) for u, v in uvs]
    return uvs


def flatten_meshes(
    meshes: list,
    weld_tol: float = DEFAULT_WELD_TOL,
    relax: bool = True,
    iterations: int = DEFAULT_ARAP_ITERATIONS,
    island_gap: float = DEFAULT_ISLAND_GAP,
) -> FlattenResult:
    """Flatten tessellated faces into one pattern with a strain map.

    Welds the faces into a single patch, lays each connected island flat with
    LSCM, optionally relaxes it with ARAP, then measures the distortion that is
    left and extracts the outline and seam lines.

    Args:
        meshes: One (coords, triangles) pair per selected face, in centimetres.
        weld_tol: Vertex weld tolerance in centimetres.
        relax: Run the ARAP relaxation after LSCM.
        iterations: ARAP sweeps when *relax* is set.
        island_gap: Space left between disconnected islands, in centimetres.

    Returns:
        A :class:`FlattenResult`. Its ``tris`` is empty when the selection held
        no usable triangles.
    """
    verts, tris, tri_source = weld_meshes(meshes, weld_tol)
    result = FlattenResult(verts=verts, tris=tris)
    if not tris:
        return result

    verts = list(verts)
    # Close any gaps before solving. A patch left hinged by uneven tessellation
    # still looks connected to everything downstream, so this has to happen
    # before the layout is computed rather than be caught afterwards.
    tris, tri_source, cracks_stitched = stitch_cracks(
        verts, tris, tri_source, weld_tol * _STITCH_TOL_FACTOR
    )
    seams_cut = 0
    offset_x = 0.0
    placed: list = []

    for triangle_indices in split_islands(len(verts), tris):
        island_tris = [tris[i] for i in triangle_indices]
        layout, island_tris, cut = _flatten_island(
            verts, island_tris, relax, iterations
        )
        seams_cut += 1 if cut else 0
        for position, index in enumerate(triangle_indices):
            tris[index] = island_tris[position]

        # Square the island up before placing it. A conformal map fixes
        # orientation arbitrarily, so without this a plain rectangular panel
        # routinely lands at an angle.
        local = _island_vertices(island_tris)
        layout = rotate_points(layout, tightest_box_angle(layout))

        min_x = min(uv[0] for uv in layout)
        min_y = min(uv[1] for uv in layout)
        max_x = max(uv[0] for uv in layout)
        placed.append(
            (
                local,
                [(uv[0] - min_x + offset_x, uv[1] - min_y) for uv in layout],
            )
        )
        offset_x += (max_x - min_x) + island_gap

    uvs = [(0.0, 0.0)] * len(verts)
    for local, layout in placed:
        for position, index in enumerate(local):
            uvs[index] = layout[position]

    sigmas = triangle_sigmas(verts, tris, uvs)
    strain, stats = vertex_strain(verts, tris, uvs, sigmas)
    stats.islands = len(placed)
    stats.seams_cut = seams_cut
    stats.cracks_stitched = cracks_stitched

    # Curvature that no layout can remove, so the dialog can say plainly whether
    # the strain it is showing was ever avoidable.
    defects = angle_defects(verts, tris)
    floor = math.radians(MIN_DEFECT_DEGREES)
    stats.bent_points = sum(1 for value in defects.values() if abs(value) > floor)
    stats.worst_defect = max((abs(v) for v in defects.values()), default=0.0)

    loops = boundary_loops(tris)
    loops.sort(
        key=lambda loop: abs(_loop_area(uvs, loop)),
        reverse=True,
    )

    result.verts = verts
    result.tris = tris
    result.uvs = uvs
    result.strain = strain
    result.stats = stats
    result.boundary = loops
    result.seams = seam_chains(tris, tri_source)
    return result


def _island_vertices(tris: list) -> list:
    """The vertices one island's triangles use, in first-seen order."""
    seen: dict = {}
    for a, b, c in tris:
        for corner in (a, b, c):
            if corner not in seen:
                seen[corner] = len(seen)
    return list(seen)


def _solve_island(verts: list, tris: list, relax: bool, iterations: int) -> list:
    """Lay one island flat and return its layout, ordered by _island_vertices."""
    local = _island_vertices(tris)
    layout = lscm(verts, tris, local)
    layout = _normalise(verts, tris, local, layout)
    if relax:
        layout = arap_relax(verts, tris, local, layout, iterations)
        layout = _normalise(verts, tris, local, layout)
    return layout


def _mean_strain(verts: list, tris: list, local: list, layout: list) -> float:
    """Area-weighted mean absolute strain of one island's layout."""
    spread = [(0.0, 0.0)] * (max(local) + 1) if local else []
    for position, index in enumerate(local):
        spread[index] = layout[position]
    sigmas = triangle_sigmas(verts, tris, spread)
    total = 0.0
    weight = 0.0
    for index, (a, b, c) in enumerate(tris):
        area = _triangle_frame(verts[a], verts[b], verts[c])[3]
        if area <= MIN_TRIANGLE_AREA:
            continue
        sigma1, sigma2 = sigmas[index]
        total += abs(math.sqrt(max(sigma1 * sigma2, 0.0)) - 1.0) * area
        weight += area
    return total / weight if weight > 0.0 else 0.0


def _flatten_island(
    verts: list, tris: list, relax: bool, iterations: int
) -> tuple[list, list, bool]:
    """Lay one island flat, slitting it open first if that turns out to help.

    A patch that is not a disc may or may not need cutting, and the topology
    alone does not say which: a closed tube has no flat form at all, while a
    flat washer is the same shape topologically and is already flat. So the cut
    is judged by its result - it is kept only when it actually lowers the
    distortion, which leaves washer-like patches unslit.

    Args:
        verts: Coordinates, extended in place when a cut adds vertices.
        tris: This island's triangles.
        relax: Whether to run the ARAP relaxation.
        iterations: ARAP sweeps.

    Returns:
        ``(layout, tris, cut)`` where layout is ordered by the vertices of the
        returned triangles, and cut says whether a seam was opened.
    """
    layout = _solve_island(verts, tris, relax, iterations)
    local = _island_vertices(tris)
    if euler_characteristic(len(local), tris) == 1:
        return layout, tris, False

    before = _mean_strain(verts, tris, local, layout)
    if before <= CUT_WORTH_TRYING:
        return layout, tris, False

    cut_verts, cut_tris = cut_to_disk(verts, tris)
    if len(cut_verts) == len(verts):
        return layout, tris, False

    cut_layout = _solve_island(cut_verts, cut_tris, relax, iterations)
    cut_local = _island_vertices(cut_tris)
    after = _mean_strain(cut_verts, cut_tris, cut_local, cut_layout)
    if after >= before:
        return layout, tris, False

    # Adopt the cut: the duplicated vertices have to reach the caller's array.
    verts.extend(cut_verts[len(verts) :])
    return cut_layout, cut_tris, True


def _turn_degrees(before: tuple, at: tuple, after: tuple) -> float:
    """How far the direction turns when passing through *at*, in degrees."""
    v1x, v1y = at[0] - before[0], at[1] - before[1]
    v2x, v2y = after[0] - at[0], after[1] - at[1]
    n1 = math.hypot(v1x, v1y)
    n2 = math.hypot(v2x, v2y)
    if n1 <= 0.0 or n2 <= 0.0:
        return 0.0
    cosine = (v1x * v2x + v1y * v2y) / (n1 * n2)
    return math.degrees(math.acos(max(-1.0, min(1.0, cosine))))


def _run_between(points: list, start: int, end: int) -> list:
    """Walk a closed chain from *start* to *end*, wrapping if it has to.

    When start and end are the same index this returns the whole way round,
    beginning and ending on that point.
    """
    count = len(points)
    out = [points[start]]
    index = start
    for _ in range(count):
        index = (index + 1) % count
        out.append(points[index])
        if index == end:
            break
    return out


def split_at_corners(
    points: list,
    angle_degrees: float = DEFAULT_CORNER_DEGREES,
    closed: bool = False,
) -> list:
    """Break a chain wherever its direction turns sharply.

    A flat pattern's outline is a mix of smooth runs and hard corners. Fitting
    one spline through the whole thing averages the corners away and the pattern
    loses its shape, so the chain is cut at every corner first and each run is
    fitted on its own.

    Runs share their end points with their neighbours, so the curves built from
    them meet exactly.

    Args:
        points: (u, v) tuples in centimetres.
        angle_degrees: Turn above which a vertex counts as a corner. Points on a
            tessellated smooth edge turn by a few degrees between segments; a
            real corner turns by far more.
        closed: True when the chain is a closed loop.

    Returns:
        A list of runs. A chain with no corners comes back as a single run equal
        to the input, which the caller may then treat as one curve.
    """
    if len(points) < 3:
        return [list(points)]

    corners = []
    if closed:
        count = len(points)
        for index in range(count):
            before = points[(index - 1) % count]
            after = points[(index + 1) % count]
            if _turn_degrees(before, points[index], after) >= angle_degrees:
                corners.append(index)
    else:
        for index in range(1, len(points) - 1):
            turn = _turn_degrees(points[index - 1], points[index], points[index + 1])
            if turn >= angle_degrees:
                corners.append(index)

    if not corners:
        return [list(points)]

    if closed:
        return [
            _run_between(
                points, corners[position], corners[(position + 1) % len(corners)]
            )
            for position in range(len(corners))
        ]

    bounds = [0, *corners, len(points) - 1]
    return [
        points[bounds[position] : bounds[position + 1] + 1]
        for position in range(len(bounds) - 1)
    ]


def _point_line_distance(point: tuple, start: tuple, end: tuple) -> float:
    """Perpendicular distance from *point* to the segment *start*-*end*."""
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length_sq = dx * dx + dy * dy
    if length_sq <= 0.0:
        return math.hypot(point[0] - start[0], point[1] - start[1])
    t = ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / length_sq
    t = min(1.0, max(0.0, t))
    return math.hypot(point[0] - (start[0] + t * dx), point[1] - (start[1] + t * dy))


def simplify_loop(points: list, tol: float, closed: bool = False) -> list:
    """Drop points that add nothing to a chain's shape.

    A tessellated boundary carries a point per mesh node. Fitting a spline
    through all of them is slow and wobbles between nodes, so the run is thinned
    with Douglas-Peucker first: every dropped point lies within *tol* of the
    line that replaces it, which bounds the error the sketch can pick up.

    Iterative rather than recursive, because a dense boundary would otherwise
    risk the interpreter's recursion limit.

    Args:
        points: (u, v) tuples in centimetres.
        tol: Largest distance a dropped point may sit from the kept chain.
        closed: True when the chain is a closed loop.

    Returns:
        The kept points, in order, always including the first and last.
    """
    if len(points) < 3 or tol <= 0.0:
        return list(points)

    keep = [False] * len(points)
    keep[0] = True
    keep[-1] = True
    stack = [(0, len(points) - 1)]

    while stack:
        first, last = stack.pop()
        if last <= first + 1:
            continue
        worst = 0.0
        worst_at = first
        for index in range(first + 1, last):
            distance = _point_line_distance(points[index], points[first], points[last])
            if distance > worst:
                worst = distance
                worst_at = index
        if worst > tol:
            keep[worst_at] = True
            stack.append((first, worst_at))
            stack.append((worst_at, last))

    kept = [point for point, wanted in zip(points, keep, strict=True) if wanted]
    # A loop thinned to a degenerate sliver would produce no usable curve.
    if closed and len(kept) < 3:
        return list(points)
    return kept


def fit_circle(points: list) -> tuple | None:
    """Least-squares circle through 2D points, or None if they do not curve.

    Uses the algebraic (Kasa) fit, which is a single 3x3 solve rather than an
    iteration. Points are shifted to their centroid first, without which a
    small arc a long way from the origin loses most of its precision.

    Args:
        points: (u, v) tuples, at least three of them.

    Returns:
        ``(cx, cy, radius)``, or None when the points are collinear or so
        nearly so that the fitted radius means nothing.
    """
    if len(points) < 3:
        return None
    count = float(len(points))
    ox = sum(p[0] for p in points) / count
    oy = sum(p[1] for p in points) / count

    sxx = sxy = syy = sxz = syz = sz = 0.0
    for px, py in points:
        x = px - ox
        y = py - oy
        z = x * x + y * y
        sxx += x * x
        sxy += x * y
        syy += y * y
        sxz += x * z
        syz += y * z
        sz += z

    # Centred, so the sums of x and y vanish and the 3x3 drops to a 2x2.
    determinant = sxx * syy - sxy * sxy
    if abs(determinant) <= 1e-18:
        return None
    cx = (syy * sxz - sxy * syz) / (2.0 * determinant)
    cy = (sxx * syz - sxy * sxz) / (2.0 * determinant)
    radius_sq = cx * cx + cy * cy + sz / count
    if radius_sq <= 0.0:
        return None
    radius = math.sqrt(radius_sq)

    # A straight run also "fits" a circle, one of absurd radius. Rejecting that
    # here is what stops a line being drawn as an arc.
    span = max(
        math.dist(points[0], points[-1]),
        max(math.dist(points[0], p) for p in points),
    )
    if span > 0.0 and radius > span * MAX_ARC_RADIUS_SPANS:
        return None
    return (cx + ox, cy + oy, radius)


def circle_deviation(points: list, cx: float, cy: float, radius: float) -> float:
    """Furthest any point sits from the given circle."""
    return max(abs(math.hypot(p[0] - cx, p[1] - cy) - radius) for p in points)


def line_deviation(points: list) -> float:
    """Furthest any point sits from the chord between the first and last."""
    if len(points) < 3:
        return 0.0
    return max(
        _point_line_distance(point, points[0], points[-1]) for point in points[1:-1]
    )


def _fits_circle(points: list, tol: float) -> bool:
    fit = fit_circle(points)
    return fit is not None and circle_deviation(points, *fit) <= tol


def _median_step(points: list) -> float:
    """Typical spacing between neighbouring points in a chain."""
    steps = sorted(math.dist(a, b) for a, b in zip(points, points[1:], strict=False))
    return steps[len(steps) // 2] if steps else 0.0


def _is_real_geometry(slice_points: list, step: float) -> bool:
    """Whether a fitted primitive describes the shape or just spans a gap.

    A straight edge of the part covers many chain points, or if the tessellator
    left it as a single long segment, a distance far greater than the spacing
    around it. A smooth curve being sliced into two-point chords does neither,
    and belongs in a spline.
    """
    if len(slice_points) >= MIN_PRIMITIVE_POINTS:
        return True
    length = math.dist(slice_points[0], slice_points[-1])
    return step > 0.0 and length >= step * MIN_PRIMITIVE_SPANS


def _join(pieces: list) -> list:
    """Concatenate consecutive slices that share an end point."""
    points = list(pieces[0])
    for piece in pieces[1:]:
        points.extend(piece[1:])
    return points


def _merge_arc_runs(segments: list) -> list:
    """Replace a string of arcs with the spline it is really approximating.

    A curve that is smooth but not circular - an ellipse, or the outline of a
    doubly curved panel - is fitted as a chain of short arcs, each within
    tolerance and none of them the actual shape. A run of them is worse geometry
    than one spline, and worse to machine from, so it is put back together. Two
    arcs in a row are left alone: that is an ordinary S of two fillets.
    """
    merged: list = []
    index = 0
    while index < len(segments):
        if segments[index][0] != "arc":
            merged.append(segments[index])
            index += 1
            continue
        end = index
        while end < len(segments) and segments[end][0] == "arc":
            end += 1
        if end - index >= MAX_CHAINED_ARCS:
            merged.append(
                ("spline", _join([piece for _k, piece in segments[index:end]]))
            )
        else:
            merged.extend(segments[index:end])
        index = end
    return merged


def _merge_slivers(segments: list, step: float) -> list:
    """Gather stretches that no primitive described into splines."""
    merged: list = []
    buffer: list = []

    def flush():
        if not buffer:
            return
        merged.append(
            ("line", buffer[0]) if len(buffer) < 2 else ("spline", _join(buffer))
        )
        buffer.clear()

    for kind, slice_points in segments:
        if kind == "spline" or _is_real_geometry(slice_points, step):
            flush()
            merged.append((kind, slice_points))
        else:
            buffer.append(slice_points)
    flush()

    # Two splines that ended up side by side describe one curve.
    joined: list = []
    for kind, slice_points in merged:
        if kind == "spline" and joined and joined[-1][0] == "spline":
            joined[-1] = ("spline", _join([joined[-1][1], slice_points]))
        else:
            joined.append((kind, slice_points))
    return joined


def segment_curve(points: list, tol: float, closed: bool = False) -> list:
    """Break a polyline into the longest straight and circular runs that fit.

    A flat pattern is mostly made of real geometry - a bolt hole is a circle, a
    filleted corner is an arc - and emitting all of it as fitted splines throws
    that away. Every stretch is measured against a line and against a circle and
    the primitive reaching furthest wins, so the sketch carries arcs and circles
    wherever the boundary genuinely has them.

    Where neither describes the shape, the greedy walk would slice a smooth
    curve into a string of two-point chords. Those are gathered back up into a
    spline instead, which is what keeps an organic outline organic.

    Greedy rather than optimal: it takes the longest primitive it can from each
    starting point rather than searching for the fewest segments overall.

    Args:
        points: (u, v) tuples in centimetres, unthinned.
        tol: Largest distance a point may sit from the primitive replacing it.
        closed: True when the chain is a closed loop.

    Returns:
        A list of ``(kind, points)`` where kind is "circle", "arc", "line" or
        "spline". A "circle" only ever appears alone, for a loop that is round
        the whole way.
    """
    if len(points) < 2:
        return []

    if closed and len(points) >= 3 and _fits_circle(points, tol):
        return [("circle", list(points))]

    chain = list(points)
    if closed and chain[0] != chain[-1]:
        chain.append(chain[0])

    step = _median_step(chain)
    segments: list = []
    start = 0
    limit = len(chain) - 1
    while start < limit:
        # A two-point line always fits, so it is the floor for both searches.
        line_end = start + 1
        index = start + 2
        while index <= limit and line_deviation(chain[start : index + 1]) <= tol:
            line_end = index
            index += 1

        arc_end = start + 1
        index = start + 3
        while index <= limit and _fits_circle(chain[start : index + 1], tol):
            arc_end = index
            index += 1

        if arc_end > line_end:
            segments.append(("arc", chain[start : arc_end + 1]))
            start = arc_end
        else:
            segments.append(("line", chain[start : line_end + 1]))
            start = line_end

    return _merge_slivers(_merge_arc_runs(segments), step)


def _loop_area(uvs: list, loop: list) -> float:
    """Signed area of a closed loop of flattened vertices (shoelace)."""
    total = 0.0
    for position, index in enumerate(loop):
        following = loop[(position + 1) % len(loop)]
        total += uvs[index][0] * uvs[following][1]
        total -= uvs[following][0] * uvs[index][1]
    return 0.5 * total
