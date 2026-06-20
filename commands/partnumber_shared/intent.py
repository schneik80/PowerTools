# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2022-2026 IMA LLC
"""Design-intent helpers and local-component enumeration.

A "target" is anything that can receive a part number in the Assign Part
Numbers command: the root component, plus each top-level local (non-referenced)
occurrence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

import adsk.core
import adsk.fusion

from . import schemes


# Fusion auto-generates placeholder part numbers using the timestamp
# YYYY-MM-DD-HH-MM-SS-mmm. The Fusion UI cosmetically displays these as
# "<ComponentName>: <timestamp>", but ``Component.partNumber`` returns only
# the bare timestamp. The regex accepts both forms defensively so we don't
# trigger the overwrite-confirm flow for either.
_FUSION_AUTO_PN_RE = re.compile(
    r"^(?:.*:\s*)?\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2}-\d{3}\s*$"
)


def is_fusion_auto_pn(pn: str) -> bool:
    """True if ``pn`` looks like Fusion's auto-generated ``Name:timestamp`` pattern."""
    if not pn:
        return False
    return bool(_FUSION_AUTO_PN_RE.match(pn.strip()))


@dataclass
class Target:
    """A single row in the assign-part-numbers dialog.

    ``component`` is the component whose ``partNumber`` will be set on OK.
    ``intent_value`` is the best-guess DesignIntentTypes for that component
    (used to filter the scheme dropdown for that row).
    ``label`` is what the user sees in the first column of the table.
    ``current_pn`` is the existing partNumber, displayed as read-only.
    """

    label: str
    component: adsk.fusion.Component
    intent_value: int
    current_pn: str = ""
    is_root: bool = False
    # Populated later once a scheme is chosen + sequential number resolved.
    chosen_prefix: Optional[str] = None
    chosen_number: Optional[int] = None


# ---------------------------------------------------------------------------
# Intent detection
# ---------------------------------------------------------------------------


def intent_of_design(design: adsk.fusion.Design) -> int:
    """Return the active design's intent as an int (Part=0, Assembly=1, Hybrid=2).

    Falls back to Hybrid (superset) if the property is unavailable.
    """
    try:
        return int(design.designIntent)
    except Exception:
        return schemes.INTENT_HYBRID


def intent_of_component(component: adsk.fusion.Component,
                        parent_intent: int) -> int:
    """Best-effort intent classification for an arbitrary component.

    The Fusion API exposes designIntent on Design, not on individual
    Components. For local components we inherit the parent design's intent;
    this keeps filtering consistent with the stated rules.
    """
    # Design-level intent is authoritative for root. For any other local
    # component we inherit the parent. (Referenced components are filtered
    # out upstream, so this is only called for locals.)
    _ = component  # intentionally unused; kept for future per-component logic
    return parent_intent


# ---------------------------------------------------------------------------
# Local-component enumeration
# ---------------------------------------------------------------------------


def has_local_components(design: adsk.fusion.Design) -> bool:
    """True if the design has at least one top-level non-referenced occurrence."""
    try:
        root = design.rootComponent
        occs = root.occurrences
        for i in range(occs.count):
            occ = occs.item(i)
            if not occ.isReferencedComponent:
                return True
    except Exception:
        return False
    return False


def iter_targets(design: adsk.fusion.Design) -> List[Target]:
    """Return the ordered list of numbering targets for a design.

    The root component is always first. Top-level local (non-referenced)
    occurrences follow in the order the API enumerates them. Referenced
    (linked/xref) occurrences are skipped — they belong to their own source
    design and already have their own part numbers.

    Local components are deduplicated by component entity token so the same
    local component that appears multiple times as different occurrences
    only shows up once in the dialog.
    """
    targets: List[Target] = []
    parent_intent = intent_of_design(design)

    root = design.rootComponent
    targets.append(
        Target(
            label=root.name,
            component=root,
            intent_value=parent_intent,
            current_pn=_safe_pn(root),
            is_root=True,
        )
    )

    seen_tokens: set = set()
    try:
        occs = root.occurrences
        for i in range(occs.count):
            occ = occs.item(i)
            if occ.isReferencedComponent:
                continue
            comp = occ.component
            if comp is None:
                continue
            token = _safe_token(comp)
            if token and token in seen_tokens:
                continue
            if token:
                seen_tokens.add(token)
            targets.append(
                Target(
                    label=comp.name,
                    component=comp,
                    intent_value=intent_of_component(comp, parent_intent),
                    current_pn=_safe_pn(comp),
                    is_root=False,
                )
            )
    except Exception:
        pass

    return targets


# ---------------------------------------------------------------------------
# Safe accessors (Fusion property reads occasionally throw on detached objects)
# ---------------------------------------------------------------------------


def _safe_pn(component: adsk.fusion.Component) -> str:
    """Return the component's user-assigned part number, or "" if none.

    Filters out Fusion's auto-generated ``YYYY-MM-DD-HH-MM-SS-mmm``
    placeholders (the API returns a bare timestamp; the UI cosmetically
    prepends the component name). Those carry no intent and shouldn't
    trigger the overwrite-confirm flow.
    """
    try:
        pn = component.partNumber or ""
    except Exception:
        return ""
    if is_fusion_auto_pn(pn):
        return ""
    return pn


# ---------------------------------------------------------------------------
# MFGDM model-ID access — DO NOT call from command_created or any other
# synchronous entry point.
#
# Per Autodesk's sample code and the MFGDM API preview docs, accessing
# ``component.dataComponent.mfgdmModelId`` is only safe from inside an
# MFGDMDataReady event callback. Reading it from command_created and then
# showing a modal messageBox + args.command.doExecute(True) was observed to
# crash Fusion on dismiss.
#
# The helpers below are retained because they may be useful from inside a
# properly-registered MFGDMDataReady handler in a future refactor, but they
# must not be invoked from a regular command callback. The current
# assignment flow relies on the readback verification after
# ``component.partNumber = value`` to detect silent-set failures instead.
# ---------------------------------------------------------------------------


def mfgdm_model_id(component: adsk.fusion.Component) -> str:  # noqa: D401
    """Return the component's MFGDM model ID, or "" if not yet available.

    .. warning::
       Only safe to call from within an ``MFGDMDataReady`` event handler.
       Calling this from ``command_created`` or similar synchronous contexts
       has been observed to destabilize Fusion. See module-level comment.
    """
    try:
        data = component.dataComponent
    except Exception:
        return ""
    if data is None:
        return ""
    try:
        return data.mfgdmModelId or ""
    except Exception:
        return ""


def targets_missing_model_id(targets: List[Target]) -> List[Target]:
    """Return the subset of ``targets`` whose components lack an MFGDM model ID.

    .. warning::
       Only safe to call from within an ``MFGDMDataReady`` event handler.
       See :func:`mfgdm_model_id` for the rationale.
    """
    missing: List[Target] = []
    for t in targets:
        if not mfgdm_model_id(t.component):
            missing.append(t)
    return missing


def _safe_token(component: adsk.fusion.Component) -> str:
    try:
        return component.entityToken or ""
    except Exception:
        return ""
