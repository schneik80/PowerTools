# Flatten Surface

Lays **curved faces flat**, shows **where the material has to stretch or gather**
to get there, and creates a **sketch of the flat pattern**.

Fusion can already unfold sheet metal, because a bend is single-curvature: it
rolls out with no distortion at all. A doubly-curved face — a dome, a saddle, a
boat hull, a shoe upper — has no such flat form. It can only be *approximated*
by one, and what matters is knowing by how much, and where. That is what this
command reports.

**Location:** the **Power Tools** panel, on the design **Tools** tab.

> **Beta.** Enable it under **Part Modeling** in PowerTools Preferences.

---

## Using it

1. Pick a plane or planar face to **Place on**. Nothing can be previewed until
   there is somewhere to draw the pattern, so this comes first; the
   **manipulator** appears on that plane once it is picked.
2. Pick the **Faces** to flatten.
3. Drag the manipulator to position the pattern on the plane.
4. Read the strain figures, adjust **Mesh quality** and **Relax pattern** to taste.
5. **OK** creates the sketch.

Faces that touch are flattened **together as one piece**, so a shape spanning
several faces keeps its shared edges the right length. Faces that do not touch
are laid out side by side as separate pieces.

Each piece is squared up before it is placed, so a rectangular panel lands
straight and landscape rather than at whatever angle the solver happened to
finish at.

## Why a shape made only of planes and cylinders can still show strain

A plane flattens exactly. So does a cylinder. So does any number of them joined
edge to edge — an extruded profile with filleted corners comes out with no
strain at all.

The exception is a **point where three or more faces meet**, like the corner of
a box. The faces there enclose less than a full turn — three square corners give
270 degrees, so 90 are missing — and that shortfall is curvature. No flat
pattern can hold it, and no software can remove it. The dialog now says so
explicitly, naming how many such corners there are and how much curvature they
hold, so a strain map like that reads as geometry rather than as a fault.

Strain from a corner is spread across the whole piece rather than piled up at
the corner, so flat faces near one will show some too. Turning **Relax pattern**
off concentrates it instead, which is sometimes easier to interpret.

Separately, neighbouring faces are meshed independently, and where they sample a
shared edge differently the pieces would be joined at only a few points. Those
gaps are found and closed before flattening, and the dialog reports how many —
you should never see the irregular pattern they used to cause.

## Tubes and other closed shapes

A closed tube — a full cylinder or cone wall — has **no flat form at all** until
it is cut, the same reason you slit a paper towel roll to flatten it. Select one
and it is slit automatically along the shortest seam between its two ends, and
the dialog says so. Once slit it unrolls **exactly**, with no distortion,
because a tube is developable.

The cut is only made when it actually helps. A flat washer is a closed ring in
exactly the same sense, but it is already flat, so it is left whole and its hole
stays a hole.

A fully closed shell such as a sphere has no open end to cut between and is not
handled: expect a poor pattern and no usable outline. Split it into faces first.

## Reading the strain map

The preview is shaded by **strain**: how much the local size has to change
between the surface and the flat pattern.

| Colour | Meaning |
|---|---|
| Blue | The material has to **gather** — the flat pattern is smaller here |
| Near-white | No distortion; this part flattens truthfully |
| Red | The material has to **stretch** — the flat pattern is larger here |

A **developable** face — a cylinder, a cone, an extruded profile — comes out
white all over, because it genuinely flattens with no distortion, and the dialog
says **"Flattens exactly"** rather than quoting a row of zeroes. Colour means
double curvature, and the strength of the colour is how much of it there is.
Otherwise the dialog reports the worst stretch, the worst gather, and the
average.

The scale adapts to the part, so the colours show where the distortion is
concentrated rather than how it compares against some fixed range. It stops
adapting below a tenth of a percent, which no material notices — otherwise a
part that flattens perfectly would have its rounding error magnified into a
full-strength map.

Two labelled spheres mark the extremes: **Max** in red at the worst stretch,
**Min** in blue at the worst gather, each carrying its percentage. On a large
pattern with a gentle gradient those spots are genuinely hard to find by eye,
and they are what decides whether the pattern is usable. Both labels turn to
face you from any viewpoint and hold their size as you zoom.

Grey lines across the preview are the **seams**: the joins between the faces you
selected.

**Show mesh** draws the triangles the strain was actually measured on. Turn it
on to judge whether the mesh is fine enough to trust — a strain map is only as
detailed as the mesh under it.

Whether those numbers are acceptable is a material question, not a geometric
one. Woven fabric and leather absorb a few percent without complaint; sheet
steel and carbon-fibre prepreg do not.

## What the sketch contains

| Geometry | What it is |
|---|---|
| Lines and splines | The outline of the pattern, and of any holes in it |
| Construction geometry | The seams between selected faces |
| Two sketch points | The worst stretch and the worst gather |

The outline is **cut at its corners** and each run between two corners is drawn
separately: straight runs become lines, curved runs become splines. That is what
keeps a corner sharp. Fitting one spline around a whole outline would average
every corner away and the pattern would lose its shape.

The sketch is created on the plane you picked, positioned where you left the
manipulator. Nothing else in the design is touched.

## Mesh quality

The faces are meshed before being flattened, and that mesh is what gets
measured. **Finer** locates the distortion more precisely and follows the
outline more closely; **coarser** previews faster.

The solver runs inside Fusion's Python, so cost rises steeply with triangle
count. Past a working budget the mesh is coarsened automatically and the dialog
says so — a coarser answer beats a frozen dialog. If you need more detail than
that allows, flatten fewer faces at a time.

## Relax pattern

**On** (the default) balances the error between shape and size, which is what a
cut pattern usually wants.

**Off** makes the flattening **angle-true**: every corner keeps its angle, and
all of the error is pushed into size instead. It previews faster, and it is the
better choice when angles matter more than areas.

Relaxing typically halves the average strain on a doubly-curved face. It cannot
remove it — no method can, because the distortion is a property of the surface
rather than of the algorithm.

## Export SVG

Saves the strain map — the shaded pattern, its outline, a colour scale and the
headline figures — to a file you choose. SVG opens in any browser and prints
without going fuzzy at any size.

The button works whenever faces are selected, so you can export without
committing a sketch. It does not close the dialog.

## Notes and limits

- **The pattern is an approximation** wherever the strain map is not white. That
  is the nature of the problem, not a defect — see the colour table above.
- **Folded patterns are reported, not hidden.** If the layout turns back on
  itself the dialog warns and the count appears in the report. Usually it means
  too many faces at once, or a face with a slit in it; flatten fewer at a time.
- **Faces must touch to be flattened together.** Coincidence is judged within 1
  micron (0.0001 cm), the same tolerance Measure Path uses.
- The sketch outline is fitted through the meshed boundary, so it follows the
  mesh rather than the exact edge. Finer mesh, closer fit.
- **Placing onto a plane inside a component instance** is the least-tested
  path; if a pattern lands somewhere unexpected, place it on a top-level plane
  instead.
- Nothing is added to the timeline except the sketch.

## Preferences

Listed under **Part Modeling** in **PowerTools Preferences**. As a beta command
it appears only when beta commands are enabled.

---

*Background and method sources:
[docs/dev/Flatten Surface research.md](dev/Flatten%20Surface%20research.md).*

*Copyright © 2026 IMA LLC. All rights reserved.*
