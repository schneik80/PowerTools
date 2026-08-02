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
from . import routing as logic
from . import schema

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
    Point3D in root space}), ``proxies`` ({role: assembly-context point
    proxy, for associative includes}), ``natives`` ({role: native entity,
    so a stale proxy can be recreated at include time}) and ``occ``.
    ``cable`` is the connector's cable breakout point as ``{"proxy",
    "world", "native"}`` (None when not authored) - required for cable
    routing. Only complete wires (all three roles resolvable) are offered.
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
        natives = {}
        for role, entity in record["points"].items():
            proxy, point = _point_refs(entity, occ)
            if point is None:
                break
            world[role] = point
            proxies[role] = proxy
            natives[role] = entity
        if len(world) != len(schema.ROLES):
            continue
        record["world"] = world
        record["proxies"] = proxies
        record["natives"] = natives
        record["occ"] = occ
        del record["points"]
        data["wires"][record["pin"]] = record

    if cable_entity is not None:
        proxy, world = _point_refs(cable_entity, occ)
        if world is not None:
            data["cable"] = {"proxy": proxy, "world": world, "native": cable_entity}
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


def collect_routes(design) -> list:
    """Routed assemblies at the design root: ``[{"occ", "payload"}, ...]``.

    An occurrence qualifies when its component carries a parseable
    PowerTools.Cable ``route`` attribute (written by build_wire /
    build_cable). Used by Update Wire and the Wire Report.
    """
    routes = []
    root = design.rootComponent
    for index in range(root.occurrences.count):
        occ = root.occurrences.item(index)
        payload = _route_payload_of(occ.component)
        if payload:
            routes.append({"occ": occ, "payload": payload})
    return routes


def _route_payload_of(comp):
    """The component's parsed route attribute payload, or None."""
    try:
        attr = comp.attributes.itemByName(schema.ATTR_GROUP, logic.ROUTE_NAME)
        return schema.parse_payload(attr.value if attr else "")
    except Exception:
        return None  # tolerant read - not a routed assembly


def _stamp_member(comp, role: str, pin: str | None = None):
    """Stamp a member attribute so reports can identify this child by data.

    Best-effort: a stamp failure must never fail the build - the Wire
    Report falls back to display-name matching for unstamped children.
    """
    try:
        comp.attributes.add(
            schema.ATTR_GROUP,
            schema.MEMBER_NAME,
            schema.build_member_payload(role, pin),
        )
    except Exception:
        ptutil.log(f"{_LOG_NAME}: could not stamp the {role} member attribute.")


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


def connector_occurrences(design) -> list:
    """Occurrences whose component carries a Define Wires manifest."""
    found: list = []
    occurrences = design.rootComponent.allOccurrences
    for index in range(occurrences.count):
        occ = occurrences.item(index)
        try:
            if component_connector_id(occ.component):
                found.append(occ)
        except Exception:
            continue  # tolerate transient/broken occurrences
    return found


def occurrence_designator(occ) -> str:
    """The occurrence's stored reference designator ("" when unassigned).

    Designators live on the OCCURRENCE (per instance, assembly-local) in
    the PowerTools.Cable group under ``schema.DESIGNATOR_NAME``.
    """
    try:
        attr = occ.attributes.itemByName(schema.ATTR_GROUP, schema.DESIGNATOR_NAME)
        payload = schema.parse_payload(attr.value if attr else "")
    except Exception:
        return ""  # tolerant read - not assigned
    if not payload:
        return ""
    return str(payload.get("designator") or "").strip()


def resolve_end_occurrence(design, end: dict, connectors: list):
    """The live connector occurrence a stored route end refers to (or None).

    The Update Wire ladder: the stored occ_token is RESOLVED through
    Design.findEntityByToken (never compared as a string - the API
    documents token strings as unstable), else a UNIQUE connector-id match
    among *connectors*.
    """
    token = str(end.get("occ_token") or "")
    if token:
        try:
            entities = design.findEntityByToken(token) or []
        except Exception:
            entities = []
        for entity in entities:
            occ = adsk.fusion.Occurrence.cast(entity)
            if occ is not None:
                return occ
    connector_id = str(end.get("connector_id") or "")
    if connector_id:
        matches = [
            occ
            for occ in connectors
            if component_connector_id(occ.component) == connector_id
        ]
        if len(matches) == 1:
            return matches[0]
    return None


def member_payload(comp) -> dict | None:
    """The component's parsed member attribute payload, or None."""
    try:
        attr = comp.attributes.itemByName(schema.ATTR_GROUP, schema.MEMBER_NAME)
        return schema.parse_payload(attr.value if attr else "")
    except Exception:
        return None  # tolerant read - not a stamped member


def own_curve_length_cm(comp) -> float:
    """Summed length of the component's non-construction sketch curves.

    Used by the Wire Report and Export Connectivity to measure routing
    sketches (construction geometry - jacket direction lines - excluded).
    """
    total = 0.0
    try:
        for sketch_index in range(comp.sketches.count):
            sketch = comp.sketches.item(sketch_index)
            curves = sketch.sketchCurves
            for curve_index in range(curves.count):
                curve = curves.item(curve_index)
                try:
                    if curve.isConstruction:
                        continue
                    total += curve.length
                except Exception:
                    ptutil.log(f"{_LOG_NAME}: a curve in {sketch.name} was skipped.")
    except Exception:
        ptutil.log(f"{_LOG_NAME}: sketch scan failed on {comp.name}.")
    return total


def member_child_length_cm(comp, role: str, name_prefix: str) -> float:
    """Curve length of the child component with member role *role*.

    Members match by their stamped member attribute first (immune to
    renames); the display-name prefix is only the fallback for assemblies
    built before members were stamped (prefix, because Fusion suffixes
    duplicate component names - "Conductor (1)"). A total miss is logged
    instead of silently reporting a zero length as fact.
    """
    fallback = None
    try:
        for index in range(comp.occurrences.count):
            child = comp.occurrences.item(index)
            member = member_payload(child.component)
            if member is not None:
                if member.get("role") == role:
                    return own_curve_length_cm(child.component)
                continue
            if fallback is None and child.component.name.startswith(name_prefix):
                fallback = child.component
    except Exception:
        ptutil.log(f"{_LOG_NAME}: child lookup failed on {comp.name}.")
    if fallback is not None:
        return own_curve_length_cm(fallback)
    ptutil.log(f"{_LOG_NAME}: no {role} member found on {comp.name} - length 0.")
    return 0.0


def measure_cable_wires(comp, payload) -> list:
    """Per-wire out-of-jacket lengths, labeled with the most reliable pin.

    Children are found by their stamped member attribute (role "wire",
    which also carries the pin - immune to renames and Fusion's uniqueness
    suffixes). For assemblies built before members were stamped, the
    fallbacks are the old ladder: name-prefix discovery, pins by creation
    order against the payload (build order = paired pin order), then
    component-name parsing when the counts disagree.
    """
    children = []  # (component, stamped pin or None)
    try:
        for index in range(comp.occurrences.count):
            child = comp.occurrences.item(index)
            member = member_payload(child.component)
            if member is not None:
                if member.get("role") == schema.MEMBER_WIRE:
                    pin = str(member.get("pin") or "")
                    children.append((child.component, pin or None))
                continue
            if child.component.name.startswith("Wire "):
                children.append((child.component, None))
    except Exception:
        ptutil.log(f"{_LOG_NAME}: cable child scan failed on {comp.name}.")
    payload_pins = []
    ends = payload.get("ends") or []
    if ends and isinstance(ends[0], dict):
        payload_pins = [str(pin) for pin in ends[0].get("pins") or []]
    use_payload = len(payload_pins) == len(children)
    wires = []
    for index, (child, stamped_pin) in enumerate(children):
        if stamped_pin:
            pin = stamped_pin
        elif use_payload:
            pin = payload_pins[index]
        elif child.name.startswith("Wire "):
            pin = child.name[len("Wire ") :]
        else:
            pin = child.name
        wires.append({"pin": pin, "extra_cm": own_curve_length_cm(child)})
    return wires


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
        params: ``{"name": str, "awg": int, "od_mm": float}`` plus an
            optional ``"color"`` (wire color key; defaulted when absent).

    Returns:
        ``{"spline_fallback": bool, "baked_points": int}`` - whether the
        sheath spline needed the guide-point fallback, and how many points
        could not be included associatively.
    """
    color = logic.normalize_wire_color(params.get("color"))
    job = {
        "name": params["name"],
        "conductor_dia_cm": logic.conductor_diameter_mm(params["awg"]) / 10.0,
        "sheath_dia_cm": params["od_mm"] / 10.0,
        "conductor_appearance": _conductor_appearance(design),
        "sheath_appearance": _wire_color_appearance(design, color),
        "result": {"spline_fallback": False, "baked_points": 0, "dropped_tangents": 0},
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
    _stamp_member(conductor_occ.component, schema.MEMBER_CONDUCTOR)
    sheath_occ = asm_comp.occurrences.addNewComponent(identity)
    sheath_occ.component.name = "Sheath"
    _stamp_member(sheath_occ.component, schema.MEMBER_SHEATH)

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
                "color": color,
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
            "cable_od_mm": float}`` plus optional ``"colors"`` (wire color
            keys in paired order; auto-assigned from the palette sequence
            when absent or mismatched).

    Returns:
        ``{"spline_fallback": bool, "baked_points": int}`` as for
        :func:`build_wire`.
    """
    (side_a, wires_a), (side_b, wires_b) = ends
    colors = [
        logic.normalize_wire_color(color) for color in (params.get("colors") or [])
    ]
    if len(colors) != len(wires_a):
        colors = logic.assign_wire_colors(len(wires_a))
    job = {
        "name": params["name"],
        "conductor_dia_cm": logic.conductor_diameter_mm(params["awg"]) / 10.0,
        "sheath_dia_cm": params["od_mm"] / 10.0,
        "cable_dia_cm": params["cable_od_mm"] / 10.0,
        "conductor_appearance": _conductor_appearance(design),
        "jacket_appearance": _wire_color_appearance(design, logic.JACKET_COLOR),
        "result": {"spline_fallback": False, "baked_points": 0, "dropped_tangents": 0},
    }

    timeline_start = design.timeline.markerPosition

    identity = adsk.core.Matrix3D.create()
    root = design.rootComponent
    cable_occ = root.occurrences.addNewComponent(identity)
    cable_comp = cable_occ.component
    cable_comp.name = f"Cable {job['name']}"

    # Wires build FIRST, jacket LAST: every occurrence/feature added before
    # a sketch's includes is a chance for the dialog-time proxies to go
    # stale, so the many per-wire includes run with the least prior
    # mutation and the jacket's four (which have a decent guide-point
    # fallback) absorb the most.
    for index, (wire_a, wire_b) in enumerate(zip(wires_a, wires_b, strict=True)):
        wire_occ = cable_comp.occurrences.addNewComponent(identity)
        wire_occ.component.name = f"Wire {wire_a['pin']}"
        _stamp_member(wire_occ.component, schema.MEMBER_WIRE, wire_a["pin"])
        # Each wire's sheathed segments carry its own assigned color.
        job["sheath_appearance"] = _wire_color_appearance(design, colors[index])
        _build_cable_wire(
            wire_occ.component,
            _root_context_occurrence(wire_occ, cable_occ),
            ((side_a, wire_a), (side_b, wire_b)),
            job,
        )

    # The cable occurrence was created at the root, so it IS root context.
    _build_jacket(cable_comp, cable_occ, ends, job)

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
                "colors": colors,
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


def _point_ref(wire: dict, role: str) -> dict:
    """The include reference for one of a wire's points."""
    return {
        "proxy": wire["proxies"].get(role),
        "native": wire.get("natives", {}).get(role),
        "occ": wire.get("occ"),
        "world": wire["world"][role],
    }


def _cable_ref(side: dict) -> dict:
    """The include reference for a connector's cable point."""
    cable = side["cable"]
    return {
        "proxy": cable.get("proxy"),
        "native": cable.get("native"),
        "occ": side.get("occ"),
        "world": cable["world"],
    }


def _sketch_point_for(sketch, ref: dict, job):
    """A sketch point for one wire point: included (associative) or baked.

    include() creates a point linked to the connector geometry, so the line
    it defines follows the connector. Proxies captured at dialog time can go
    STALE by the time later sketches build (each occurrence/feature the
    build adds can invalidate them - the cable build does far more work
    before its wire sketches than the single-wire build does), so a failed
    include is retried once with a FRESH proxy recreated from the native
    entity. Only then does the point fall back to a baked fixed position,
    counted in the build result and reported in the summary.
    """
    proxy = ref.get("proxy")
    for attempt in ("cached", "refreshed"):
        if proxy is None:
            break
        try:
            created = sketch.include(proxy)
            if created and created.count > 0:
                point = adsk.fusion.SketchPoint.cast(created.item(0))
                if point is not None:
                    return point
            ptutil.log(f"{_LOG_NAME}: include produced no point ({attempt} proxy).")
        except Exception:
            ptutil.log(
                f"{_LOG_NAME}: include failed ({attempt} proxy):\n"
                f"{traceback.format_exc()}"
            )
        if attempt == "refreshed":
            break
        proxy = _fresh_proxy(ref)
    point = sketch.sketchPoints.add(sketch.modelToSketchSpace(ref["world"]))
    try:
        point.isFixed = True
    except Exception:
        ptutil.log(f"{_LOG_NAME}: could not fix a baked wire point.")
    job["result"]["baked_points"] += 1
    return point


def _fresh_proxy(ref: dict):
    """Recreate the assembly-context proxy from the native entity."""
    native = ref.get("native")
    occ = ref.get("occ")
    if native is None or occ is None:
        return None
    try:
        return native.createForAssemblyContext(occ)
    except Exception:
        ptutil.log(f"{_LOG_NAME}: proxy refresh failed:\n{traceback.format_exc()}")
        return None


def _build_conductor_bodies(comp, ctx_occ, wires, job):
    """Bodies 1 and 2: bare-conductor stubs, start -> strip, per connector."""
    name = job["name"]
    sketch = _add_route_sketch(comp, ctx_occ, f"Wire {name} conductor paths")
    for index, wire in enumerate(wires, start=1):
        start_point = _sketch_point_for(
            sketch, _point_ref(wire, schema.ROLE_START), job
        )
        strip_point = _sketch_point_for(
            sketch, _point_ref(wire, schema.ROLE_STRIP), job
        )
        line = sketch.sketchCurves.sketchLines.addByTwoPoints(start_point, strip_point)
        path = comp.features.createPath(line, False)
        _add_pipe(
            comp,
            path,
            job["conductor_dia_cm"],
            f"Wire {name} conductor {index}",
            appearance=job.get("conductor_appearance"),
        )


def _build_sheath_body(comp, ctx_occ, wires, job):
    """Body 3: strip -> exit, smooth exit-to-exit spline, exit -> strip."""
    wire_a, wire_b = wires
    name = job["name"]
    sketch = _add_route_sketch(comp, ctx_occ, f"Wire {name} sheath path")
    end_points = []
    for wire in (wire_a, wire_b):
        strip_point = _sketch_point_for(
            sketch, _point_ref(wire, schema.ROLE_STRIP), job
        )
        exit_point = _sketch_point_for(sketch, _point_ref(wire, schema.ROLE_EXIT), job)
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
    _add_pipe(
        comp,
        path,
        job["sheath_dia_cm"],
        f"Wire {name} sheath",
        appearance=job.get("sheath_appearance"),
    )


def _constrained_spline(sketch, start_point, end_point, tangent_lines, label):
    """Fitted spline start-to-end, merged onto its anchors and made tangent.

    The anchor points must already terminate real curves (line endpoints -
    merging into a BARE included point raises InternalValidationError, see
    docs/arch/Route Wire.md), so `SketchPoint.merge` joins the spline's
    ends onto them and the two tangent constraints deterministically bend
    only the spline - including on recompute when connectors move.

    Returns the spline, or None when a step refuses (the attempt is
    deleted; the caller builds its guide-point fallback).
    """
    fit = adsk.core.ObjectCollection.create()
    fit.add(start_point.geometry)
    fit.add(end_point.geometry)
    spline = sketch.sketchCurves.sketchFittedSplines.add(fit)
    try:
        if not start_point.merge(spline.startSketchPoint):
            raise ValueError(f"merge of {label} spline start failed")
        if not end_point.merge(spline.endSketchPoint):
            raise ValueError(f"merge of {label} spline end failed")
        constraints = sketch.geometricConstraints
        line_a, line_b = tangent_lines
        if constraints.addTangent(line_a, spline) is None:
            raise ValueError(f"addTangent({label} line A, spline) returned null")
        if constraints.addTangent(spline, line_b) is None:
            raise ValueError(f"addTangent(spline, {label} line B) returned null")
        return spline
    except Exception:
        ptutil.log(
            f"{_LOG_NAME}: constrained {label} spline failed, using "
            f"guide points.\n{traceback.format_exc()}"
        )
    try:
        spline.deleteMe()
    except Exception:
        ptutil.log(f"{_LOG_NAME}: could not delete the {label} spline attempt.")
    return None


def _guide_spline(sketch, guides, job):
    """Baked guide-point fallback spline, flagged in the build result."""
    fit = adsk.core.ObjectCollection.create()
    for xyz in guides:
        fit.add(sketch.modelToSketchSpace(adsk.core.Point3D.create(*xyz)))
    job["result"]["spline_fallback"] = True
    return sketch.sketchCurves.sketchFittedSplines.add(fit)


def _add_exit_spline(sketch, exit_lines, wires, job):
    """Create the exit-to-exit spline, tangent to both exit lines.

    The exit lines are fully DEFINED by their endpoints (included connector
    points, or fixed baked points), so the solver has no freedom on the
    lines - see :func:`_constrained_spline`. (`SketchPoint.merge` predates
    the finding that `addCoincident` documents point-to-point support; the
    merge recipe demonstrably survives connector moves here, so it stays.)
    Falls back to an unconstrained spline shaped by directional guide
    points, flagged in the build result.
    """
    wire_a, wire_b = wires
    line_a, line_b = exit_lines
    spline = _constrained_spline(
        sketch, line_a.endSketchPoint, line_b.endSketchPoint, exit_lines, "exit"
    )
    if spline is not None:
        return spline
    guides = logic.spline_guide_points(
        _as_tuple(wire_a["world"][schema.ROLE_STRIP]),
        _as_tuple(wire_a["world"][schema.ROLE_EXIT]),
        _as_tuple(wire_b["world"][schema.ROLE_STRIP]),
        _as_tuple(wire_b["world"][schema.ROLE_EXIT]),
    )
    return _guide_spline(sketch, guides, job)


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
    cable_a = _sketch_point_for(sketch, _cable_ref(side_a), job)
    cable_b = _sketch_point_for(sketch, _cable_ref(side_b), job)
    exit_a = _sketch_point_for(sketch, _point_ref(wires_a[0], schema.ROLE_EXIT), job)
    exit_b = _sketch_point_for(sketch, _point_ref(wires_b[0], schema.ROLE_EXIT), job)
    lines = sketch.sketchCurves.sketchLines
    direction_a = lines.addByTwoPoints(exit_a, cable_a)
    direction_b = lines.addByTwoPoints(exit_b, cable_b)
    try:
        direction_a.isConstruction = True
        direction_b.isConstruction = True
    except Exception:
        ptutil.log(f"{_LOG_NAME}: could not mark jacket direction lines.")

    spline = _constrained_spline(
        sketch, cable_a, cable_b, (direction_a, direction_b), "jacket"
    )
    if spline is None:
        guides = logic.spline_guide_points(
            _as_tuple(_centroid([w["world"][schema.ROLE_EXIT] for w in wires_a])),
            _as_tuple(side_a["cable"]["world"]),
            _as_tuple(_centroid([w["world"][schema.ROLE_EXIT] for w in wires_b])),
            _as_tuple(side_b["cable"]["world"]),
        )
        spline = _guide_spline(sketch, guides, job)
    path = comp.features.createPath(spline, False)
    _add_pipe(
        comp,
        path,
        job["cable_dia_cm"],
        f"Cable {name} jacket",
        appearance=job.get("jacket_appearance"),
    )


def _build_cable_wire(comp, ctx_occ, pair, job):
    """One paired wire of a cable: 4 bodies in its own component.

    Per end: a bare conductor stub (start to strip, AWG diameter) and a
    sheathed segment strip -> exit -> cable point built from TWO STRAIGHT
    LINES at the wire OD. Lines between included points are the one
    construction that reliably follows connector moves: every
    constraint-correct fan-out SPLINE recipe (merged ends; coincident
    ends + addTangent; the UI-ideal tangent-handle + collinear) built
    without error, yet a Fusion recompute defect left most splines behind
    when a connector actually moved - see docs/arch/Route Wire.md and git
    history for the full chain. The mid-run between the cable points is
    represented by the jacket only.
    """
    (side_a, wire_a), (side_b, wire_b) = pair
    label = f"Cable {job['name']} wire {wire_a['pin']}"
    sketch = _add_route_sketch(comp, ctx_occ, f"{label} paths")
    for suffix, side, wire in (("1", side_a, wire_a), ("2", side_b, wire_b)):
        start_point = _sketch_point_for(
            sketch, _point_ref(wire, schema.ROLE_START), job
        )
        strip_point = _sketch_point_for(
            sketch, _point_ref(wire, schema.ROLE_STRIP), job
        )
        exit_point = _sketch_point_for(sketch, _point_ref(wire, schema.ROLE_EXIT), job)
        cable_point = _sketch_point_for(sketch, _cable_ref(side), job)

        lines = sketch.sketchCurves.sketchLines
        conductor_line = lines.addByTwoPoints(start_point, strip_point)
        conductor_path = comp.features.createPath(conductor_line, False)
        _add_pipe(
            comp,
            conductor_path,
            job["conductor_dia_cm"],
            f"{label} conductor {suffix}",
            appearance=job.get("conductor_appearance"),
        )

        exit_line = lines.addByTwoPoints(strip_point, exit_point)
        fan_line = lines.addByTwoPoints(exit_point, cable_point)
        curves = adsk.core.ObjectCollection.create()
        curves.add(exit_line)
        curves.add(fan_line)
        sheath_path = comp.features.createPath(curves, False)
        _add_pipe(
            comp,
            sheath_path,
            job["sheath_dia_cm"],
            f"{label} sheath {suffix}",
            appearance=job.get("sheath_appearance"),
        )


def _sketch_is_sick(sketch) -> bool:
    """True when the sketch's timeline item reports a compute problem."""
    try:
        states = adsk.fusion.FeatureHealthStates
        health = sketch.timelineObject.healthState
        return health in (
            states.ErrorFeatureHealthState,
            states.WarningFeatureHealthState,
        )
    except Exception:
        return False  # health unreadable - assume fine


def _centroid(points) -> adsk.core.Point3D:
    """Average of a non-empty list of Point3D."""
    count = len(points)
    return adsk.core.Point3D.create(
        sum(p.x for p in points) / count,
        sum(p.y for p in points) / count,
        sum(p.z for p in points) / count,
    )


# ---------------------------------------------------------------------------
# Appearances (wire colors, copper conductors, black jackets)
# ---------------------------------------------------------------------------
# Library names: the appearance library was renamed in newer Fusion builds,
# so both known names are tried before falling back to scanning every
# installed library. Appearance resolution is always best-effort - a build
# must never fail because a library was renamed or an appearance removed.
_APPEARANCE_LIBRARY_NAMES = (
    "Fusion Appearance Library",
    "Fusion 360 Appearance Library",
)
# Paint appearances carry a plain modifiable "Color" ColorProperty - the
# documented recipe for custom solid colors is addByCopy + set that
# property (not all appearance types expose one).
_COLOR_BASE_NAMES = (
    "Paint - Enamel Glossy (Yellow)",
    "Paint - Enamel Glossy (Red)",
    "Plastic - Matte (Yellow)",
)
_COPPER_NAMES = ("Copper - Polished", "Copper - Satin", "Copper")
_COPPER_APPEARANCE = "PowerTools Conductor Copper"
_WIRE_APPEARANCE_PREFIX = "PowerTools Wire "


def _appearance_libraries() -> list:
    """Installed material libraries, the known appearance libraries first."""
    ordered: list = []
    seen: set = set()
    try:
        libraries = adsk.core.Application.get().materialLibraries
        for preferred in _APPEARANCE_LIBRARY_NAMES:
            try:
                library = libraries.itemByName(preferred)
            except Exception:
                library = None
            if library is not None and preferred not in seen:
                ordered.append(library)
                seen.add(preferred)
        for index in range(libraries.count):
            library = libraries.item(index)
            try:
                name = library.name
            except Exception:
                continue
            if name not in seen:
                ordered.append(library)
                seen.add(name)
    except Exception:
        ptutil.log(f"{_LOG_NAME}: material library scan failed.")
    return ordered


def _library_appearance(names: tuple):
    """The first library appearance matching one of *names* (else None)."""
    for library in _appearance_libraries():
        for name in names:
            try:
                appearance = library.appearances.itemByName(name)
            except Exception:
                appearance = None
            if appearance is not None:
                return appearance
    return None


def _color_base_appearance():
    """A library appearance whose color can be modified (else None)."""
    base = _library_appearance(_COLOR_BASE_NAMES)
    if base is not None:
        return base
    # Last resort: the first library appearance carrying a Color property.
    for library in _appearance_libraries():
        try:
            appearances = library.appearances
            for index in range(appearances.count):
                appearance = appearances.item(index)
                try:
                    if appearance.appearanceProperties.itemByName("Color"):
                        return appearance
                except Exception:
                    continue
        except Exception:
            continue
    return None


def _tinted_appearance(design, name: str, rgb: tuple):
    """The design's *name* appearance, created from a paint base plus RGB.

    Created once per design and reused on later builds
    (``design.appearances.itemByName`` first). Returns None when no
    color-capable base exists; callers skip coloring rather than fail.
    """
    try:
        existing = design.appearances.itemByName(name)
        if existing is not None:
            return existing
    except Exception:
        pass  # itemByName can raise instead of returning None
    base = _color_base_appearance()
    if base is None:
        ptutil.log(f"{_LOG_NAME}: no color-capable base appearance found.")
        return None
    try:
        appearance = design.appearances.addByCopy(base, name)
        color_prop = adsk.core.ColorProperty.cast(
            appearance.appearanceProperties.itemByName("Color")
        )
        color_prop.value = adsk.core.Color.create(rgb[0], rgb[1], rgb[2], 255)
        return appearance
    except Exception:
        ptutil.log(
            f"{_LOG_NAME}: could not create appearance '{name}':\n"
            f"{traceback.format_exc()}"
        )
        return None


def _wire_color_appearance(design, color_key: str):
    """The design-cached appearance for one wire color key (else None)."""
    key = logic.normalize_wire_color(color_key)
    return _tinted_appearance(
        design, f"{_WIRE_APPEARANCE_PREFIX}{key}", logic.wire_color_rgb(key)
    )


def _conductor_appearance(design):
    """Copper for conductor bodies.

    Prefers the appearance library's real copper (copied into the design
    once, keyed by its own name); falls back to a copper-tinted paint
    appearance so conductors read as copper even if the library changes.
    """
    copper = _library_appearance(_COPPER_NAMES)
    if copper is not None:
        try:
            existing = design.appearances.itemByName(copper.name)
            if existing is not None:
                return existing
        except Exception:
            pass
        try:
            return design.appearances.addByCopy(copper, copper.name)
        except Exception:
            ptutil.log(f"{_LOG_NAME}: library copper copy failed.")
    return _tinted_appearance(design, _COPPER_APPEARANCE, logic.CONDUCTOR_RGB)


def _add_pipe(comp, path, dia_cm: float, label: str, appearance=None):
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
            body = pipe.bodies.item(0)
            body.name = label
            if appearance is not None:
                body.appearance = appearance
    except Exception:
        ptutil.log(f"{_LOG_NAME}: could not name/color the body for '{label}'.")
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
