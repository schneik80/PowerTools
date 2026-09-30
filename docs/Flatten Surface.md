# Flatten Surface

[Back to README](../README.md)

## Overview

Flatten Surface flattens curved faces into a flat pattern, previews how far the material has to stretch or gather, and creates a sketch of the result.

Fusion can already unfold sheet metal, because a bend is single-curvature and rolls out with no distortion. A doubly-curved face, a dome, a saddle, a boat hull, a shoe upper, has no exact flat form; it can only be approximated, and what matters is by how much and where. SolidWorks offers this as the Premium-tier **Flatten Surface** feature with its deformation plot; ExactFlat sells it as a dedicated product. Flatten Surface brings the same strain map into Fusion and finishes with real sketch geometry: lines, arcs and circles you can dimension and machine to, not a spline that merely looks like one.

> **Beta.** Tick **Show beta commands** under **General** in **File › PowerTools Preferences**, then enable **Flatten Surface** under **Part Modeling**, and restart Fusion.

## Prerequisites

- A design document must be open.

## Where to find it

**Utilities** tab › **Power Tools** panel › **Flatten Surface**, in the Design workspace.

## How to use

1. Pick a plane or planar face to **Place on**. The manipulator appears on that plane once it is picked.
2. Pick the **Faces** to flatten. Tick **Tangent chain** first if one click should take a whole smooth run.
3. Drag the manipulator to position the pattern on the plane.
4. Read the strain figures; adjust **Mesh quality** and **Relax pattern** to taste.
5. Select **OK** to create the sketch.

Faces that touch are flattened together as one piece, so a shape spanning several faces keeps its shared edges the right length. Faces that do not touch are laid out side by side as separate pieces. Each piece is squared up before it is placed, so a rectangular panel lands straight and landscape.

## Options

| Option | Default | Effect |
|---|---|---|
| **Place on** | — | The plane or planar face the pattern is drawn on |
| **Faces** | — | The faces to flatten, one or more |
| **Tangent chain** | Off | Picking one face also picks every face joined to it by a smooth edge, stopping at any sharp edge. It only ever adds: unticking it stops further chaining without undoing what is picked |
| **Mesh quality** | Medium | Coarse, Medium or Fine; finer locates distortion more precisely and follows the outline more closely, coarser previews faster |
| **Relax pattern** | On | Balances the error between shape and size, which is what a cut pattern usually wants. Off makes the flattening angle-true: every corner keeps its angle and all the error goes into size. It previews faster and typically doubles the average strain |
| **Show mesh** | Off | Draws the triangles the strain was measured on, to judge whether the mesh is fine enough to trust |
| **Export SVG** | — | Saves the strain map, outline, colour scale and headline figures to an SVG file (default name `<document name> flat pattern.svg`) without closing the dialog |

## Which shapes flatten exactly

A plane flattens exactly. So does a cylinder, a cone, and any number of them joined edge to edge: an extruded profile with filleted corners comes out with no strain at all and the dialog says **Flattens exactly.**

The exception is a point where three or more faces meet, like the corner of a box. The faces there enclose less than a full turn, and that shortfall is curvature no flat pattern can hold. The dialog names how many such corners there are and how much curvature they hold; a strain map on a shape like that is reporting geometry, not a fault. Strain from a corner is spread across the whole piece; turning **Relax pattern** off concentrates it instead.

Neighbouring faces are meshed independently, so where they sample a shared edge differently the pieces would meet at only a few points. Gaps up to 50 microns are closed before flattening and the dialog reports how many.

## Tubes and other closed shapes

A closed tube, a full cylinder or cone wall, has no flat form until it is cut. When cutting would reduce the strain, the tube is slit along the shortest seam between its two ends and the dialog says so; once slit it unrolls exactly. A hole is never cut open: a washer or a bossed bore is a closed ring too, but its rim goes round something, so rings keep their holes and carry whatever strain that costs. A fully closed shell such as a sphere has no open end to cut between and is not handled; split it into faces first.

## Reading the strain map

The preview is shaded by strain: how much the local size has to change between the surface and the flat pattern.

| Colour | Meaning |
|---|---|
| Blue | The material has to gather; the flat pattern is smaller here |
| Near-white | No distortion |
| Red | The material has to stretch; the flat pattern is larger here |

A developable face comes out white all over and the dialog says **Flattens exactly** rather than quoting zeros. Otherwise it reports the worst stretch, the worst gather and the average. The colour scale adapts to the part, so colours show where distortion is concentrated; it stops adapting below a tenth of a percent, which no material notices, so a part that flattens perfectly is not shown with its rounding error magnified.

When there is distortion, two labelled spheres mark the extremes: **Max** in red at the worst stretch and **Min** in blue at the worst gather, each with its percentage. Grey lines are the seams between the faces you selected. Whether the numbers are acceptable is a material question: woven fabric and leather absorb a few percent, sheet steel and carbon-fibre prepreg do not.

## What the sketch contains

A sketch named **Flatten Surface pattern**, on the plane you picked and positioned where you left the manipulator, in the active component:

| Geometry | What it is |
|---|---|
| Lines, arcs, circles and splines | The outline of the pattern and of any holes in it |
| Construction geometry | The seams between selected faces |
| Two sketch points | The worst stretch and the worst gather |

The outline is cut at its corners first, so a corner stays sharp. Each run then becomes the geometry it actually is: straight runs become lines, circular runs arcs, and a round hole a real circle, but only when the fit is exact, so the outline of a doubly-curved panel stays one spline rather than a chain of little arcs. Refining the mesh does not change which is which. Nothing else in the design is touched.

## Limitations

- The pattern is an approximation wherever the strain map is not white; that is the nature of the problem.
- If the layout folds back on itself the dialog warns with the count. Usually it means too many faces at once; flatten fewer at a time or refine the mesh.
- Faces must touch to be flattened together; coincidence is judged within 1 micron.
- The sketch outline follows the meshed boundary, not the exact edge; finer mesh, closer fit.
- The mesh is capped at about 4000 triangles: above that it is coarsened automatically, up to three times, and the dialog says so. For more detail, flatten fewer faces at a time.
- Placing onto a plane inside a component instance may land the pattern somewhere unexpected; place it on a top-level plane if so.

> **Developers:** see the [architecture notes](./arch/Flatten%20Surface.md).

---

[Back to README](../README.md)

*Copyright © 2026 IMA LLC. All rights reserved.*
