# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2022-2026 IMA LLC

"""Parameter fingerprinting for detecting value changes between versions.

Walks ``design.allParameters``, groups them by owning timeline feature
via ``parameter.createdBy.timelineObject.index``, and stores each
parameter's numeric value, expression, and role.  Comparison uses
numeric values (with tolerance) to avoid false positives from
expression formatting differences like ``"180.00 deg"`` vs ``"180 deg"``.
"""

from typing import Dict, Tuple

import adsk.fusion


# Type alias: {param_name: (value, expression, role)}
ParamEntry = Tuple[float, str, str]
ParamDict = Dict[str, ParamEntry]

# Tolerance for floating-point value comparison (relative)
_REL_TOL = 1e-9


def extract_feature_params(design: adsk.fusion.Design) -> Dict[int, ParamDict]:
    """Build a mapping of timeline-index -> parameter dict for every feature.

    Must be called while the document is open.

    Args:
        design: The active Fusion Design object.

    Returns:
        ``{timeline_index: {param_name: (value, expression, role), ...}, ...}``
        Features with no parameters are omitted from the dict.
    """
    result: Dict[int, ParamDict] = {}

    try:
        all_params = design.allParameters
    except Exception:
        return result

    for i in range(all_params.count):
        try:
            p = all_params.item(i)
            creator = p.createdBy
            if creator is None:
                continue
            tl_obj = creator.timelineObject
            if tl_obj is None:
                continue

            idx = tl_obj.index
            name = p.name or ""
            value = p.value
            expr = p.expression or ""
            role = p.role or ""

            if idx not in result:
                result[idx] = {}
            result[idx][name] = (value, expr, role)
        except Exception:
            # Skip parameters that can't be resolved (broken refs, etc.)
            continue

    return result


def attach_params_to_features(features: list, param_map: Dict[int, ParamDict]) -> None:
    """Attach parameter dicts to TimelineFeature objects by timeline index.

    Mutates each feature in-place, setting ``feature.feature_params``.

    Args:
        features: List of TimelineFeature from walk_timeline().
        param_map: Output of extract_feature_params().
    """
    for f in features:
        params = param_map.get(f.index)
        if params:
            f.feature_params = params


def _values_equal(a: float, b: float) -> bool:
    """Compare two parameter values with relative tolerance."""
    if a == b:
        return True
    if a == 0.0 or b == 0.0:
        return abs(a - b) < _REL_TOL
    return abs(a - b) / max(abs(a), abs(b)) < _REL_TOL


def params_differ(older_params: ParamDict, newer_params: ParamDict) -> bool:
    """Return True if any parameter value actually changed between versions.

    Uses numeric value comparison with tolerance to avoid false positives
    from expression formatting differences.
    """
    if set(older_params.keys()) != set(newer_params.keys()):
        return True

    for name in older_params:
        old_val, _, _ = older_params[name]
        new_val, _, _ = newer_params[name]
        if not _values_equal(old_val, new_val):
            return True

    return False


def param_change_detail(older_params: ParamDict, newer_params: ParamDict) -> str:
    """Build a human-readable summary of parameter changes between two versions.

    Only reports parameters whose numeric value actually changed.
    Uses expression strings for display but numeric values for comparison.

    Returns a string like ``"d1: 10 mm -> 15 mm, d3: 5 mm -> 8 mm"``
    or an empty string if nothing meaningfully changed.
    """
    changes: list[str] = []

    all_names = sorted(set(older_params.keys()) | set(newer_params.keys()))

    for name in all_names:
        old_entry = older_params.get(name)
        new_entry = newer_params.get(name)

        if old_entry and new_entry:
            old_val, old_expr, _ = old_entry
            new_val, new_expr, _ = new_entry
            if not _values_equal(old_val, new_val):
                changes.append(f"{name}: {old_expr} \u2192 {new_expr}")
        elif old_entry and not new_entry:
            _, old_expr, _ = old_entry
            changes.append(f"{name}: {old_expr} \u2192 removed")
        elif new_entry and not old_entry:
            _, new_expr, _ = new_entry
            changes.append(f"{name}: added \u2192 {new_expr}")

    return ", ".join(changes)
