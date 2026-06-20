# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2022-2026 IMA LLC

"""Sketch fingerprinting for change detection between versions.

Extracts a lightweight fingerprint from a live Fusion 360 Sketch entity
consisting of revisionId (primary change detector) and element counts
(secondary detail for human-readable summaries).
"""

from dataclasses import dataclass
from typing import Optional

import adsk.fusion


@dataclass
class SketchFingerprint:
    """Fingerprint data extracted from a Sketch for change detection.

    ``revision_id`` is the authoritative change indicator — it changes
    any time the sketch is modified.  The element counts provide a
    human-readable summary of *what* changed.
    """
    revision_id: str
    line_count: int
    circle_count: int
    arc_count: int
    ellipse_count: int
    spline_count: int
    point_count: int
    dimension_count: int
    constraint_count: int
    profile_count: int
    text_count: int
    is_fully_constrained: bool


def extract_sketch_fingerprint(entity) -> Optional[SketchFingerprint]:
    """Extract a fingerprint from a live Sketch entity.

    Must be called while the document containing the sketch is open.
    All property reads are simple count/property accesses — no
    geometry iteration required.

    Args:
        entity: The timeline item entity (should be castable to Sketch).

    Returns:
        A SketchFingerprint, or None if the entity is not a valid sketch
        or properties cannot be read.
    """
    try:
        sketch = adsk.fusion.Sketch.cast(entity)
        if sketch is None:
            return None

        curves = sketch.sketchCurves
        return SketchFingerprint(
            revision_id=sketch.revisionId or "",
            line_count=curves.sketchLines.count,
            circle_count=curves.sketchCircles.count,
            arc_count=curves.sketchArcs.count,
            ellipse_count=curves.sketchEllipses.count,
            spline_count=(
                curves.sketchFittedSplines.count
                + curves.sketchFixedSplines.count
                + curves.sketchControlPointSplines.count
            ),
            point_count=sketch.sketchPoints.count,
            dimension_count=sketch.sketchDimensions.count,
            constraint_count=sketch.geometricConstraints.count,
            profile_count=sketch.profiles.count,
            text_count=sketch.sketchTexts.count,
            is_fully_constrained=sketch.isFullyConstrained,
        )
    except Exception:
        # Sketch may be in an error state or suppressed — degrade gracefully
        return None


def sketch_change_detail(
    older_fp: SketchFingerprint,
    newer_fp: SketchFingerprint,
) -> str:
    """Build a human-readable summary of count deltas between two fingerprints.

    Returns a string like ``"Lines: 5\u21927, Dims: 3\u21925"`` or
    ``"Internal change (geometry or parameters modified)"`` when the
    revisionId differs but all counts match.
    """
    labels = [
        ("Lines", older_fp.line_count, newer_fp.line_count),
        ("Circles", older_fp.circle_count, newer_fp.circle_count),
        ("Arcs", older_fp.arc_count, newer_fp.arc_count),
        ("Splines", older_fp.spline_count, newer_fp.spline_count),
        ("Points", older_fp.point_count, newer_fp.point_count),
        ("Dims", older_fp.dimension_count, newer_fp.dimension_count),
        ("Constraints", older_fp.constraint_count, newer_fp.constraint_count),
        ("Profiles", older_fp.profile_count, newer_fp.profile_count),
        ("Texts", older_fp.text_count, newer_fp.text_count),
    ]

    changes: list[str] = []
    for label, old_val, new_val in labels:
        if old_val != new_val:
            changes.append(f"{label}: {old_val}\u2192{new_val}")

    if not changes:
        return "Internal change (geometry or parameters modified)"
    return ", ".join(changes)
