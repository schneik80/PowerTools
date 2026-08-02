# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.
"""Shared Fusion-side wire building for the Cable commands.

Used by Route Wire (initial build) and Update Wire (delete and rebuild).
Two responsibilities:

- ``read_connector(occ)``: scan an occurrence's component for the Define
  Wires attribute data and hand back routable wires with both the point
  proxies (for associative links) and their world positions (for previews
  and fallbacks).
- ``build_wire(design, ends, params)``: build the wire assembly tree
  (``Wire <name>`` containing ``Conductor`` and ``Sheath`` components), the
  conductor and sheath Pipe bodies, the route attribute, and the timeline
  group.

Associativity: the routing sketches are created in root context
(``Sketches.add`` with ``occurrenceForCreation`` - the API analog of the
UI's active occurrence) and the wire points are brought in with
``Sketch.include`` of the connector-point proxies, so the lines are fully
DEFINED by connector geometry and follow when connectors move. The
exit-to-exit spline is merged onto those line endpoints and tangency then
deterministically bends only the spline. When an include refuses, that
point falls back to a fixed baked position (counted in the build result);
connector swap/edit breaking the links is accepted - Update Wire is the
recovery path.
"""

import traceback

import adsk.core
import adsk.fusion

from ...lib import ptAddInUtils as ptutil
from ..definewires import logic as schema
from . import logic

_LOG_NAME = "Cable wire builder"


# ---------------------------------------------------------------------------
# Reading connector data
# ---------------------------------------------------------------------------
def read_connector(occ) -> dict:
    """Scan the occurrence's component for Define Wires attribute data.

    Returns a dict with ``occ``, ``occ_token``, ``path`` (unique occurrence
    path), ``comp_name``, ``connector_id``, ``wires``, ``cable`` and
    ``error`` ("" when usable). Each wire (keyed by pin) carries
    ``wire_id``, ``pin``, ``awg_min``, ``awg_max``, ``world`` ({role:
    Point3D in root space}) and ``proxies`` ({role: assembly-context point
    proxy, for associative includes}). ``cable`` is the connector's cable
    breakout point as ``{"proxy", "world"}`` (None when not authored) -
    required for cable routing. Only complete wires (all three roles
    resolvable) are offered.
    """
    comp = occ.component
    data = {
        "occ": occ,
        "occ_token": entity_token(occ),
        "path": occ_path(occ),
        "comp_name": comp.name,
        "connector_id": component_connector_id(comp),
        "wires": {},
        "cable": None,
        "error": "",
    }

    partial: dict = {}
    cable_entity = None
    for entity in _iter_component_points(comp):
        for attr_name, payload in _cable_attrs_on(entity):
            if attr_name == schema.CABLE_POINT_NAME:
                if payload is not None and cable_entity is None:
                    cable_entity = entity
                continue
            parsed = schema.parse_point_attr_name(attr_name)
            if parsed is None or payload is None:
                continue
            wire_id, role = parsed
            record = partial.setdefault(
                wire_id,
                {
                    "wire_id": wire_id,
                    "pin": str(payload.get("pin") or ""),
                    "awg_min": schema.coerce_awg(
                        payload.get("awg_min"), schema.AWG_DEFAULT_MIN
                    ),
                    "awg_max": schema.coerce_awg(
                        payload.get("awg_max"), schema.AWG_DEFAULT_MAX
                    ),
                    "points": {},
                },
            )
            record["points"][role] = entity

    for record in partial.values():
        if not record["pin"] or set(record["points"]) != set(schema.ROLES):
            continue  # incomplete wire - not routable
        world = {}
        proxies = {}
        for role, entity in record["points"].items():
            proxy, point = _point_refs(entity, occ)
            if point is None:
                break
            world[role] = point
            proxies[role] = proxy
        if len(world) != len(schema.ROLES):
            continue
        record["world"] = world
        record["proxies"] = proxies
        del record["points"]
        data["wires"][record["pin"]] = record

    if cable_entity is not None:
        proxy, world = _point_refs(cable_entity, occ)
        if world is not None:
            data["cable"] = {"proxy": proxy, "world": world}
        else:
            ptutil.log(
                f"{_LOG_NAME}: cable point attribute found on '{comp.name}' "
                "but its point could not be resolved to a world position."
            )
    else:
        ptutil.log(
            f"{_LOG_NAME}: no cable point attribute on '{comp.name}' "
            f"({len(data['wires'])} wire(s) found)."
        )

    if not data["wires"]:
        data["error"] = (
            f"No complete Define Wires data found on '{comp.name}'. Run "
            "Define Wires on the connector part first."
        )
    return data


def component_connector_id(comp) -> str:
    """The component's connector id from its manifest attribute ("" if none)."""
    try:
        attr = comp.attributes.itemByName(schema.ATTR_GROUP, schema.MANIFEST_NAME)
        payload = schema.parse_payload(attr.value if attr else "")
    except Exception:
        return ""  # tolerant read - a missing manifest is not an error
    if not payload:
        return ""
    return str(payload.get("connector_id") or "")


def entity_token(entity) -> str:
    """The entity's persistent token, or "" when unavailable."""
    try:
        return entity.entityToken or ""
    except Exception:
        return ""


def occ_path(occ) -> str:
    """Unique identity for an occurrence (used to reject picking it twice)."""
    try:
        return occ.fullPathName or occ.name
    except Exception:
        return occ.name


def _iter_component_points(comp):
    """Yield every construction point and sketch point of *comp* (native)."""
    try:
        for index in range(comp.constructionPoints.count):
            yield comp.constructionPoints.item(index)
    except Exception:
        ptutil.log(f"{_LOG_NAME}: construction point scan failed on {comp.name}.")
    try:
        for sketch_index in range(comp.sketches.count):
            sketch = comp.sketches.item(sketch_index)
            for point_index in range(sketch.sketchPoints.count):
                yield sketch.sketchPoints.item(point_index)
    except Exception:
        ptutil.log(f"{_LOG_NAME}: sketch point scan failed on {comp.name}.")


def _cable_attrs_on(entity) -> list:
    """``(name, parsed_payload)`` for the entity's PowerTools.Cable attributes."""
    results = []
    try:
        attrs = entity.attributes
        for index in range(attrs.count):
            attribute = attrs.item(index)
            if attribute.groupName != schema.ATTR_GROUP:
                continue
            results.append((attribute.name, schema.parse_payload(attribute.value)))
    except Exception:
        ptutil.log(f"{_LOG_NAME}: attribute read failed on an entity - skipped.")
    return results


def _point_refs(entity, occ):
    """``(proxy, world Point3D)`` for a wire point in root space, or Nones."""
    try:
        proxy = entity.createForAssemblyContext(occ)
    except Exception:
        ptutil.log(f"{_LOG_NAME}: no assembly-context proxy for a wire point.")
        return None, None
    try:
        construction_point = adsk.fusion.ConstructionPoint.cast(proxy)
        if construction_point:
            return proxy, construction_point.geometry
        sketch_point = adsk.fusion.SketchPoint.cast(proxy)
        if sketch_point:
            return proxy, sketch_point.worldGeometry
    except Exception:
        ptutil.log(f"{_LOG_NAME}: world position unavailable for a wire point.")
    return None, None


# ---------------------------------------------------------------------------
# Building the wire
# ---------------------------------------------------------------------------
def build_wire(design, ends, params) -> dict:
    """Build the complete wire assembly.

    Args:
        design: The active parametric design.
        ends: Two ``(side_data, wire)`` tuples - side_data from
            :func:`read_connector`, wire one of its ``wires`` records.
        params: ``{"name": str, "awg": int, "od_mm": float}``.

    Returns:
        ``{"spline_fallback": bool, "baked_points": int}`` - whether the
        sheath spline needed the guide-point fallback, and how many points
        could not be included associatively.
    """
    job = {
        "name": params["name"],
        "conductor_dia_cm": logic.conductor_diameter_mm(params["awg"]) / 10.0,
        "sheath_dia_cm": params["od_mm"] / 10.0,
        "result": {"spline_fallback": False, "baked_points": 0},
    }
    wires = (ends[0][1], ends[1][1])

    timeline_start = design.timeline.markerPosition

    identity = adsk.core.Matrix3D.create()
    root = design.rootComponent
    asm_occ = root.occurrences.addNewComponent(identity)
    asm_comp = asm_occ.component
    asm_comp.name = f"Wire {job['name']}"
    conductor_occ = asm_comp.occurrences.addNewComponent(identity)
    conductor_occ.component.name = "Conductor"
    sheath_occ = asm_comp.occurrences.addNewComponent(identity)
    sheath_occ.component.name = "Sheath"

    _build_conductor_bodies(
        conductor_occ.component,
        _root_context_occurrence(conductor_occ, asm_occ),
        wires,
        job,
    )
    _build_sheath_body(
        sheath_occ.component,
        _root_context_occurrence(sheath_occ, asm_occ),
        wires,
        job,
    )

    asm_comp.attributes.add(
        schema.ATTR_GROUP,
        logic.ROUTE_NAME,
        logic.build_route_payload(
            {
                "name": job["name"],
                "awg": params["awg"],
                "od_mm": params["od_mm"],
                "ends": [_route_end(side, wire) for side, wire in ends],
            }
        ),
    )

    _group_timeline(design, timeline_start, f"Wire {job['name']}")
    return job["result"]


def build_cable(design, ends, params) -> dict:
    """Build a complete multi-conductor cable assembly.

    Tree: a ``Cable <name>`` component at the root owning the jacket body
    (cable point to cable point), with one nested ``Wire <pin>`` component
    per paired wire holding its 4 bodies (2 conductor stubs + 2 sheathed
    end segments from strip via exit to the cable point).

    Args:
        design: The active parametric design.
        ends: Two ``(side_data, wires)`` tuples - side_data from
            :func:`read_connector` (must carry a ``cable`` point), wires an
            equal-length list of its wire records in paired (pin) order.
        params: ``{"name": str, "awg": int, "od_mm": float,
            "cable_od_mm": float}``.

    Returns:
        ``{"spline_fallback": bool, "baked_points": int}`` as for
        :func:`build_wire`.
    """
    job = {
        "name": params["name"],
        "conductor_dia_cm": logic.conductor_diameter_mm(params["awg"]) / 10.0,
        "sheath_dia_cm": params["od_mm"] / 10.0,
        "cable_dia_cm": params["cable_od_mm"] / 10.0,
        "result": {"spline_fallback": False, "baked_points": 0},
    }
    (side_a, wires_a), (side_b, wires_b) = ends

    timeline_start = design.timeline.markerPosition

    identity = adsk.core.Matrix3D.create()
    root = design.rootComponent
    cable_occ = root.occurrences.addNewComponent(identity)
    cable_comp = cable_occ.component
    cable_comp.name = f"Cable {job['name']}"

    # The cable occurrence was created at the root, so it IS root context.
    _build_jacket(cable_comp, cable_occ, ends, job)

    for wire_a, wire_b in zip(wires_a, wires_b, strict=True):
        wire_occ = cable_comp.occurrences.addNewComponent(identity)
        wire_occ.component.name = f"Wire {wire_a['pin']}"
        _build_cable_wire(
            wire_occ.component,
            _root_context_occurrence(wire_occ, cable_occ),
            ((side_a, wire_a), (side_b, wire_b)),
            job,
        )

    cable_comp.attributes.add(
        schema.ATTR_GROUP,
        logic.ROUTE_NAME,
        logic.build_route_payload(
            {
                "kind": logic.KIND_CABLE,
                "name": job["name"],
                "awg": params["awg"],
                "od_mm": params["od_mm"],
                "cable_od_mm": params["cable_od_mm"],
                "ends": [
                    _cable_route_end(side_a, wires_a),
                    _cable_route_end(side_b, wires_b),
                ],
            }
        ),
    )

    _group_timeline(design, timeline_start, f"Cable {job['name']}")
    return job["result"]


def _cable_route_end(side_data: dict, wires: list) -> dict:
    """One connector's identity for a cable route attribute payload."""
    return {
        "connector_id": side_data["connector_id"],
        "occ_token": side_data["occ_token"],
        "pins": [wire["pin"] for wire in wires],
        "wire_ids": [wire["wire_id"] for wire in wires],
    }


def _route_end(side_data: dict, wire: dict) -> dict:
    """One end's identity for the route attribute payload.

    ``occ_token`` lets Update Wire re-resolve the exact occurrence even when
    several instances of the same connector exist; ``connector_id`` is the
    fallback when the token dies (document copied, connector reinserted).
    """
    return {
        "connector_id": side_data["connector_id"],
        "wire_id": wire["wire_id"],
        "pin": wire["pin"],
        "occ_token": side_data["occ_token"],
    }


def _root_context_occurrence(child_occ, parent_occ):
    """Root-context proxy of a nested occurrence (None when unavailable)."""
    try:
        return child_occ.createForAssemblyContext(parent_occ)
    except Exception:
        ptutil.log(f"{_LOG_NAME}: no root-context proxy for a wire component.")
        return None


def _add_route_sketch(comp, ctx_occ, sketch_name: str):
    """A 3D routing sketch in *comp*, created in root context when possible.

    Creating the sketch with occurrenceForCreation (the API analog of the
    UI's active occurrence) lets include() record associative links to the
    connector geometry in other components.
    """
    sketch = None
    if ctx_occ is not None:
        try:
            sketch = comp.sketches.add(comp.xYConstructionPlane, ctx_occ)
        except Exception:
            ptutil.log(
                f"{_LOG_NAME}: in-context sketch creation failed, using a "
                f"component-local sketch.\n{traceback.format_exc()}"
            )
    if sketch is None:
        sketch = comp.sketches.add(comp.xYConstructionPlane)
    sketch.name = sketch_name
    return sketch


def _sketch_point_for(sketch, proxy, world, job):
    """A sketch point for one wire point: included (associative) or baked.

    include() creates a point linked to the connector geometry, so the line
    it defines follows the connector. When include refuses (or no proxy is
    available) the world position is baked as a FIXED point - the wire
    still builds deterministically, just without associativity for that
    point, counted in the build result.
    """
    if proxy is not None:
        try:
            created = sketch.include(proxy)
            if created and created.count > 0:
                point = adsk.fusion.SketchPoint.cast(created.item(0))
                if point is not None:
                    return point
            ptutil.log(f"{_LOG_NAME}: include produced no sketch point.")
        except Exception:
            ptutil.log(
                f"{_LOG_NAME}: include failed for a wire point:\n"
                f"{traceback.format_exc()}"
            )
    point = sketch.sketchPoints.add(sketch.modelToSketchSpace(world))
    try:
        point.isFixed = True
    except Exception:
        ptutil.log(f"{_LOG_NAME}: could not fix a baked wire point.")
    job["result"]["baked_points"] += 1
    return point


def _build_conductor_bodies(comp, ctx_occ, wires, job):
    """Bodies 1 and 2: bare-conductor stubs, start -> strip, per connector."""
    name = job["name"]
    sketch = _add_route_sketch(comp, ctx_occ, f"Wire {name} conductor paths")
    for index, wire in enumerate(wires, start=1):
        start_point = _sketch_point_for(
            sketch,
            wire["proxies"].get(schema.ROLE_START),
            wire["world"][schema.ROLE_START],
            job,
        )
        strip_point = _sketch_point_for(
            sketch,
            wire["proxies"].get(schema.ROLE_STRIP),
            wire["world"][schema.ROLE_STRIP],
            job,
        )
        line = sketch.sketchCurves.sketchLines.addByTwoPoints(start_point, strip_point)
        path = comp.features.createPath(line, False)
        _add_pipe(comp, path, job["conductor_dia_cm"], f"Wire {name} conductor {index}")


def _build_sheath_body(comp, ctx_occ, wires, job):
    """Body 3: strip -> exit, smooth exit-to-exit spline, exit -> strip."""
    wire_a, wire_b = wires
    name = job["name"]
    sketch = _add_route_sketch(comp, ctx_occ, f"Wire {name} sheath path")
    end_points = []
    for wire in (wire_a, wire_b):
        strip_point = _sketch_point_for(
            sketch,
            wire["proxies"].get(schema.ROLE_STRIP),
            wire["world"][schema.ROLE_STRIP],
            job,
        )
        exit_point = _sketch_point_for(
            sketch,
            wire["proxies"].get(schema.ROLE_EXIT),
            wire["world"][schema.ROLE_EXIT],
            job,
        )
        end_points.append((strip_point, exit_point))

    lines = sketch.sketchCurves.sketchLines
    line_a = lines.addByTwoPoints(end_points[0][0], end_points[0][1])
    line_b = lines.addByTwoPoints(end_points[1][0], end_points[1][1])
    spline = _add_exit_spline(sketch, (line_a, line_b), wires, job)

    curves = adsk.core.ObjectCollection.create()
    curves.add(line_a)
    curves.add(spline)
    curves.add(line_b)
    path = comp.features.createPath(curves, False)
    _add_pipe(comp, path, job["sheath_dia_cm"], f"Wire {name} sheath")


def _add_exit_spline(sketch, exit_lines, wires, job):
    """Create the exit-to-exit spline, tangent to both exit lines.

    The exit lines are fully DEFINED by their endpoints (included connector
    points, or fixed baked points), so the solver has no freedom on the
    lines: merging the spline's endpoints into the lines' exit endpoints
    (SketchPoint.merge - point-to-point coincident constraints are not
    supported by the API) and adding tangent constraints deterministically
    bends only the spline, and keeps doing so when connectors move. Only if
    a step refuses does this fall back to an unconstrained spline shaped by
    directional guide points, flagged in the build result.
    """
    wire_a, wire_b = wires
    line_a, line_b = exit_lines
    fit = adsk.core.ObjectCollection.create()
    fit.add(line_a.endSketchPoint.geometry)
    fit.add(line_b.endSketchPoint.geometry)
    spline = sketch.sketchCurves.sketchFittedSplines.add(fit)
    try:
        if not line_a.endSketchPoint.merge(spline.startSketchPoint):
            raise ValueError("merge of spline start into exit line A failed")
        if not line_b.endSketchPoint.merge(spline.endSketchPoint):
            raise ValueError("merge of spline end into exit line B failed")
        constraints = sketch.geometricConstraints
        if constraints.addTangent(line_a, spline) is None:
            raise ValueError("addTangent(line_a, spline) returned null")
        if constraints.addTangent(spline, line_b) is None:
            raise ValueError("addTangent(spline, line_b) returned null")
        return spline
    except Exception:
        ptutil.log(
            f"{_LOG_NAME}: constrained spline construction failed, using "
            f"guide-point spline.\n{traceback.format_exc()}"
        )
    try:
        spline.deleteMe()
    except Exception:
        ptutil.log(f"{_LOG_NAME}: could not delete the constrained spline attempt.")
    guides = logic.spline_guide_points(
        _as_tuple(wire_a["world"][schema.ROLE_STRIP]),
        _as_tuple(wire_a["world"][schema.ROLE_EXIT]),
        _as_tuple(wire_b["world"][schema.ROLE_STRIP]),
        _as_tuple(wire_b["world"][schema.ROLE_EXIT]),
    )
    fallback_fit = adsk.core.ObjectCollection.create()
    for xyz in guides:
        fallback_fit.add(sketch.modelToSketchSpace(adsk.core.Point3D.create(*xyz)))
    job["result"]["spline_fallback"] = True
    return sketch.sketchCurves.sketchFittedSplines.add(fallback_fit)


def _build_jacket(comp, ctx_occ, ends, job):
    """The cable jacket body: cable point to cable point, at the cable OD.

    Fully associative, using the same proven recipe as the single-wire exit
    spline: per side, a CONSTRUCTION direction line from the first paired
    wire's included exit point to the included cable point (fully defined
    by connector geometry), with the jacket spline's ends merged into the
    cable points and made tangent to those lines. Everything re-solves
    when a connector moves.

    (An earlier build shaped the jacket with two BAKED interior guide
    points instead. Those are free sketch points at fixed coordinates:
    after a connector moved, the spline's ends followed but the curve still
    had to pass through the stale guides, kinking the path and failing the
    jacket pipe's recompute. Baked guides remain only as the constraint
    fallback, which is flagged in the build result.)
    """
    (side_a, wires_a), (side_b, wires_b) = ends
    name = job["name"]
    sketch = _add_route_sketch(comp, ctx_occ, f"Cable {name} jacket path")
    cable_a = _sketch_point_for(
        sketch, side_a["cable"]["proxy"], side_a["cable"]["world"], job
    )
    cable_b = _sketch_point_for(
        sketch, side_b["cable"]["proxy"], side_b["cable"]["world"], job
    )
    exit_a = _sketch_point_for(
        sketch,
        wires_a[0]["proxies"].get(schema.ROLE_EXIT),
        wires_a[0]["world"][schema.ROLE_EXIT],
        job,
    )
    exit_b = _sketch_point_for(
        sketch,
        wires_b[0]["proxies"].get(schema.ROLE_EXIT),
        wires_b[0]["world"][schema.ROLE_EXIT],
        job,
    )
    lines = sketch.sketchCurves.sketchLines
    direction_a = lines.addByTwoPoints(exit_a, cable_a)
    direction_b = lines.addByTwoPoints(exit_b, cable_b)
    try:
        direction_a.isConstruction = True
        direction_b.isConstruction = True
    except Exception:
        ptutil.log(f"{_LOG_NAME}: could not mark jacket direction lines.")

    fit = adsk.core.ObjectCollection.create()
    fit.add(cable_a.geometry)
    fit.add(cable_b.geometry)
    spline = sketch.sketchCurves.sketchFittedSplines.add(fit)
    try:
        if not cable_a.merge(spline.startSketchPoint):
            raise ValueError("merge of jacket spline start failed")
        if not cable_b.merge(spline.endSketchPoint):
            raise ValueError("merge of jacket spline end failed")
        constraints = sketch.geometricConstraints
        if constraints.addTangent(direction_a, spline) is None:
            raise ValueError("addTangent(direction_a, spline) returned null")
        if constraints.addTangent(spline, direction_b) is None:
            raise ValueError("addTangent(spline, direction_b) returned null")
    except Exception:
        ptutil.log(
            f"{_LOG_NAME}: constrained jacket spline failed, using baked "
            f"guide points.\n{traceback.format_exc()}"
        )
        try:
            spline.deleteMe()
        except Exception:
            ptutil.log(f"{_LOG_NAME}: could not delete the jacket spline attempt.")
        guides = logic.spline_guide_points(
            _as_tuple(_centroid([w["world"][schema.ROLE_EXIT] for w in wires_a])),
            _as_tuple(side_a["cable"]["world"]),
            _as_tuple(_centroid([w["world"][schema.ROLE_EXIT] for w in wires_b])),
            _as_tuple(side_b["cable"]["world"]),
        )
        fallback_fit = adsk.core.ObjectCollection.create()
        for xyz in guides:
            fallback_fit.add(sketch.modelToSketchSpace(adsk.core.Point3D.create(*xyz)))
        spline = sketch.sketchCurves.sketchFittedSplines.add(fallback_fit)
        job["result"]["spline_fallback"] = True
    path = comp.features.createPath(spline, False)
    _add_pipe(comp, path, job["cable_dia_cm"], f"Cable {name} jacket")


def _build_cable_wire(comp, ctx_occ, pair, job):
    """One paired wire of a cable: 4 bodies in its own component.

    Per end: a bare conductor stub (start to strip, AWG diameter) and a
    sheathed segment strip -> exit -> cable point (line plus fan-out spline,
    wire OD). The mid-run between the cable points is represented by the
    jacket only.
    """
    (side_a, wire_a), (side_b, wire_b) = pair
    label = f"Cable {job['name']} wire {wire_a['pin']}"
    sketch = _add_route_sketch(comp, ctx_occ, f"{label} paths")
    for suffix, side, wire in (("1", side_a, wire_a), ("2", side_b, wire_b)):
        start_point = _sketch_point_for(
            sketch,
            wire["proxies"].get(schema.ROLE_START),
            wire["world"][schema.ROLE_START],
            job,
        )
        strip_point = _sketch_point_for(
            sketch,
            wire["proxies"].get(schema.ROLE_STRIP),
            wire["world"][schema.ROLE_STRIP],
            job,
        )
        exit_point = _sketch_point_for(
            sketch,
            wire["proxies"].get(schema.ROLE_EXIT),
            wire["world"][schema.ROLE_EXIT],
            job,
        )
        cable_point = _sketch_point_for(
            sketch, side["cable"]["proxy"], side["cable"]["world"], job
        )

        lines = sketch.sketchCurves.sketchLines
        conductor_line = lines.addByTwoPoints(start_point, strip_point)
        conductor_path = comp.features.createPath(conductor_line, False)
        _add_pipe(
            comp,
            conductor_path,
            job["conductor_dia_cm"],
            f"{label} conductor {suffix}",
        )

        exit_line = lines.addByTwoPoints(strip_point, exit_point)
        spline = _add_fanout_spline(sketch, exit_line, cable_point, (wire, job))
        curves = adsk.core.ObjectCollection.create()
        curves.add(exit_line)
        curves.add(spline)
        sheath_path = comp.features.createPath(curves, False)
        _add_pipe(comp, sheath_path, job["sheath_dia_cm"], f"{label} sheath {suffix}")


def _add_fanout_spline(sketch, exit_line, cable_point, refs):
    """Spline from a wire's exit to the cable point, tangent at the exit.

    Same merge-then-tangent construction as the single-wire exit spline,
    but one-sided: the cable end is direction-free (the wires converge into
    the jacket there). Falls back to a guide-point spline
    (logic.fanout_guide_points) when a step refuses, flagged in the result.
    """
    wire, job = refs
    fit = adsk.core.ObjectCollection.create()
    fit.add(exit_line.endSketchPoint.geometry)
    fit.add(cable_point.geometry)
    spline = sketch.sketchCurves.sketchFittedSplines.add(fit)
    try:
        if not exit_line.endSketchPoint.merge(spline.startSketchPoint):
            raise ValueError("merge of fan-out spline start failed")
        if not cable_point.merge(spline.endSketchPoint):
            raise ValueError("merge of fan-out spline end failed")
        if sketch.geometricConstraints.addTangent(exit_line, spline) is None:
            raise ValueError("addTangent(exit_line, spline) returned null")
        return spline
    except Exception:
        ptutil.log(
            f"{_LOG_NAME}: constrained fan-out spline failed, using "
            f"guide points.\n{traceback.format_exc()}"
        )
    try:
        spline.deleteMe()
    except Exception:
        ptutil.log(f"{_LOG_NAME}: could not delete the fan-out spline attempt.")
    guides = logic.fanout_guide_points(
        _as_tuple(wire["world"][schema.ROLE_STRIP]),
        _as_tuple(wire["world"][schema.ROLE_EXIT]),
        _as_tuple(sketch.sketchToModelSpace(cable_point.geometry)),
    )
    fallback_fit = adsk.core.ObjectCollection.create()
    for xyz in guides:
        fallback_fit.add(sketch.modelToSketchSpace(adsk.core.Point3D.create(*xyz)))
    job["result"]["spline_fallback"] = True
    return sketch.sketchCurves.sketchFittedSplines.add(fallback_fit)


def _centroid(points) -> adsk.core.Point3D:
    """Average of a non-empty list of Point3D."""
    count = len(points)
    return adsk.core.Point3D.create(
        sum(p.x for p in points) / count,
        sum(p.y for p in points) / count,
        sum(p.z for p in points) / count,
    )


def _add_pipe(comp, path, dia_cm: float, label: str):
    """Solid circular pipe of *dia_cm* along *path*, named *label*."""
    pipes = comp.features.pipeFeatures
    pipe_input = pipes.createInput(
        path, adsk.fusion.FeatureOperations.NewBodyFeatureOperation
    )
    # VERIFY AT RUNTIME: sectionSize is assumed to be the section DIAMETER
    # (matching the UI's "Section Size" field); the API docs do not say
    # radius or diameter. Section type defaults to circular, solid.
    pipe_input.sectionSize = adsk.core.ValueInput.createByReal(dia_cm)
    pipe = pipes.add(pipe_input)
    pipe.name = label
    try:
        if pipe.bodies.count > 0:
            pipe.bodies.item(0).name = label
    except Exception:
        ptutil.log(f"{_LOG_NAME}: could not rename body for '{label}'.")
    return pipe


def _group_timeline(design, start_index: int, label: str):
    """Group everything created since *start_index* under *label*."""
    try:
        timeline = design.timeline
        end_index = timeline.markerPosition - 1
        if end_index > start_index:
            group = timeline.timelineGroups.add(start_index, end_index)
            group.name = label
    except Exception:
        ptutil.log(f"{_LOG_NAME}: timeline grouping failed:\n{traceback.format_exc()}")


def _as_tuple(point) -> tuple:
    """Point3D -> (x, y, z) for the pure-logic helpers."""
    return (point.x, point.y, point.z)
