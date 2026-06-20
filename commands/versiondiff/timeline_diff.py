# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2022-2026 IMA LLC

import json
import os
import re
import secrets
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

import adsk.core
import adsk.fusion

from .param_fingerprint import param_change_detail, params_differ
from .sketch_hash import extract_sketch_fingerprint, sketch_change_detail
from .timeline_model import TimelineFeature, VersionInfo, DiffEntry, DiffResult, AlignedRow

# Pattern to parse Occurrence names like "Center Diff Mount v2:1"
# Captures: (base_component_name, version_number, instance_number)
_OCCURRENCE_NAME_RE = re.compile(r"^(.+?)\s+v(\d+):(\d+)$")


def walk_timeline(timeline: adsk.fusion.Timeline) -> list:
    """Walk a Fusion 360 design timeline and extract all features.

    Args:
        timeline: The design's Timeline object.

    Returns:
        List of TimelineFeature dataclass instances.
    """
    features = []

    for i in range(timeline.count):
        item = timeline.item(i)

        # Skip timeline groups -- their child features are already
        # individual timeline items and will be collected in index order.
        if item.isGroup:
            continue

        # Extract short type name from entity objectType
        # Some timeline items have invalid/broken entities that raise RuntimeError
        try:
            entity = item.entity
        except RuntimeError:
            entity = None

        component_name = ""
        component_version = ""

        if entity is not None:
            full_type = entity.objectType  # e.g. "adsk::fusion::ExtrudeFeature"
            feature_type = full_type.split("::")[-1] if "::" in full_type else full_type
            entity_type = full_type

            # For Occurrence (XREF) features, parse name to extract
            # base component name, version, and instance.
            # Name format: "ComponentName vN:I" e.g. "Center Diff Mount v2:1"
            if feature_type == "Occurrence":
                feature_type = "XREF"
                match = _OCCURRENCE_NAME_RE.match(item.name)
                if match:
                    component_name = f"{match.group(1)}:{match.group(3)}"  # "Center Diff Mount:1"
                    component_version = f"v{match.group(2)}"               # "v2"
                else:
                    # Fallback: use full name if pattern doesn't match
                    component_name = item.name
                    component_version = ""
        else:
            feature_type = "Group" if item.isGroup else "Unknown"
            entity_type = ""

        # Map health state enum to string
        try:
            health_map = {
                adsk.fusion.FeatureHealthStates.HealthyFeatureHealthState: "Healthy",
                adsk.fusion.FeatureHealthStates.WarningFeatureHealthState: "Warning",
                adsk.fusion.FeatureHealthStates.ErrorFeatureHealthState: "Error",
            }
            health_str = health_map.get(item.healthState, "Unknown")
        except RuntimeError:
            health_str = "Unknown"

        # Extract sketch fingerprint for change detection across versions
        sketch_fp = None
        if feature_type == "Sketch" and entity is not None:
            sketch_fp = extract_sketch_fingerprint(entity)

        features.append(TimelineFeature(
            name=item.name,
            feature_type=feature_type,
            index=item.index,
            is_group=item.isGroup,
            is_suppressed=item.isSuppressed,
            is_rolled_back=item.isRolledBack,
            health_state=health_str,
            entity_type=entity_type,
            component_name=component_name,
            component_version=component_version,
            sketch_fingerprint=sketch_fp,
        ))

    return features


def get_version_info(data_file: adsk.core.DataFile) -> VersionInfo:
    """Extract version metadata from a Fusion DataFile.

    Args:
        data_file: The DataFile to read version info from.

    Returns:
        VersionInfo dataclass instance.
    """
    date_str = ""
    if data_file.dateModified:
        date_str = datetime.fromtimestamp(data_file.dateModified).strftime("%Y-%m-%d %H:%M:%S")

    updated_by = ""
    if data_file.lastUpdatedBy:
        updated_by = data_file.lastUpdatedBy.displayName

    # Capture thumbnail as base64-encoded PNG for embedding in the HTML report.
    # DataFile.thumbnail returns a DataObjectFuture; .dataObject.getAsBase64String()
    # returns the PNG already base64-encoded when state == 1 (ready).
    thumbnail_b64 = ""
    try:
        thumb_future = getattr(data_file, "thumbnail", None)
        if thumb_future is not None:
            thumb_obj = getattr(thumb_future, "dataObject", None)
            if thumb_obj is not None:
                thumbnail_b64 = thumb_obj.getAsBase64String()
    except Exception:
        pass

    return VersionInfo(
        version_number=data_file.versionNumber,
        version_id=data_file.versionId,
        name=data_file.name,
        date_modified=date_str,
        last_updated_by=updated_by,
        description=data_file.description or "",
        thumbnail_b64=thumbnail_b64,
    )


def _feature_key(f: TimelineFeature) -> tuple:
    """Return the identity key for a feature.

    For XREF (Occurrence) features, identity is based on component_name
    so that the same component at different versions matches as one row.
    For all other features, identity is (name, feature_type).
    """
    if f.feature_type == "XREF" and f.component_name:
        return ("XREF", f.component_name)
    return (f.name, f.feature_type)


def _xref_version_detail(baseline_f, compare_f) -> str:
    """Build a human-readable version change description for XREF features."""
    old_ver = compare_f.component_version if compare_f else ""
    new_ver = baseline_f.component_version if baseline_f else ""
    if old_ver and new_ver and old_ver != new_ver:
        return f"{old_ver} \u2192 {new_ver}"
    if old_ver and not new_ver:
        return old_ver
    if new_ver and not old_ver:
        return new_ver
    return ""


def _make_aligned_row(baseline_f: 'TimelineFeature', compare_f: 'TimelineFeature') -> AlignedRow:
    """Create an AlignedRow for two matched features, detecting XREF version and sketch changes."""
    # Check for XREF version change
    if (baseline_f.feature_type == "XREF" and compare_f.feature_type == "XREF"
            and baseline_f.component_version and compare_f.component_version
            and baseline_f.component_version != compare_f.component_version):
        detail = _xref_version_detail(baseline_f, compare_f)
        return AlignedRow(older=compare_f, newer=baseline_f, status="version_changed", detail=detail)

    # Check for sketch modification via fingerprint
    if (baseline_f.feature_type == "Sketch" and compare_f.feature_type == "Sketch"
            and baseline_f.sketch_fingerprint and compare_f.sketch_fingerprint
            and baseline_f.sketch_fingerprint.revision_id != compare_f.sketch_fingerprint.revision_id):
        sk_detail = sketch_change_detail(compare_f.sketch_fingerprint, baseline_f.sketch_fingerprint)
        return AlignedRow(
            older=compare_f, newer=baseline_f,
            status="sketch_modified", sketch_detail=sk_detail,
        )

    # Check for parameter changes on any feature type
    if (baseline_f.feature_params and compare_f.feature_params
            and params_differ(compare_f.feature_params, baseline_f.feature_params)):
        p_detail = param_change_detail(compare_f.feature_params, baseline_f.feature_params)
        if p_detail:
            return AlignedRow(
                older=compare_f, newer=baseline_f,
                status="params_changed", params_detail=p_detail,
            )

    # Check for health state change (only change is health status)
    if (baseline_f.health_state and compare_f.health_state
            and baseline_f.health_state != compare_f.health_state):
        h_detail = f"{compare_f.health_state} \u2192 {baseline_f.health_state}"
        return AlignedRow(
            older=compare_f, newer=baseline_f,
            status="health_changed", health_detail=h_detail,
        )

    return AlignedRow(older=compare_f, newer=baseline_f, status="unchanged")


def compute_diff(baseline_features: list, compare_features: list) -> tuple:
    """Compare two timeline feature lists and produce a diff.

    Uses (name, feature_type) as the identity key for most features.
    For XREF (Occurrence) features, matches by component_name so that the
    same component at different versions is shown on one row as
    "version_changed" instead of delete + add.

    Statuses:
    - "newer": feature exists in baseline but not in comparison
    - "deleted": feature exists in comparison but not in baseline
    - "unchanged": feature exists in both, no difference detected
    - "version_changed": XREF with same component but different version
    - "sketch_modified": Sketch with same name but different revisionId
    - "params_changed": Feature exists in both but parameter values differ

    Args:
        baseline_features: List of TimelineFeature from the current version.
        compare_features: List of TimelineFeature from the comparison version.

    Returns:
        Tuple of (list[DiffEntry], list[AlignedRow], summary_dict).
    """
    # Build lookup dicts keyed by identity key
    baseline_map = {}
    for f in baseline_features:
        baseline_map[_feature_key(f)] = f

    compare_map = {}
    for f in compare_features:
        compare_map[_feature_key(f)] = f

    diff_entries = []
    seen_keys = set()

    # Walk baseline features in order
    for f in baseline_features:
        key = _feature_key(f)
        seen_keys.add(key)

        if key in compare_map:
            cf = compare_map[key]
            # Check for XREF version change
            if (f.feature_type == "XREF" and cf.feature_type == "XREF"
                    and f.component_version and cf.component_version
                    and f.component_version != cf.component_version):
                status = "version_changed"
                detail = _xref_version_detail(f, cf)
            # Check for sketch modification
            elif (f.feature_type == "Sketch" and cf.feature_type == "Sketch"
                    and f.sketch_fingerprint and cf.sketch_fingerprint
                    and f.sketch_fingerprint.revision_id != cf.sketch_fingerprint.revision_id):
                status = "sketch_modified"
                detail = sketch_change_detail(cf.sketch_fingerprint, f.sketch_fingerprint)
            # Check for parameter changes
            elif (f.feature_params and cf.feature_params
                    and f.feature_params != cf.feature_params):
                p_detail = param_change_detail(cf.feature_params, f.feature_params)
                if p_detail:
                    status = "params_changed"
                    detail = p_detail
                else:
                    status = "unchanged"
                    detail = ""
            # Check for health state change (only change is health status)
            elif (f.health_state and cf.health_state
                    and f.health_state != cf.health_state):
                status = "health_changed"
                detail = f"{cf.health_state} \u2192 {f.health_state}"
            else:
                status = "unchanged"
                detail = ""
            compare_index = cf.index
        else:
            status = "newer"
            compare_index = None
            detail = ""

        diff_entries.append(DiffEntry(
            name=f.name,
            feature_type=f.feature_type,
            status=status,
            baseline_index=f.index,
            compare_index=compare_index,
            detail=detail,
        ))

    # Walk comparison features for deleted items
    for f in compare_features:
        key = _feature_key(f)
        if key not in seen_keys:
            diff_entries.append(DiffEntry(
                name=f.name,
                feature_type=f.feature_type,
                status="deleted",
                baseline_index=None,
                compare_index=f.index,
            ))

    # --- Build aligned rows for two-column view ---
    # Track compare features already matched out-of-order so they aren't
    # emitted a second time when the ci pointer reaches them.
    aligned_rows = []
    consumed_compare_keys = set()
    bi = 0  # baseline pointer
    ci = 0  # compare pointer

    while bi < len(baseline_features) or ci < len(compare_features):
        # Advance ci past any compare features already consumed out-of-order
        while ci < len(compare_features) and _feature_key(compare_features[ci]) in consumed_compare_keys:
            ci += 1

        bf = baseline_features[bi] if bi < len(baseline_features) else None
        cf = compare_features[ci] if ci < len(compare_features) else None

        if bf and cf:
            b_key = _feature_key(bf)
            c_key = _feature_key(cf)

            if b_key == c_key:
                # Same feature in both -- check for XREF version change
                row = _make_aligned_row(bf, cf)
                aligned_rows.append(row)
                consumed_compare_keys.add(c_key)
                bi += 1
                ci += 1
            elif c_key not in baseline_map:
                # Compare feature was deleted
                aligned_rows.append(AlignedRow(older=cf, newer=None, status="deleted"))
                consumed_compare_keys.add(c_key)
                ci += 1
            elif b_key not in compare_map:
                # Baseline feature is newer
                aligned_rows.append(AlignedRow(older=None, newer=bf, status="newer"))
                bi += 1
            else:
                # Both exist but at different positions -- reordered.
                # Pull the matching compare feature out-of-order and mark consumed.
                matched_cf = compare_map.get(b_key)
                row = _make_aligned_row(bf, matched_cf)
                aligned_rows.append(row)
                consumed_compare_keys.add(b_key)
                bi += 1
        elif bf:
            aligned_rows.append(AlignedRow(older=None, newer=bf, status="newer"))
            bi += 1
        elif cf:
            # Skip if already consumed
            if _feature_key(cf) not in consumed_compare_keys:
                aligned_rows.append(AlignedRow(older=cf, newer=None, status="deleted"))
            ci += 1

    # Compute summary
    newer_count = sum(1 for e in diff_entries if e.status == "newer")
    deleted_count = sum(1 for e in diff_entries if e.status == "deleted")
    unchanged_count = sum(1 for e in diff_entries if e.status == "unchanged")
    version_changed_count = sum(1 for e in diff_entries if e.status == "version_changed")
    sketch_modified_count = sum(1 for e in diff_entries if e.status == "sketch_modified")
    params_changed_count = sum(1 for e in diff_entries if e.status == "params_changed")
    health_changed_count = sum(1 for e in diff_entries if e.status == "health_changed")

    summary = {
        "newer": newer_count,
        "deleted": deleted_count,
        "unchanged": unchanged_count,
        "version_changed": version_changed_count,
        "sketch_modified": sketch_modified_count,
        "params_changed": params_changed_count,
        "health_changed": health_changed_count,
        "total_baseline": len(baseline_features),
        "total_comparison": len(compare_features),
    }

    return diff_entries, aligned_rows, summary


def save_diff_json(diff_result: DiffResult) -> str:
    """Save a DiffResult as a JSON file in the temp directory.

    Args:
        diff_result: The complete diff result to serialize.

    Returns:
        POSIX-style path to the saved JSON file.
    """
    temp_path = tempfile.gettempdir()
    report_name = secrets.token_urlsafe(8)
    filepath = os.path.join(temp_path, f"version_diff_{report_name}.json")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(diff_result.to_json())

    return Path(filepath).as_posix()
