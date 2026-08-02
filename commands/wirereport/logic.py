# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.
"""Pure, Fusion-free helpers for the Wire Report command.

Turns raw route data (attributes plus measured sketch-path lengths, all in
internal centimeters) into the report structure the palette renders. The
key rule: a cable's length is set by its LONGEST wire path - every wire in
a manufactured cable is cut to the same length, so the longest run (its
end fan-outs plus the jacket) governs the cable cut length.
"""

from __future__ import annotations

from ..routewire import logic as route_logic


def summarize_single(route: dict) -> dict:
    """Report entry for a single-wire route.

    Args:
        route: ``{"name", "awg", "od_mm", "ends", "conductor_cm",
            "sheath_cm"}`` - lengths are the measured path lengths of the
            Conductor and Sheath components in internal cm.

    Returns:
        The route fields plus ``kind`` and ``total_cm`` (bare stubs plus
        the sheathed run - the wire's cut length).
    """
    conductor_cm = float(route.get("conductor_cm") or 0.0)
    sheath_cm = float(route.get("sheath_cm") or 0.0)
    return {
        "kind": route_logic.KIND_SINGLE,
        "name": str(route.get("name") or ""),
        "awg": route.get("awg"),
        "od_mm": route.get("od_mm"),
        "ends": route.get("ends") or [],
        "conductor_cm": conductor_cm,
        "sheath_cm": sheath_cm,
        "total_cm": conductor_cm + sheath_cm,
    }


def summarize_cable(route: dict) -> dict:
    """Report entry for a cable route.

    Args:
        route: ``{"name", "awg", "od_mm", "cable_od_mm", "ends",
            "jacket_cm", "wires": [{"pin", "extra_cm"}]}`` - ``extra_cm``
            is a wire's measured length OUTSIDE the jacket (both ends'
            conductor stubs, exit lines, and fan-out segments).

    Returns:
        The route fields plus per-wire ``path_cm`` (extra + jacket),
        ``cable_cm`` = the LONGEST wire path (this sets the cable cut
        length), and ``longest_pin`` naming the governing wire.
    """
    jacket_cm = float(route.get("jacket_cm") or 0.0)
    wires = []
    for wire in route.get("wires") or []:
        extra_cm = float(wire.get("extra_cm") or 0.0)
        wires.append(
            {
                "pin": str(wire.get("pin") or ""),
                "extra_cm": extra_cm,
                "path_cm": extra_cm + jacket_cm,
            }
        )
    longest = max(wires, key=lambda wire: wire["path_cm"], default=None)
    return {
        "kind": route_logic.KIND_CABLE,
        "name": str(route.get("name") or ""),
        "awg": route.get("awg"),
        "od_mm": route.get("od_mm"),
        "cable_od_mm": route.get("cable_od_mm"),
        "ends": route.get("ends") or [],
        "jacket_cm": jacket_cm,
        "wires": wires,
        "cable_cm": longest["path_cm"] if longest else jacket_cm,
        "longest_pin": longest["pin"] if longest else "",
    }


def summarize_routes(routes: list[dict]) -> dict:
    """The whole report: per-assembly entries plus rollup totals.

    Args:
        routes: Raw route dicts, each carrying ``kind``
            (:data:`route_logic.KIND_SINGLE` when absent) and the fields
            its summarizer needs. Unknown kinds are skipped into
            ``skipped``.

    Returns:
        ``{"assemblies": [...], "totals": {"wire_count", "cable_count",
        "conductor_cm"}, "skipped": int}`` - ``conductor_cm`` is the summed
        cut length of every wire in every assembly (bill-of-materials
        style).
    """
    assemblies: list = []
    skipped = 0
    wire_count = 0
    cable_count = 0
    conductor_cm = 0.0
    for route in routes:
        kind = route.get("kind") or route_logic.KIND_SINGLE
        if kind == route_logic.KIND_SINGLE:
            entry = summarize_single(route)
            wire_count += 1
            conductor_cm += entry["total_cm"]
        elif kind == route_logic.KIND_CABLE:
            entry = summarize_cable(route)
            cable_count += 1
            conductor_cm += sum(wire["path_cm"] for wire in entry["wires"])
        else:
            skipped += 1
            continue
        assemblies.append(entry)
    return {
        "assemblies": assemblies,
        "totals": {
            "wire_count": wire_count,
            "cable_count": cable_count,
            "conductor_cm": conductor_cm,
        },
        "skipped": skipped,
    }
