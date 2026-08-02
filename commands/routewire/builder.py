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
    path), ``comp_name``, ``connector_id``, ``wires`` and ``error`` (""
    when usable). Each wire (keyed by pin) carries ``wire_id``, ``pin``,
    ``awg_min``, ``awg_max``, ``world`` ({role: Point3D in root space}) and
    ``proxies`` ({role: assembly-context point proxy, for associative
    includes}). Only complete wires (all three roles resolvable) are
    offered.
    """
    comp = occ.component
    data = {
        "occ": occ,
        "occ_token": entity_token(occ),
        "path": occ_path(occ),
        "comp_name": comp.name,
        "connector_id": component_connector_id(comp),
        "wires": {},
        "error": "",
    }

    partial: dict = {}
    for entity in _iter_component_points(comp):
        for attr_name, payload in _cable_attrs_on(entity):
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

    _group_timeline(design, timeline_start, job["name"])
    return job["result"]


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


def _group_timeline(design, start_index: int, name: str):
    """Group everything created since *start_index* as 'Wire <name>'."""
    try:
        timeline = design.timeline
        end_index = timeline.markerPosition - 1
        if end_index > start_index:
            group = timeline.timelineGroups.add(start_index, end_index)
            group.name = f"Wire {name}"
    except Exception:
        ptutil.log(f"{_LOG_NAME}: timeline grouping failed:\n{traceback.format_exc()}")


def _as_tuple(point) -> tuple:
    """Point3D -> (x, y, z) for the pure-logic helpers."""
    return (point.x, point.y, point.z)
