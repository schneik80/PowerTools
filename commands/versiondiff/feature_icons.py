# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2022-2026 IMA LLC

"""Fusion 360 feature-type → icon mapping for the version diff report.

Each key is the short class name extracted from entity.objectType
(e.g. ``entity.objectType.split('::')[-1]``).  The value is the SVG
filename inside ``resources/feature_icons/``.

The mapping is intentionally broad — unmapped types fall back to a
generic icon at render time.
"""

import base64
import os
from functools import lru_cache

# Directory that holds the feature-icon SVGs
_ICON_DIR = os.path.join(os.path.dirname(__file__), "resources", "feature_icons")

# ---------------------------------------------------------------------------
# feature_type  →  svg filename  (without path)
# ---------------------------------------------------------------------------
FEATURE_ICON_MAP: dict[str, str] = {
    # ── Solid modeling ────────────────────────────────────────────────
    "ExtrudeFeature":           "solid-extrude.svg",
    "RevolveFeature":           "solid-revolve.svg",
    "SweepFeature":             "solid-sweep.svg",
    "LoftFeature":              "solid-loft.svg",
    "RibFeature":               "solid-rib.svg",
    "WebFeature":               "solid-web.svg",
    "CoilFeature":              "solid-coil.svg",
    "HoleFeature":              "solid-hole.svg",
    "ThreadFeature":            "solid-thread.svg",
    "FilletFeature":            "solid-fillet.svg",
    "ChamferFeature":           "solid-chamfer.svg",
    "ShellFeature":             "solid-shell.svg",
    "DraftFeature":             "solid-draft.svg",
    "ThickenFeature":           "solid-thicken.svg",
    "BoxFeature":               "solid-primitive_box.svg",
    "CylinderFeature":          "solid-primitive_cylinder.svg",
    "SphereFeature":            "solid-primitive_sphere.svg",
    "TorusFeature":             "solid-primitive_torus.svg",
    "PipeFeature":              "solid-primitive_pipe.svg",
    "ScaleFeature":             "sketch-scale.svg",
    "MoveFeature":              "assembly-move.svg",
    "CombineFeature":           "solid-api.svg",
    "SplitBodyFeature":         "solid-api.svg",
    "SplitFaceFeature":         "solid-api.svg",
    "MirrorFeature":            "symmterytype-mirror.svg",
    "DeleteFaceFeature":        "solid-api.svg",
    "ReplaceFaceFeature":       "solid-api.svg",
    "OffsetFacesFeature":       "surface-offset.svg",
    "PressFeature":             "solid-api.svg",
    "RemoveFeature":            "solid-api.svg",
    "CopyPasteBodies":          "solid-api.svg",
    "ReplaceBodyFeature":       "solid-api.svg",
    "ReverseNormalFeature":     "solid-api.svg",
    "SilhouetteSplitFeature":   "solid-api.svg",
    "FullRoundFilletFeature":   "solid-full_round_fillet.svg",
    "RuleFilletFeature":        "solid-rulefillet.svg",

    # ── Surface modeling ──────────────────────────────────────────────
    "ExtendFeature":            "surface-extend.svg",
    "OffsetFeature":            "surface-offset.svg",
    "PatchFeature":             "surface-patch.svg",
    "RuledSurfaceFeature":      "surface-ruled.svg",
    "StitchFeature":            "surface-stitch.svg",
    "UnstitchFeature":          "surface-unstitch.svg",
    "TrimFeature":              "surface-trim.svg",
    "BoundaryFillFeature":      "surface-patch.svg",
    "MidSurfaceFeature":        "surface-midsurfaceshell.svg",
    "SurfaceDeleteFaceFeature": "surface-trim.svg",
    "TrimBrepFeature":          "surface-trim.svg",

    # ── Sketch ────────────────────────────────────────────────────────
    "Sketch":                   "sketch-sketch_feature.svg",

    # ── Construction geometry ─────────────────────────────────────────
    "ConstructionAxis":         "construction-axis_two_points.svg",
    "ConstructionPlane":        "construction-plane_offset.svg",
    "ConstructionPoint":        "construction-point_vertex.svg",

    # ── Patterns ──────────────────────────────────────────────────────
    "CircularPatternFeature":   "sketch-pattern_circular.svg",
    "RectangularPatternFeature":"sketch-pattern_rectangular.svg",

    # ── Assembly / joints ─────────────────────────────────────────────
    "Joint":                    "assembly-joint.svg",
    "AsBuiltJoint":             "assembly-jointasbuilt.svg",
    "JointOrigin":              "assembly-joint.svg",
    "RigidGroup":               "assembly-rigidgroup.svg",
    "Occurrence":               "assembly-place.svg",
    "XREF":                     "assembly-place.svg",

    # ── Form / T-Spline ──────────────────────────────────────────────
    "FormFeature":              "tspline-tsplinebasefeature.svg",

    # ── Mesh ──────────────────────────────────────────────────────────
    "MeshFeature":              "mesh-meshbody.svg",
    "MeshBody":                 "mesh-meshbody.svg",
    "TriMeshBrepConvertFeature":"icons-convert2mesh.svg",

    # ── Other ─────────────────────────────────────────────────────────
    "BaseFeature":              "tspline-tsplinebasefeature.svg",
    "CanvasDecal":              "solid-api.svg",
    "Decal":                    "solid-api.svg",
    "SnapShotFeature":          "assembly-snapshot.svg",
    "PlaneAndOffsetFeature":    "construction-plane_offset.svg",

    # ── Plastic features ──────────────────────────────────────────────
    "BossFeature":              "plasticfeatures-boss.svg",
    "LipFeature":               "plasticfeatures-lip.svg",
    "RestFeature":              "plasticfeatures-rest.svg",
    "SnapFitFeature":           "plasticfeatures-snapfit.svg",
}

# The fallback icon used when no mapping exists for a feature type
_FALLBACK_ICON = "solid-api.svg"


@lru_cache(maxsize=256)
def get_icon_data_uri(feature_type: str) -> str:
    """Return a base64 data-URI string for the given feature type's SVG icon.

    The result is cached so repeated calls for the same type are fast.
    Returns an empty string if the icon file cannot be read.
    """
    filename = FEATURE_ICON_MAP.get(feature_type, _FALLBACK_ICON)
    filepath = os.path.join(_ICON_DIR, filename)

    if not os.path.isfile(filepath):
        return ""

    try:
        with open(filepath, "rb") as f:
            svg_bytes = f.read()
        b64 = base64.b64encode(svg_bytes).decode("ascii")
        return f"data:image/svg+xml;base64,{b64}"
    except OSError:
        return ""


def icon_img_tag(feature_type: str) -> str:
    """Return an ``<img>`` HTML tag for the feature type icon.

    Returns an empty string when no icon is available, so the report
    degrades gracefully.
    """
    uri = get_icon_data_uri(feature_type)
    if not uri:
        return ""
    return (
        f'<img src="{uri}" alt="" '
        f'style="width:16px;height:16px;vertical-align:middle;margin-right:4px;opacity:0.8;">'
    )
