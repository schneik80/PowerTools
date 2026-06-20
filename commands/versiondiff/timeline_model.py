# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2022-2026 IMA LLC

import json
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class TimelineFeature:
    """Represents a single feature in a Fusion 360 design timeline."""
    name: str
    feature_type: str
    index: int
    is_group: bool
    is_suppressed: bool
    is_rolled_back: bool
    health_state: str
    entity_type: str
    component_name: str = ""       # For Occurrence (XREF) features: the referenced component name
    component_version: str = ""    # For Occurrence (XREF) features: the source document version
    sketch_fingerprint: object = None  # Optional[SketchFingerprint] — set for Sketch features
    feature_params: dict = None        # Optional[dict] — {param_name: (expression, role)}


@dataclass
class VersionInfo:
    """Metadata about a Fusion 360 document version."""
    version_number: int
    version_id: str
    name: str
    date_modified: str
    last_updated_by: str
    description: str
    thumbnail_b64: str = ""  # Base64-encoded PNG thumbnail (data URI payload)


@dataclass
class DiffEntry:
    """A single entry in the timeline diff result."""
    name: str
    feature_type: str
    status: str  # "newer" | "deleted" | "unchanged" | "version_changed"
    baseline_index: Optional[int]
    compare_index: Optional[int]
    detail: str = ""  # Extra info, e.g. version change description for XREFs


@dataclass
class AlignedRow:
    """A single row in the two-column aligned diff view.

    Each row has an older side and a newer side. One side may be None
    when a feature only exists in one version.
    """
    older: Optional[TimelineFeature]
    newer: Optional[TimelineFeature]
    status: str  # "newer" | "deleted" | "unchanged" | "version_changed" | "sketch_modified" | "params_changed" | "health_changed"
    detail: str = ""  # Extra info for version_changed rows
    sketch_detail: str = ""  # Count delta summary for sketch_modified rows
    params_detail: str = ""  # Parameter change summary for params_changed rows
    health_detail: str = ""  # Health state change summary for health_changed rows


@dataclass
class DiffResult:
    """Complete diff output comparing two version timelines."""
    baseline: VersionInfo
    comparison: VersionInfo
    features: list = field(default_factory=list)      # list[DiffEntry]
    aligned_rows: list = field(default_factory=list)   # list[AlignedRow]
    summary: dict = field(default_factory=dict)
    older_is_comparison: bool = True  # True when comparison is older than baseline
    baseline_properties: object = None   # Optional[DesignProperties]
    comparison_properties: object = None # Optional[DesignProperties]

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, default=str)
