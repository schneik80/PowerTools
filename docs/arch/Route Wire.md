# Route Wire — Architecture
[← Route Wire guide](../Route%20Wire.md)

## Purpose

Second half of the cable prove-out: consume the `PowerTools.Cable` attributes
written by [Define Wires](./Define%20Wires.md) from *assembly* context, and
build real wire geometry from them. The schema module
`commands/definewires/logic.py` stays the single source of truth; this
command imports it as `schema`. Route-specific pure logic (AWG math, gauge
intersection, spline guide points, route payload) lives in
`commands/routewire/logic.py` with tests in `tests/test_routewire_logic.py`.

## How connector data is read (and why not findAttributes)

Whether `design.findAttributes` reaches into referenced (XRef) documents was
left an open question by Define Wires. Route Wire sidesteps it: the user
*selects* the two occurrences, so the command scans just those components
directly — every construction point and sketch point of `occurrence.component`
is checked for attributes in the `PowerTools.Cable` group
(`entry._iter_component_points` / `_cable_attrs_on`). This works identically
for referenced and local components. Only **complete** wires (all three roles
present, non-empty pin) are offered for routing.

World positions come from occurrence proxies:
`entity.createForAssemblyContext(occ)` then `.geometry` (construction points)
or `.worldGeometry` (sketch points) — both in root space, however deeply the
occurrence is nested.

## Geometry construction

All new components are created with identity transforms, so component-local
coordinates equal root (world) coordinates; every point is still mapped
through `sketch.modelToSketchSpace` before sketching.

- **Conductor** component — one 3D sketch (`Wire <name> conductor paths`)
  with a start-to-strip line per connector; each line becomes a Path
  (`Features.createPath(line, False)`) swept as a solid circular **Pipe**
  feature at the bare AWG diameter (`logic.conductor_diameter_mm`, the
  standard `0.127 mm * 92^((36-AWG)/39)` formula).
- **Sheath** component — one 3D sketch (`Wire <name> sheath path`): line
  strip1-to-exit1, line strip2-to-exit2, and an exit1-to-exit2 fitted spline.
  The spline is made smooth against both lines by *fixing the lines*
  (`isFixed`, so the solver bends the spline, not the connector geometry) and
  adding coincident + tangent constraints. The API does not document
  3D-sketch constraint support, so any constraint failure falls back to an
  unconstrained spline shaped by directional guide points
  (`logic.spline_guide_points`: interior fit points continuing each
  strip-to-exit direction past the exit by 25% of the exit-to-exit span).
  The three curves are collected into one Path
  (`createPath(ObjectCollection, False)` — endpoint-connected curves) and
  swept as a Pipe at the user's sheath diameter.

**Pipe instead of manual sweep.** The described "sweep a circle along the
path" is implemented with `PipeFeatures` (path + solid circular section),
Fusion's native feature for exactly this — it removes the
plane-profile-alignment failure surface of a manual sweep.
**VERIFY AT RUNTIME:** `PipeFeatureInput.sectionSize` is assumed to be the
section **diameter** (matching the UI's "Section Size"); the API docs do not
specify radius vs diameter. If pipes come out double/half size, halve/double
the `ValueInput` in `entry._add_pipe`.

## Structure, naming, timeline

```text
Root
  Wire <name>     component, stamped with the route attribute
    Conductor     bodies "Wire <name> conductor 1|2"
    Sheath        body  "Wire <name> sheath"
```

`design.timeline.markerPosition` is captured before any creation; afterwards
everything from that index on is grouped via `timelineGroups.add` and the
group is named `Wire <name>`. (True `CustomFeature` API packaging —
definition registration plus compute handlers — was judged out of scope for a
prove-out; the timeline group delivers the "one named unit in the timeline"
behavior.) Grouping requires a parametric design, which command_created
enforces.

## Route attribute (schema v1 addition)

Stamped on the `Wire <name>` component: group `PowerTools.Cable`, name
`route`, JSON value:

```json
{"schema": 1, "name": "PWR1", "awg": 22, "od_mm": 1.54,
 "ends": [
   {"connector_id": "ConnA-3f9a2b1c", "wire_id": "7c1d2e3f", "pin": "1"},
   {"connector_id": "ConnB-9ab04d12", "wire_id": "55aa66bb", "pin": "4"}
 ]}
```

This makes routed wires enumerable later (which pins are already consumed,
re-route/update flows) without parsing geometry.

## Known limitations (accepted for the prove-out)

- The wire is **not associative**: connector points are captured as fixed
  coordinates at build time. Moving a connector strands the wire; the
  intended follow-up is delete-and-re-route (or a future update command
  driven by the route attribute).
- Pins already consumed by an existing route are still offered.
- The preview is a straight exit-to-exit line, not the final spline shape.
- Icons are placeholders copied from `roundsketchdimensions`.

---

[← Route Wire guide](../Route%20Wire.md)
