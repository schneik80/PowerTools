# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2022-2026 IMA LLC
"""Part number scheme registry and formatting helpers.

A "scheme" is a prefix + a monotonic counter shared across the active hub.
Counters are persisted in the Pn-Cache JSON. This module has no dependency on
the Fusion API so it can be unit-tested in isolation.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

# ---------------------------------------------------------------------------
# Scheme definitions
# ---------------------------------------------------------------------------

# Ordered so dropdowns have a stable presentation.
SCHEMES: List[Tuple[str, str]] = [
    ("PRT", "Custom part"),
    ("ASY", "Assembly"),
    ("WLD", "Weldment"),
    ("COT", "Commercial off-the-shelf"),
    ("TOL", "Tooling / fixture / jig"),
    ("DWG", "Drawing (controlled document)"),
]

SCHEME_PREFIXES: List[str] = [p for p, _ in SCHEMES]

SCHEME_LABEL: Dict[str, str] = {p: f"{p} — {desc}" for p, desc in SCHEMES}

# ---------------------------------------------------------------------------
# Intent filtering
# ---------------------------------------------------------------------------

# Maps a DesignIntentTypes integer value to the list of prefixes allowed for
# that intent. Values come from adsk.fusion.DesignIntentTypes:
#   PartDesignIntentType     = 0
#   AssemblyDesignIntentType = 1
#   HybridDesignIntentType   = 2
INTENT_PART = 0
INTENT_ASSEMBLY = 1
INTENT_HYBRID = 2

_INTENT_TO_PREFIXES: Dict[int, List[str]] = {
    INTENT_PART:     ["PRT", "COT", "TOL"],
    INTENT_ASSEMBLY: ["ASY", "WLD", "TOL"],
    INTENT_HYBRID:   ["PRT", "ASY", "WLD", "COT", "TOL"],
}

# DWG is reserved for the drawing command; never appears in the design command.
DRAWING_PREFIX = "DWG"


def prefixes_for_intent(intent_value: int) -> List[str]:
    """Return allowed scheme prefixes for a given intent, in display order.

    Unknown/undetectable intent (e.g. occurrence whose intent we can't read)
    falls back to the HYBRID superset so the user can still choose.
    """
    return list(_INTENT_TO_PREFIXES.get(intent_value, _INTENT_TO_PREFIXES[INTENT_HYBRID]))


# ---------------------------------------------------------------------------
# Number formatting
# ---------------------------------------------------------------------------

NUMBER_WIDTH = 6  # PRT-000001


def format_number(prefix: str, n: int) -> str:
    """Format ``prefix`` + zero-padded ``n`` (e.g. format_number("PRT", 42) -> "PRT-000042")."""
    return f"{prefix}-{n:0{NUMBER_WIDTH}d}"
