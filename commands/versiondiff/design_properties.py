# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2022-2026 IMA LLC

"""Extract physical material, appearances, mass properties and extents from a design.

Used by the version diff to compare design-level properties between two
versions before drilling into the timeline feature comparison.
"""

from dataclasses import dataclass, field
from typing import Optional, Tuple

import adsk.core
import adsk.fusion


@dataclass
class DesignProperties:
    """Snapshot of a design's physical and visual properties."""

    # Material
    material: str = ""

    # Unique body appearance names (sorted)
    body_appearances: list = field(default_factory=list)

    # Mass properties
    mass: float = 0.0       # kg
    volume: float = 0.0     # cm³
    area: float = 0.0       # cm²
    density: float = 0.0    # kg/cm³
    center_of_mass: Tuple[float, float, float] = (0.0, 0.0, 0.0)

    # Bounding box
    bbox_min: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    bbox_max: Tuple[float, float, float] = (0.0, 0.0, 0.0)

    # Body count
    body_count: int = 0


def extract_design_properties(design: adsk.fusion.Design) -> Optional[DesignProperties]:
    """Extract properties from a live Fusion design.

    Must be called while the document is open.  All reads are fast
    property accesses — the heaviest call is ``getPhysicalProperties()``.

    Args:
        design: The active Fusion Design object.

    Returns:
        A DesignProperties snapshot, or None on failure.
    """
    try:
        root = design.rootComponent
        props = DesignProperties()

        # ── Material ──────────────────────────────────────────────────
        try:
            if root.material:
                props.material = root.material.name
        except Exception:
            pass

        # ── Body appearances ──────────────────────────────────────────
        try:
            bodies = root.bRepBodies
            props.body_count = bodies.count
            appearances = set()
            for i in range(bodies.count):
                body = bodies.item(i)
                if body.appearance:
                    appearances.add(body.appearance.name)
            props.body_appearances = sorted(appearances)
        except Exception:
            pass

        # ── Mass properties ───────────────────────────────────────────
        try:
            phys = root.getPhysicalProperties()
            props.mass = phys.mass
            props.volume = phys.volume
            props.area = phys.area
            props.density = phys.density
            com = phys.centerOfMass
            props.center_of_mass = (com.x, com.y, com.z)
        except Exception:
            pass

        # ── Bounding box ──────────────────────────────────────────────
        try:
            bb = root.boundingBox
            props.bbox_min = (bb.minPoint.x, bb.minPoint.y, bb.minPoint.z)
            props.bbox_max = (bb.maxPoint.x, bb.maxPoint.y, bb.maxPoint.z)
        except Exception:
            pass

        return props

    except Exception:
        return None
