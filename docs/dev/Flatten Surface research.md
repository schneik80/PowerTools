# Flatten Surface — background research

Research compiled 2026-08-29 for a planned PowerTools "Flatten Surface" command:
select one or more curved faces, flatten them to a planar pattern, preview a
shrink/expand (strain) color map, and commit a sketch of the flattened outline.
All URLs were verified by live fetch on 2026-08-29; dead or misremembered items
were dropped or flagged.

Feature intent (from the maintainer):

- Pick one or more faces.
- Pick a placement plane; a manipulator moves the preview in the plane's X/Y
  (not WCS).
- Preview the strain map live; on commit, generate a sketch outline of the
  flattened geometry.
- Candidate preview mechanisms considered: (a) duplicate body / OBJ import with
  material, (b) HTML palette, (c) realtime temporary custom graphics on the
  plane. Research verdict below: (c) is the right route; (a) is not viable.

---

## 1. The problem in one paragraph

Flattening a doubly-curved surface is mesh parameterization: tessellate the
face(s), compute a 2D layout that minimizes a distortion energy, then measure
the distortion that remains. Conformal methods (LSCM, ABF++, BFF) preserve
angles and push all error into area (shrink/expand) — exactly the quantity to
color-map. Isometric methods (ARAP, SLIM) balance angle and area error and are
what fabrication wants. Fabric-specific methods (fishnet/Chebyshev draping,
woven-net strain-energy release) additionally model yarn shear. Distortion is
universally derived from the per-triangle Jacobian's singular values s1 >= s2:
s1*s2 = area ratio (signed shrink/expand, diverging colormap), s1/s2 = shear
(sequential colormap). For near-developable CAD surfaces every method converges
to near-zero distortion; the color map is precisely the "how non-developable is
this" signal.

---

## 2. Open-source libraries (mesh parameterization)

Scope notes that apply to every entry: these are mesh parameterizers — NURBS
faces must be tessellated first; each chart must be a topological disk (closed
surfaces need seams/cuts or cone singularities).

| Library | License | Language | Algorithms | Distortion output |
|---|---|---|---|---|
| libigl (github.com/libigl/libigl) | MPL-2.0 (some GPL) | C++ header-only | harmonic, LSCM, ARAP, SLIM, SCAF, MIQ | build from Jacobians |
| libigl Python (`pip install libigl`) | GPL/MPL | compiled wheels | `igl.lscm`, harmonic, ARAP; SLIM varies by release | ~20 lines of numpy |
| Boundary First Flattening (github.com/GeometryCollective/boundary-first-flattening) | MIT | C++ (SuiteSparse) | BFF conformal, boundary control, cones, minimal-area-distortion mode | best in class: viewer shows white=none, blue=shrink, red=expand; per-vertex log conformal factor u, e^(2u) = local area scaling |
| CGAL Surface Mesh Parameterization | GPL | C++ | Tutte, authalic, MVC, LSCM, ARAP, Orbifold-Tutte (no ABF++) | none built in |
| geometry-central (geometry-central.net) + polyscope | MIT | C++ | BFF incl. scale-factor variants | scale factors; polyscope renders scalar colormaps |
| Blender bpy | GPL-2+ | app | `uv.unwrap`: ANGLE_BASED (ABF++), CONFORMAL (LSCM), 4.3+ MINIMUM_STRETCH (SLIM) | "Display Stretch" overlay is UI-only; recompute in script; fully headless-scriptable (`blender --background --python`) |
| xatlas (github.com/jpcy/xatlas) | MIT | C++ vendorable (1 cpp + 1 h) | auto chart segmentation + LSCM + packing | none; atlas output, not a single panel |
| mouette (github.com/GCoiffier/mouette) | MIT | pure Python (needs numpy/scipy) | Tutte, LSCM, BFF, cones, cutting | dedicated distortion-measurement module — only Python lib with this built in |
| confmap (github.com/russelmann/confmap) | MIT | pure Python (numpy/scipy) | CETM + BFF | log scale factors + quasi-conformal error; best readable reference text |
| Easy3D | GPL-3 | C++ w/ Py bindings | harmonic, LSCM | none |
| PMP library | MIT | C++ | harmonic, LSCM | none |
| OpenMesh/OpenFlipper | BSD-3/LGPL | C++ | none (data structure only) | — |
| PyMeshLab | GPL-3 | pip wheels | atlas-oriented filters | none for UVs |

Not candidates: potpourri3d has no parameterization (geodesics only);
gpytoolbox's ARAP is roadmap-only; trimesh's `unwrap()` is just an xatlas
wrapper.

Key conclusion for PowerTools: nothing off the shelf is stdlib-only. Every
pure-Python option leans on numpy/scipy. Realistic strategies for Fusion's
embedded no-pip CPython:

1. Port/hand-roll: LSCM is one sparse linear least-squares solve; with a
   hand-written conjugate-gradient solver it is feasible for meshes of a few
   thousand triangles (slow but fine for a command preview). confmap and
   mouette are the reference texts; FreeCAD's flatmesh is the C++ blueprint.
2. Shell out: the BFF CLI is a single small MIT executable (OBJ in, flattened
   OBJ out) with the best distortion output; headless Blender is an
   alternative. Both mean shipping/locating an external binary.
3. Dev-side only: `pip install libigl` in `.venv-dev` as a ground-truth
   comparison harness for tests, never at runtime.

---

## 3. CAD / fabrication-specific methods

FreeCAD ecosystem:

- flatmesh / LscmRelax (looooo; FreeCAD `src/Mod/MeshPart/App/MeshFlatteningLscmRelax.cpp`,
  LGPL, C++/pybind11): LSCM initial layout + nonlinear FEM stress relaxation —
  the "sprung-back pattern" pipeline, written for OpenGlider paraglider panels.
  Best single-file algorithmic blueprint found.
- SheetMetal workbench (github.com/shaise/FreeCAD_SheetMetal, LGPL, Python):
  exact bend-graph development with K-factor tables; developable-only, zero
  strain by definition. Reusable unfold-tree bookkeeping patterns.
- Curves workbench Flatten Face (github.com/tomate44/CurvesWB, LGPL): unrolls
  developable/near-developable NURBS faces; documented to fail on genuinely
  doubly-curved faces.
- OpenGlider (GPL-3, Python): production proof that Python flat-pattern
  pipelines ship (panel segmentation -> flatten -> seam allowance -> DXF).
  GPL: architecture reference only.

Academic methods with open code:

- BFF (MIT, C++) — see table above. Also mattj23/bf-flatten-service: BFF as an
  HTTP microservice (an integration pattern worth remembering).
- ARAP parameterization (Liu et al. 2008, eecs.harvard.edu/~sjg/papers/arap.pdf;
  in libigl): best pure-Python port target overall. Local step = per-triangle
  closed-form 2x2 SVD; global step = one prefactored cotan-Laplacian SPD solve
  (CG acceptable at a few thousand triangles). LSCM init + ARAP iterations +
  sigma-based strain map is effectively an open Rhino-Squish clone.
- SLIM (igl.ethz.ch/projects/slim, GPL ref impl, MPL via libigl; shipped as
  Blender 4.3 "Minimum Stretch"): symmetric Dirichlet isometric energy,
  guaranteed injectivity — the energy class fabrication wants.
- ABF++ (OpenABF, single-header C++, GPL): harder port, less fabrication-
  relevant than isometric energies.
- Wang C.C.L., "Freeform surface flattening based on fitting a woven mesh
  model" (CAD 2004, mewangcl.github.io/pubs/CADFlatten04.pdf): Chebyshev woven
  net fit + spring-mass strain-energy release — the documented ExactFlat-style
  pipeline. Most portable industrial algorithm: loops-and-arrays pure Python,
  no sparse solver, and strain output is intrinsic. WireWarping (CAD 2008):
  length-preserved seam curves. Papers only; no maintained open code.
- Developability optimization (Stein/Grinspun/Crane 2018, MIT C++,
  github.com/odedstein/DevelopabilityOfTriangleMeshes): deform a mesh toward
  piecewise-developable before unrolling — a possible v2+ "make flattenable"
  feature, not v1.

Cloth/composite draping:

- KinDrape (github.com/chrkrogh/KinDrape, permissive/cite-required): kinematic
  pin-jointed-net (fishnet/Chebyshev) draping, ~100 lines, Python version in
  repo, outputs per-cell shear angles. Highest immediate-feasibility item in
  the whole survey; mold sampling maps to Fusion `SurfaceEvaluator`.
- Chebyshev Parameterization for Woven Fabric (Sorkine-Hornung group, SIGGRAPH
  Asia 2024, igl.ethz.ch/projects/chebyshev, C++, license unstated): SOTA
  anisotropic yarn-direction energy; port the energy, not the code.

Papercraft: Blender "Export Paper Model" (github.com/addam/Export-Paper-Model-from-Blender,
GPL, pure Python): rigid isometric unfolding into near-developable islands with
overlap splitting, packing, SVG/PDF. Right algorithm shape for "segment into
strips, unfold each exactly" — reimplement, do not copy (GPL).

Fusion ecosystem gap:

- Native Fusion: sheet-metal flat pattern only; doubly-curved surfaces have no
  path (official workaround article confirms).
- ExactFlat's 2015 Fusion plugin appears discontinued; their site now
  emphasizes SolidWorks/Rhino/Onshape. The Fusion slot is effectively vacant.
- mschafer/SurfaceDevelopment (MIT, Python, dormant): developable-only Fusion
  script, no strain output. No open-source doubly-curved flattener with strain
  output exists for Fusion.

Commercial parity spec (from ExactFlat marketing + Rhino Squish docs,
docs.mcneel.com/rhino/8/help/en-us/commands/squish.htm):

1. Flat pattern geometry (sketch/DXF).
2. Per-face strain map with stretch/compression sign (Squish: red=compression,
   green=stretch, top-10 text dots).
3. Summary stats + worst-spot markers.
4. Length-preserved boundary/seam option (WireWarping-style).
5. Map-back of 2D annotations onto the 3D surface (SquishBack).
6. Material bias (stretch-favoring vs compression-favoring).

License watch: MIT/permissive — BFF, confmap, KinDrape, Developability,
mschafer, xatlas, mouette. GPL (reimplement from papers, never copy) — SLIM
reference impl, OpenABF, Blender add-ons, OpenGlider, PyMeshLab. Unstated —
woven-fabric-chebyshev, vincentBenet/flatten_surface.

---

## 4. Distortion math and color mapping

### 4.1 Per-triangle Jacobian singular values (the master quantity)

Reference: Sander, Snyder, Gortler, Hoppe, "Texture Mapping Progressive
Meshes" (SIGGRAPH 2001), hhoppe.com/tmpm.pdf. For the 3D->2D direction: build
an orthonormal frame in each 3D triangle's plane, express the triangle in local
2D coords, solve the 2x2 system mapping local 3D edge vectors to 2D pattern
edge vectors -> Jacobian J. With a = J11^2 + J21^2, b = J11*J12 + J21*J22,
c = J12^2 + J22^2:

    sigma_max/min = sqrt( ((a+c) +/- sqrt((a-c)^2 + 4b^2)) / 2 )

Closed form — no SVD library needed.

| Property | Condition | Scalar to plot |
|---|---|---|
| Isometric | s1 = s2 = 1 | — |
| Conformal (angles kept) | s1 = s2 | shear s1/s2 (sequential map) |
| Equiareal | s1*s2 = 1 | area factor s1*s2 = det J = A2D/A3D (diverging map) |

- Signed area strain for display: `sqrt(s1*s2) - 1` (percent, linear,
  industry-friendly) or `log(s1*s2)` (symmetric multiplicative form).
- Engineering framing: Green-Lagrange E = (J^T J - I)/2; principal strains
  eps_i = sigma_i - 1 (what ExactFlat-class tools report as % strain).
- Quasi-conformal error: K = s1/s2; Beltrami |mu| = (s1-s2)/(s1+s2).
- Composites color shear angle (warp/weft deviation from 90 deg) instead —
  predicts dart/splice locations.
- Tissot indicatrix (cartography): same math; small ellipses on a grid show
  the direction of stretch, which scalar color cannot. Optional glyph overlay.
- One scalar cannot capture both area and shear unless the map is conformal
  (BFF's case, where the per-vertex log conformal factor u is the whole story).
- Area-only shortcut: no Jacobian needed at all — per-face
  `abs(area2D) / area3D`.

### 4.2 Precedents in existing tools

- BFF viewer: area-distortion mode, white = none, blue = shrink, red = expand;
  prints avg/max log conformal factor. Closest precedent for the target UX.
- Blender "Display Stretch" (source: `extract_mesh_vbo_edituv_stretch_area.cc`
  and `_angle.cc`): area mode compares per-face uvarea/area3d against the
  global ratio (so uniform scale reads as zero distortion); angle mode uses
  per-corner |theta2D - theta3D|/pi. Uses an unsigned spectral ramp (a design
  wart; do not copy the ramp).
- MeshLab: per-face quality -> colorize, with two reusable normalization
  ideas: percentile clip (e.g. 2-98%) and zero-symmetric range (neutral color
  pinned at exactly 0).
- polyscope: `addFaceScalarQuantity` + checker/grid parameterization styles.

### 4.3 Colormap guidance

- Diverging map centered at 0: blue = compression, white = neutral,
  red = stretch. Candidates: Moreland coolwarm/"Fast" (public-domain tables,
  kennethmoreland.com/color-advice), ColorBrewer RdBu, Crameri vik/berlin
  (MIT, colorblind-safe; berlin suits dark themes).
- Avoid jet/rainbow: non-monotonic lightness creates false edges and hides
  small strain deltas; not colorblind-safe.
- Normalization: symmetric range about 0 with percentile clipping, or a fixed
  material-tolerance range (e.g. +/-3% strain) so color meaning is constant
  across parts (manufacturing go/no-go).
- Unsigned quantities (s1/s2, shear angle) get a sequential map, not
  diverging.
- Per-face flat color = honest/diagnostic; per-vertex averaged (area-weighted
  average of incident faces) = smooth presentation. Offer face mode for
  diagnosis if both are cheap.

### 4.4 Pure-stdlib recipes (no numpy)

Per-face singular values (math module only):

```python
import math

def tri_area_3d(q1, q2, q3):
    ux, uy, uz = (q2[0]-q1[0], q2[1]-q1[1], q2[2]-q1[2])
    vx, vy, vz = (q3[0]-q1[0], q3[1]-q1[1], q3[2]-q1[2])
    cx, cy, cz = (uy*vz-uz*vy, uz*vx-ux*vz, ux*vy-uy*vx)
    return 0.5 * math.sqrt(cx*cx + cy*cy + cz*cz)

def tri_area_2d(p1, p2, p3):  # signed; abs() for magnitude, sign<0 => flipped
    return 0.5 * ((p2[0]-p1[0])*(p3[1]-p1[1]) - (p3[0]-p1[0])*(p2[1]-p1[1]))

def face_singular_values(q1, q2, q3, p1, p2, p3):
    """sigma1 >= sigma2 of the 3D->2D map for one triangle."""
    e1 = (q2[0]-q1[0], q2[1]-q1[1], q2[2]-q1[2])
    L = math.sqrt(sum(c*c for c in e1)); e1 = tuple(c/L for c in e1)
    w = (q3[0]-q1[0], q3[1]-q1[1], q3[2]-q1[2])
    d = sum(w[i]*e1[i] for i in range(3))
    e2 = tuple(w[i]-d*e1[i] for i in range(3))
    L2 = math.sqrt(sum(c*c for c in e2)); e2 = tuple(c/L2 for c in e2)
    u1 = (p2[0]-p1[0], p2[1]-p1[1]); u2 = (p3[0]-p1[0], p3[1]-p1[1])
    det = L*L2
    inv = ((L2/det, -d/det), (0.0, L/det))
    J = ((u1[0]*inv[0][0] + u2[0]*inv[1][0], u1[0]*inv[0][1] + u2[0]*inv[1][1]),
         (u1[1]*inv[0][0] + u2[1]*inv[1][0], u1[1]*inv[0][1] + u2[1]*inv[1][1]))
    a = J[0][0]**2 + J[1][0]**2
    b = J[0][0]*J[0][1] + J[1][0]*J[1][1]
    c = J[0][1]**2 + J[1][1]**2
    s = math.sqrt(max((a-c)**2 + 4*b*b, 0.0))
    return math.sqrt(max((a+c+s)/2, 0.0)), math.sqrt(max((a+c-s)/2, 0.0))
```

Diverging scalar -> RGB (extend with more Moreland control points for better
perceptual behavior; his CSV tables are public domain):

```python
_COOLWARM = [(0.0, (59, 76, 192)), (0.5, (221, 221, 221)), (1.0, (180, 4, 38))]

def diverging_rgb(x, vmax):
    """x = signed strain; vmax = symmetric clip (e.g. 0.03 for +/-3%)."""
    t = max(0.0, min(1.0, (x + vmax) / (2 * vmax)))
    for (t0, c0), (t1, c1) in zip(_COOLWARM, _COOLWARM[1:]):
        if t <= t1:
            f = (t - t0) / (t1 - t0)
            return tuple(round(a + f * (b - a)) for a, b in zip(c0, c1))
    return _COOLWARM[-1][1]
```

Percentile normalization mirroring MeshLab: sort per-face values, take
`lo = values[int(0.02*n)]`, `hi = values[int(0.98*n)]`,
`vmax = max(abs(lo), abs(hi))`.

An SVG renderer (one colored `<polygon>` per face, f-strings only) was also
prototyped in research — useful if a printable strain report or palette view is
ever wanted; details in the research transcript. Gotchas recorded: flip Y;
same-color hairline stroke to kill antialiasing cracks; bucket faces by
quantized color into few `<path>` elements above ~50k faces.

### 4.5 Export conventions (future DXF/report work)

- DXF: semantic layers (outer profile / interior / bends / annotations) —
  cutters key off layers, not colors. Distortion belongs on annotation layers
  as out-of-tolerance outlines, dart/splice lines, fiber ticks; never colored
  fill on cut layers.
- Composites practice (FiberSIM/Ansys ACP/Creo): DXF for the cutter plus a
  PDF/SVG "strain report" page with the colored pattern and a legend.

---

## 5. Fusion API verification (help.autodesk.com, fetched 2026-08-29)

- Tessellation per face: VERIFIED. `BRepFace.meshManager` ->
  `createMeshCalculator()` -> `TriangleMeshCalculator` (`surfaceTolerance` in
  cm, `maxSideLength`, `maxNormalDeviation`, `maxAspectRatio`, or
  `setQuality(LOD)`) -> `TriangleMesh` with `nodeCoordinatesAsDouble`,
  `nodeIndices`, `normalVectors`, and `textureCoordinates` (per-node surface
  UVs, free).
- Custom graphics with per-vertex colors: VERIFIED — the right preview route.
  `Component.customGraphicsGroups.add()` -> `group.addMesh(coords, indexList,
  normals, normalIdx)`; `CustomGraphicsCoordinates.colors` = flat RGBA byte
  array (one per vertex) + `CustomGraphicsVertexColorEffect.create()` assigned
  to the mesh `.color`; colors blend across triangles. Graphics created inside
  `executePreview` are rolled back automatically each recompute/cancel;
  graphics made elsewhere need explicit `deleteMe()` in destroy. Perf: cache
  tessellation, update one group instead of create/delete churn (forum-
  reported lingering slowdown after heavy churn).
- Manipulator: VERIFIED. `TriadCommandInput` (May 2022+): `hideAll()` then
  enable only X/Y translation + XY planar move; read `transform` /
  `positionTransform` / `lastTransform`, `xTranslation`/`yTranslation` (cm).
  Pattern: create hidden, set transform to the placement plane's coordinate
  system, then show. Fallback: two
  `DistanceValueCommandInput.setManipulator(origin, dir)` arrows.
- Selection: VERIFIED. Face input: filter `Faces`/`SolidFaces`,
  `setSelectionLimits(1, 0)`. Plane input: filters
  `["PlanarFaces", "ConstructionPlanes"]` (OR), limits (1, 1) — auto-advances
  focus when satisfied. Manage `hasFocus` in `inputChanged`; `addSelection`
  cannot be called from `commandCreated` (use `activate`).
- Sketch output: VERIFIED. `Component.sketches.add(planeOrPlanarFace)`;
  `sketchFittedSplines.add(ObjectCollection of Point3D)`; geometry is in
  sketch space — place flattened 2D coords as `Point3D(x, y, 0)` after
  checking `sketch.xDirection`/`yDirection`/`origin`, or use
  `modelToSketchSpace`. Bulk perf: `sketch.isComputeDeferred = True` around
  creation.
- OBJ-with-material preview: REJECTED. `MeshBodies.add` imports OBJ/STL/3MF
  but per-vertex colors are dropped (forum + support articles confirm); only
  texture/MTL colors are partially honored; no live drag/update either.
- Evaluator: VERIFIED. `BRepFace.evaluator` (use plural batch methods for
  mesh-sized sets), `parametricRange`, `isParamReversed` (flip orientation
  when true), `face.area` (cm^2), boundary via `face.loops` -> edges ->
  `CurveEvaluator3D`.
- Dialog feedback: VERIFIED. Read-only `TextBoxCommandInput` (basic HTML) for
  min/max strain stats; `ImageCommandInput` (PNG, display-only, `imageFile`
  swappable) for a color-legend strip.
- Cross-cutting: all API units are cm and radians. For a graphics-only
  preview leave `isValidResult` False so `execute` runs (see
  docs/dev/Custom graphics that stay painted.md for the house rules).

---

## 6. Synthesis for PowerTools

- Preview: custom graphics mesh with per-vertex strain colors during
  `executePreview`, positioned via a TriadCommandInput restricted to the
  placement plane's X/Y. Palette and OBJ routes rejected (viewport is where
  the map belongs; OBJ drops vertex colors).
- Solver: pure-Python `flatten.py` with zero adsk imports (plain vertex/index
  tuples in cm), LSCM via hand-rolled sparse CG, optional ARAP local/global
  iterations for fabrication-quality patterns; strain from the closed-form
  singular values above. Practical budget: hundreds to low-thousands of
  triangles per patch, controlled by tessellation tolerance.
- Validation: libigl in `.venv-dev` as a dev-side ground-truth harness for the
  solver's unit tests; analytic cases (cylinder segment flattens isometrically,
  sphere cap has known strain sign) as pytest fixtures.
- Commit: sketch on the placement plane; boundary loops chained from the
  welded patch's boundary edges, emitted as fitted splines with
  `isComputeDeferred` around bulk creation.
- Market context: Fusion has no native or third-party doubly-curved flattener
  with a strain map; ExactFlat's Fusion plugin is gone. The parity checklist
  in section 3 is the long-term feature yardstick.
