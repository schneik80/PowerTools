# Flatten Surface — Architecture

[← Flatten Surface guide](../Flatten%20Surface.md) ·
[Solver internals](../dev/Flatten%20Surface%20solver.md)

| | |
|---|---|
| **Command ID** | `PTPM_flattensurface` |
| **Registry group** | `partmodeling` (beta) |
| **Location** | The shared **Power Tools** panel, design **Tools** tab |
| **Modules** | `commands/flattensurface/entry.py`, `flatten.py`, `report.py` |
| **Tests** | `tests/test_flattensurface_flatten.py`, `_cracks.py`, `_report.py`, `_entry.py` |

The command tessellates the selected B-Rep faces, lays the resulting mesh flat,
measures the distortion that survives, previews it as a colour-shaded mesh on a
chosen plane, and on OK writes the outline into a sketch.

## Architecture

### System context

```mermaid
C4Context
    title System Context — Flatten Surface
    Person(user, "Fusion User", "Designer producing a flat pattern from curved faces")
    System(addin, "Flatten Surface", "Power Tools command that flattens faces and reports strain")
    System_Ext(fusion, "Autodesk Fusion", "CAD platform: B-Rep topology, tessellation, custom graphics, sketches")
    System_Ext(disk, "File system", "Destination chosen in a save dialog")
    Rel(user, addin, "Picks a plane, picks faces, drags the manipulator")
    Rel(addin, fusion, "Meshes faces, draws the preview, creates the sketch")
    Rel(fusion, user, "Shows the shaded pattern, markers and seams")
    Rel(addin, disk, "Writes an SVG strain map on request")
```

### Component diagram

The split is the repo's usual one: every Fusion call lives in `entry.py`, and
everything that can be reasoned about without Fusion lives in modules that import
no `adsk`, so they are unit-tested directly.

```mermaid
C4Component
    title Component Diagram — Flatten Surface
    Container_Boundary(ui, "entry.py — all adsk contact") {
        Component(created, "command_created()", "Python", "Builds the dialog, hides the triad until a plane exists")
        Component(changed, "command_input_changed()", "Python", "Captures picks, places the triad, invalidates the cache, runs export")
        Component(chain, "tangent_closure()", "Python", "Walks smooth neighbours so one pick takes a filleted run")
        Component(solve, "_solve()", "Python", "Tessellates, coarsens to budget, calls the solver, caches the result")
        Component(preview, "command_execute_preview()", "Python", "The ONLY place custom graphics are created")
        Component(mesh, "_draw_mesh()", "Python", "Vertex-coloured CustomGraphicsMesh of the flat pattern")
        Component(extremes, "_draw_extremes()", "Python", "Min/Max spheres with billboarded labels")
        Component(wire, "_draw_wireframe()", "Python", "One addLines entity for the whole triangulation")
        Component(stats, "_update_stats()", "Python", "Writes strain, cuts, gaps and curvature into the dialog")
        Component(sketch, "_create_sketch()", "Python", "Lines, splines, construction seams and marker points")
        Component(export, "_export_svg()", "Python", "Save dialog, then writes report.py output")
    }
    Container_Boundary(core, "flatten.py — no adsk import") {
        Component(weld, "weld_meshes()", "Python", "Spatial-hash vertex interning across faces")
        Component(stitch, "stitch_cracks()", "Python", "Re-cuts triangles around stranded vertices")
        Component(island, "split_islands()", "Python", "Connected components")
        Component(ring, "rings_a_hole()", "Python", "Boundary turning: a hole rim turns 2 pi, a tube end nothing")
        Component(cut, "cut_to_disk()", "Python", "Slits an open-ended patch along a shortest seam")
        Component(lscm, "lscm()", "Python", "Conformal layout via sparse least squares")
        Component(arap, "arap_relax()", "Python", "Local/global isometric relaxation")
        Component(sigma, "triangle_sigmas()", "Python", "Closed-form 2x2 singular values")
        Component(defect, "angle_defects()", "Python", "Curvature that cannot be flattened")
        Component(box, "tightest_box_angle()", "Python", "Squares each island up")
        Component(ramp, "strain_to_rgba()", "Python", "Diverging colour ramp with a floor")
        Component(meas, "is_measurable()", "Python", "Whether there is any distortion worth drawing")
        Component(seg, "segment_curve()", "Python", "Recovers lines, arcs and circles from the traced outline")
    }
    Container_Boundary(out, "report.py — no adsk import") {
        Component(svg, "svg_strain_map()", "Python", "Shaded polygons, outline and colour scale")
    }
    System_Ext(fusion, "Autodesk Fusion", "Tessellation, custom graphics, sketches")
    Rel(created, changed, "Registers handlers")
    Rel(changed, solve, "On a face, quality or relax change")
    Rel(solve, fusion, "BRepFace.meshManager")
    Rel(solve, weld, "Per-face meshes")
    Rel(weld, stitch, "Welded patch")
    Rel(stitch, island, "Sound patch")
    Rel(island, ring, "Per island, when not a disc")
    Rel(ring, cut, "Only when it is open ended")
    Rel(island, lscm, "Per island")
    Rel(lscm, arap, "Initial layout")
    Rel(arap, box, "Relaxed layout")
    Rel(solve, sigma, "Measures the result")
    Rel(solve, defect, "Explains what cannot improve")
    Rel(preview, mesh, "Draws")
    Rel(preview, extremes, "Draws when there is distortion")
    Rel(preview, wire, "Draws when Show mesh is on")
    Rel(mesh, ramp, "Per-vertex colours")
    Rel(preview, stats, "Updates the dialog")
    Rel(changed, chain, "When Tangent chain is ticked")
    Rel(sketch, seg, "Asks what each run really is")
    Rel(stats, meas, "Says exactly, or quotes the numbers")
    Rel(export, svg, "Builds the file")
```

### The pipeline

Every stage below runs on plain tuples. Each is individually testable, and each
exists because of a specific failure it prevents.

```mermaid
flowchart TD
    T[Tessellate each selected face] --> W[Weld coincident vertices]
    W --> S[Stitch cracks<br/>faces meshed unevenly]
    S --> I[Split into islands]
    I --> D{"Island a disc?<br/>V-E+F = 1"}
    D -->|yes| L[LSCM conformal layout]
    D -->|no| H{"Rings a hole?<br/>rim turns through 2 pi"}
    H -->|yes, keep the hole| L
    H -->|no, open ended| M{Distortion above<br/>the cut threshold?}
    M -->|no| L
    M -->|yes| C[Cut to disc along<br/>a shortest seam]
    C --> L2[LSCM] --> K{Cut lowered<br/>the strain?}
    K -->|yes| R
    K -->|no| L
    L --> R[ARAP relax, if enabled]
    R --> B[Rotate to tightest box,<br/>landscape]
    B --> P[Place islands side by side]
    P --> G[Measure strain from<br/>Jacobian singular values]
    G --> A[Measure angle defect]
    A --> O[Extract boundary loops and seams]
```

Three decisions in that flow refuse to be made structurally, and each was got
wrong first by trying:

| Decision | Why structure is not enough |
|---|---|
| Whether a non-disc may be cut | A washer and a tube are both annuli. Boundary turning separates them: a hole rim turns through `2*pi`, a tube end through nothing. Rings keep their holes whatever it costs, because a hole slit by mistake unrolls into a spiral. |
| Whether a cut was worth making | Even on an open-ended patch the cut is kept only if it lowers distortion. |
| Whether the strain is anyone's fault | A patch can be curved everywhere and still flatten exactly. Only the angle defect tells a genuine corner from a shape that was always flattenable. |

### What the sketch gets

The outline is traced from the mesh, so it arrives as a polyline. Turning it back
into geometry is a separate concern from flattening, and has its own failure mode
at each end: fit too eagerly and a smooth outline facets into chords, fit not at
all and a bolt hole becomes a spline that merely looks round.

```mermaid
flowchart TD
    B[Boundary loop or seam chain] --> X[Split at corners<br/>so a corner stays sharp]
    X --> Y{Whole loop fits<br/>one circle?}
    Y -->|yes| CI[Circle]
    Y -->|no| Z[Greedy: extend a line<br/>and an arc, take the longer]
    Z --> Q{"Fits far tighter<br/>than tolerance?"}
    Q -->|yes| P[Keep as line or arc]
    Q -->|no| SP[Gather into a spline]
```

The tightness test is the load-bearing one. Genuine geometry is *exact* — the
mesh points along a machined edge really are collinear — and fits to about a
millionth of the tolerance, while a chord laid across a curve uses a third of the
budget or more. Judging on that rather than on bare tolerance is what keeps the
answer stable as the mesh is refined; see
[the solver note](../dev/Flatten%20Surface%20solver.md#recognising-geometry-in-the-outline).

### Preview and commit

```mermaid
sequenceDiagram
    participant U as User
    participant F as Fusion
    participant E as entry.py
    participant C as flatten.py
    U->>F: Pick plane
    F->>E: inputChanged
    E->>E: _plane_frame(), show triad
    U->>F: Pick faces
    F->>E: inputChanged
    E->>C: _solve() - tessellate, flatten, measure
    C-->>E: FlattenResult (cached)
    F->>E: executePreview
    E->>F: customGraphicsGroups.add(), addMesh + vertex colours
    E->>F: TextBox stats
    U->>F: Drag the triad
    F->>E: executePreview
    Note over E: Cache hit - only the group transform changes
    U->>F: OK
    F->>E: execute
    E->>F: sketches.add(), lines, splines, points
```

The triad drag path is the reason the solve is cached: re-tessellating and
re-solving on every drag event would make the manipulator unusable. The cache key
is the face set plus the two solver settings, and it is safe because model
geometry cannot change while a command dialog is open.

## Implementation notes

### Custom graphics

The command follows
[Custom graphics that stay painted](../dev/Custom%20graphics%20that%20stay%20painted.md):
graphics are created **only** inside `executePreview`, and `isValidResult` is left
`False` so `execute` still runs and creates the sketch.

The mesh uses `CustomGraphicsVertexColorEffect` with a flat RGBA byte array on
`CustomGraphicsCoordinates.colors`. The wireframe overlay needs its **own**
coordinates object: reusing the mesh's would inherit those per-vertex colours and
paint the wireframe the exact colour of the surface beneath it. Depth priorities
order the layers — mesh, wireframe (1), seams (2), markers (3), labels (4).

### Tangent chaining

`BRepFace.tangentiallyConnectedFaces` reports only a face's **immediate** smooth
neighbours, so `tangent_closure()` walks outward breadth-first to reach a whole
filleted run, keyed by entity token because Fusion returns a fresh wrapper on
every access.

Two things make the expansion safe to run from `inputChanged`. Adding to a
selection input fires `inputChanged` again, so a re-entrancy flag stops the walk
calling itself; and the expansion only runs when the selection has **grown**,
which is what lets a user deselect a face without the chain instantly restoring
it. Neighbours are re-proxied into the seed's `assemblyContext`, since a proxied
face's neighbours may come back native and would then be measured in the wrong
space.

### The triad

`TriadCommandInput.isVisible` governs the input's **row in the dialog**, not the
manipulator in the viewport. `hideAll()` at creation is what keeps the handles off
screen until a plane is picked; without it a full triad sits at the world origin
and visibly reshapes itself on the first plane selection.

### Coordinate spaces

Selections are captured in `inputChanged` via `ptutil.capture_selections`, because
a `SelectionCommandInput` cannot be read reliably from `execute` (see
`lib/ptAddInUtils/selection_utils.py`).

The solver works in plain centimetres in root space. Sketch geometry is built in
model space from the placement plane's frame and then passed through
`sketch.modelToSketchSpace()`, rather than being written as sketch coordinates
directly — Fusion chooses the sketch's own axes, and they need not match the
frame, so writing directly can mirror or rotate the pattern.

### Performance

The solver is pure Python because Fusion's bundled interpreter has no pip, so
triangle count is the whole performance story. `_MAX_TRIANGLES` caps a solve at
roughly a second; past it the mesh is coarsened and the dialog says so. Mesh
fineness is expressed as a fraction of the selection's bounding-box diagonal, so
one quality setting behaves the same on a watch case and a boat hull.

The side-length cap matters as much as the sag tolerance: sag alone leaves a
planar face as two enormous triangles at any setting, which both conditions the
solver badly and leaves too few nodes along that face's edges to weld against a
finely meshed curved neighbour.

## Scope and limits

- **Closed shells are not handled.** A sphere has no open end for a seam to run
  between, so `cut_to_disk` cannot open it. Expect a poor pattern and no usable
  outline.
- **The outline follows the mesh**, not the exact B-Rep edge, so a finer mesh
  gives a closer fit. Runs between detected corners become lines when straight
  and fitted splines otherwise.
- **Distortion is a property of the surface.** Relaxation typically halves the
  average strain on a doubly-curved face; nothing removes it.
- **Only the sketch reaches the timeline.**

### Still unverified in Fusion

Each has a logged fallback rather than an exception.

| Item | Fallback |
|---|---|
| Placing onto a plane inside an occurrence | Proxy geometry reads in root coordinates while the sketch resolves against its parent component; documented as the least-tested path |
| `SketchFittedSpline.isClosed` on a corner-free loop | Logged; the spline stays open and visually closed |
| `CustomGraphicsBillBoard` for the Min/Max labels | Label still placed, orientation view-dependent |
| Whether `TriangleMeshCalculator` conforms across shared edges | `stitch_cracks` repairs it either way and reports what it closed |

---

*Copyright © 2026 IMA LLC. All rights reserved.*
