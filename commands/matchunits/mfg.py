# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.
"""Manufacture-side units logic for Match Units. Imports no ``adsk`` module.

The second, independent check the command performs: whether the **Manufacture**
workspace's active unit system agrees with the open document's **Design** units.

This is deliberately a sibling of ``logic.py`` rather than part of it, because
the two checks agree on almost nothing:

| | Design check (``logic.py``) | Manufacture check (here) |
|---|---|---|
| Read | typed enum property | text command output, parsed |
| Write | typed property assignment | ``UnitSystems.Activate <id>`` |
| Direction | document <- application default | Manufacture <- document |
| Granularity | exact unit, length **and** mass | **family**, length only |

The granularity difference is the one that forces the split.
``logic.UnitsState.is_known`` requires both a length and a mass, and
``logic.compare`` returns None unless both sides are complete — the invariant
that stops the design *write* path acting on a half-read. A length-only
comparison run through those types would have to fabricate a mass value, which
``differences``, ``change_plan`` and ``tooltip_text`` would then all report on.
Only ``short_label`` / ``long_label`` are shared, and those are imported.

**Compare families, not units.** Manufacture offers two systems; Design offers
eleven length units. Comparing a design *unit* against a Manufacture *system*
gives a check that can never be satisfied: a design in centimetres would want
"mm", see "mm", still read as different, and prompt again on every single
workspace switch, forever. So both sides are reduced to a family — metric or
imperial — and only a family difference is worth asking about.

Nothing here guesses. An unparseable system list, an unrecognized unit, or a
design unit with no family all resolve to None, which the caller must treat as
"say nothing". This check offers to rewrite a document's settings, so a
plausible wrong answer is worse than no answer (c8c0382).
"""

from dataclasses import dataclass

from .logic import UNKNOWN_LONG, UNKNOWN_SHORT, long_label, short_label

METRIC = "metric"
IMPERIAL = "imperial"

# Which family each design length unit belongs to, keyed by the same
# ``adsk.fusion.DistanceUnits`` member names as ``logic.DISTANCE_UNITS`` and
# resolved against the live enum by :func:`build_families` — same discipline as
# the tables in logic.py, so a renumbered enum cannot mislabel a unit.
#
# Every name in logic.DISTANCE_UNITS must appear here.
# ``test_every_distance_unit_has_a_family`` fails if one is added without a
# family, because the alternative is a unit that silently never prompts.
DISTANCE_FAMILY = {
    "MillimeterDistanceUnits": METRIC,
    "CentimeterDistanceUnits": METRIC,
    "MeterDistanceUnits": METRIC,
    "MicronDistanceUnits": METRIC,
    "HectometerDistanceUnits": METRIC,
    "InchDistanceUnits": IMPERIAL,
    "FootDistanceUnits": IMPERIAL,
    "YardDistanceUnits": IMPERIAL,
    "MileDistanceUnits": IMPERIAL,
    "MilDistanceUnits": IMPERIAL,
    "NauticalMileDistanceUnits": IMPERIAL,
}

# The Manufacture workspace's unit systems, as (family, id, short, sentence).
#
# These ids are NOT adsk enum values. They are the strings the
# ``UnitSystems.Activate <id>`` text command takes and that ``UnitSystems.List``
# reports back, and they have no API equivalent at all — the CAM product has no
# settable units manager. Only these two exist on the build this was written
# against: List run against the CAM product declares exactly these two, so they
# are the only legitimate targets.
MFG_SYSTEMS = (
    (METRIC, "MmMKS", "mm", "millimeters"),
    (IMPERIAL, "InchImperial", "in", "inches"),
)

# Every unit system id observed on any product, classified by family.
#
# Deliberately wider than MFG_SYSTEMS: that tuple is what Manufacture can be
# switched *to*, while this is what it might be found *on*. Run against the
# Design product, UnitSystems.List declares six systems, and reading a
# foot-based ``Imperial`` as "unrecognized" would silently miss a real mismatch
# against a millimetre design.
#
# ``Custom`` is absent on purpose and must stay absent. A custom system is an
# arbitrary pair of units, so it has no family, and inventing one would be a
# plausible wrong answer in front of a document rewrite (c8c0382). An id absent
# from this map entirely lands in the same place: no family, so no prompt.
SYSTEM_FAMILY = {
    "CmMKS": METRIC,
    "MmMKS": METRIC,
    "MMKS": METRIC,
    "InchImperial": IMPERIAL,
    "Imperial": IMPERIAL,
}

# One of each system's display units in Fusion's internal length unit (cm),
# which is what ``UnitsManager.evaluateExpression("1")`` returns. Used only to
# cross-check the id parsed out of ``UnitSystems.List`` against an independent
# API measurement, before anything is rewritten.
MFG_SYSTEM_SCALE = {
    "MmMKS": 0.1,
    "InchImperial": 2.54,
}


def build_families(distance_enum) -> dict:
    """Re-key :data:`DISTANCE_FAMILY` by live enum value.

    Args:
        distance_enum: ``adsk.fusion.DistanceUnits``.

    Returns:
        ``DistanceUnits`` value -> :data:`METRIC` / :data:`IMPERIAL`. Names this
        build's enum does not carry are skipped; ``logic.build_tables`` already
        reports those, so they are not counted twice.
    """
    families = {}
    for name, family in DISTANCE_FAMILY.items():
        value = getattr(distance_enum, name, None)
        if value is not None:
            families[value] = family
    return families


# -- Parsing UnitSystems.List -------------------------------------------------
#
# A parsing contract with Fusion's own diagnostic output, not with a documented
# interface, so every field degrades independently to None.

_SYSTEM_LINE_PREFIX = "UnitSystem name:"
_ACTIVE_LINE_PREFIX = "The active unit system is"
_ID_MARKER = " id: "
_INITIALIZED_MARKER = " initialized:"
_MODELING_LENGTH_MARKER = "ModelingLength"
_UNITS_MARKER = "units: "
_NAME_MARKER = " name:"


@dataclass(frozen=True)
class UnitSystemReport:
    """What ``UnitSystems.List`` said.

    Attributes:
        systems: ``(name, id)`` per declared system, in reported order.
        active_id: The active system's id, resolved by looking its reported
            *name* up among ``systems``. None when the output could not be
            parsed, the active line was absent, or the active name matched no
            declared system.
        active_name: The active system's reported name, kept even when it could
            not be resolved to an id — the thing worth logging in that case.
        active_length_unit: The unit named by the active system's
            ``ModelingLength`` choice, e.g. ``inch``. A second, independent
            reading of the same fact, for the cross-check.
    """

    systems: tuple = ()
    active_id: str = None
    active_name: str = None
    active_length_unit: str = None

    @property
    def ids(self) -> tuple:
        """Every declared system id, in reported order."""
        return tuple(system_id for _name, system_id in self.systems)


def parse_unit_systems(text: str) -> UnitSystemReport:
    """Parse the output of the ``UnitSystems.List`` text command.

    The format, as captured on the build this was written against::

        UnitSystem name: mm modeling length with MKS (...) units id: MmMKS initialized: 1 (base ...)
        UnitSystem name: inch modeling length with imperial (...) units id: InchImperial initialized: 1 (base ...)

        The active unit system is inch modeling length with imperial (...) units
            UnitSystemChoiceById Id : ModelingLength (base UnitSystemChoice units: inch name: Modeling Length (...))

    Three details drive the implementation. The active system is reported by
    **name**, not by id, so the name has to be looked back up among the header
    lines. And a system's name itself contains parentheses, commas and the word
    "units" — so the id is taken from the last ``" id: "`` *before*
    ``" initialized:"``, rather than by splitting the line naively. And the
    name is **not stable across products**: the same ``MmMKS`` is named
    "...second, celsius) units" under the CAM product but
    "...second, Celsius) units" under Design — so the active name is only
    ever matched against header lines from the *same* output, never a literal.

    Args:
        text: Raw command output. Anything empty or not a string yields an
            empty report.

    Returns:
        A :class:`UnitSystemReport`. A format change costs this check its
        voice rather than giving it a wrong answer.
    """
    if not text or not isinstance(text, str):
        return UnitSystemReport()

    systems = []
    active_name = None
    active_length_unit = None

    for raw_line in text.splitlines():
        line = raw_line.strip()

        if line.startswith(_SYSTEM_LINE_PREFIX):
            rest = line[len(_SYSTEM_LINE_PREFIX) :]
            # Drop the trailing " initialized: 1 (base ...)" dump first, so the
            # id search cannot stray into the parenthesised debug noise.
            head = rest.split(_INITIALIZED_MARKER, 1)[0]
            name, separator, system_id = head.rpartition(_ID_MARKER)
            if not separator:
                continue
            name, system_id = name.strip(), system_id.strip()
            if name and system_id:
                systems.append((name, system_id))
            continue

        if line.startswith(_ACTIVE_LINE_PREFIX):
            active_name = line[len(_ACTIVE_LINE_PREFIX) :].strip() or None
            continue

        if _MODELING_LENGTH_MARKER in line and _UNITS_MARKER in line:
            tail = line.split(_UNITS_MARKER, 1)[1]
            active_length_unit = tail.split(_NAME_MARKER, 1)[0].strip() or None

    active_id = None
    if active_name is not None:
        for name, system_id in systems:
            if name == active_name:
                active_id = system_id
                break

    return UnitSystemReport(
        systems=tuple(systems),
        active_id=active_id,
        active_name=active_name,
        active_length_unit=active_length_unit,
    )


# -- Resolving a system -------------------------------------------------------


def family_of_system(system_id: str) -> str:
    """The family a unit system id belongs to.

    Args:
        system_id: An id as reported by ``UnitSystems.List``.

    Returns:
        :data:`METRIC` / :data:`IMPERIAL`, or None for ``Custom`` and for any
        id this module has never seen — both of which mean "say nothing".
    """
    return SYSTEM_FAMILY.get(system_id)


def system_for_family(family: str) -> str:
    """The Manufacture system id for a family, or None if there is none."""
    for candidate_family, system_id, _short, _long in MFG_SYSTEMS:
        if candidate_family == family:
            return system_id
    return None


def system_for_scale(scale, tolerance: float = 1e-6) -> str:
    """The Manufacture system whose display unit measures *scale* internal units.

    The independent cross-check on :func:`parse_unit_systems`: ``scale`` comes
    from ``UnitsManager.evaluateExpression("1")``, so it is measured rather
    than parsed.

    Args:
        scale: One display unit in internal units (cm). Note that ``-1`` is
            ``evaluateExpression``'s documented error return rather than a
            scale, and that it does not raise — hence the explicit
            non-positive rejection.
        tolerance: Absolute match tolerance. Neither 0.1 nor 2.54 is exactly
            representable, so this is never an equality test.

    Returns:
        The matching system id, or None when *scale* matches none of them.
    """
    if scale is None or scale <= 0:
        return None
    for system_id, expected in MFG_SYSTEM_SCALE.items():
        if abs(scale - expected) <= tolerance:
            return system_id
    return None


# Readable names for systems Manufacture may be found on but cannot be switched
# to, so a prompt can still say what it is currently set to.
_OTHER_SYSTEM_LABELS = {
    "CmMKS": ("cm", "centimeters"),
    "MMKS": ("m", "meters"),
    "Imperial": ("ft", "feet"),
}


def short_system_label(system_id: str) -> str:
    """Abbreviated name for a unit system id."""
    for _family, candidate, short, _long in MFG_SYSTEMS:
        if candidate == system_id:
            return short
    labels = _OTHER_SYSTEM_LABELS.get(system_id)
    return labels[0] if labels else UNKNOWN_SHORT


def long_system_label(system_id: str) -> str:
    """Sentence-form name for a unit system id."""
    for _family, candidate, _short, sentence in MFG_SYSTEMS:
        if candidate == system_id:
            return sentence
    labels = _OTHER_SYSTEM_LABELS.get(system_id)
    return labels[1] if labels else UNKNOWN_LONG


# -- The comparison -----------------------------------------------------------


@dataclass(frozen=True)
class MfgComparison:
    """The Manufacture workspace's active unit system against the design's.

    Compared at family granularity by construction: ``target_id`` is derived
    from the design unit's family, so a design in centimetres is satisfied by
    Manufacture being on ``MmMKS`` and does not re-prompt.

    Attributes:
        active_id: The system Manufacture is on now.
        target_id: The system the design's length unit implies.
        design_distance: The design's ``DistanceUnits`` value, for wording.
    """

    active_id: str
    target_id: str
    design_distance: object = None

    @property
    def matches(self) -> bool:
        """True when there is nothing to change.

        Compared by **family**, not by id. Comparing ids would leave any
        Manufacture system that is not itself an activatable target
        permanently mismatched, prompting on every workspace switch forever
        — the same trap that makes the design side family-based.
        """
        return family_of_system(self.active_id) == family_of_system(self.target_id)


def compare(families: dict, design_distance, active_id: str):
    """Pair the Manufacture side up against the design side.

    Args:
        families: Map from :func:`build_families`.
        design_distance: The design's ``DistanceUnits`` value.
        active_id: The active Manufacture system id, from
            :func:`parse_unit_systems`.

    Returns:
        An :class:`MfgComparison`, or None when either side is unusable: an
        unreadable or unrecognized active system, or a design unit with no
        family. Every None case means the check has nothing trustworthy to say
        and must stay silent rather than prompt.
    """
    if not active_id or family_of_system(active_id) is None:
        return None
    family = families.get(design_distance)
    if family is None:
        return None
    target_id = system_for_family(family)
    if target_id is None:
        return None
    return MfgComparison(
        active_id=active_id, target_id=target_id, design_distance=design_distance
    )


# -- Text. ASCII only; these reach a Fusion dialog. ---------------------------


def prompt_text(
    distance_table: dict, comparison: MfgComparison, document_name: str
) -> str:
    """The yes/no question asked on switching into Manufacture."""
    design_units = long_label(distance_table, comparison.design_distance)
    active = long_system_label(comparison.active_id)
    target = long_system_label(comparison.target_id)
    return (
        f'"{document_name}" is in {design_units} in the Design workspace, but '
        f"the Manufacture workspace is set to {active}.\n\n"
        f"Feeds, speeds and toolpath dimensions are entered and shown in "
        f"{active}.\n\n"
        f"Change the Manufacture workspace to {target} to match the design?"
    )


def applied_text(comparison: MfgComparison) -> str:
    """Confirmation of a change that was made."""
    return (
        f"Manufacture units changed from "
        f"{short_system_label(comparison.active_id)} to "
        f"{short_system_label(comparison.target_id)}, matching the design."
    )


def already_matching_text(comparison: MfgComparison) -> str:
    """Report for a check that found nothing to do."""
    return (
        f"The Manufacture workspace is already in "
        f"{long_system_label(comparison.target_id)}, matching the design."
    )


def log_line(distance_table: dict, comparison: MfgComparison) -> str:
    """One-line comparison for the DEBUG log."""
    design_units = short_label(distance_table, comparison.design_distance)
    if comparison.matches:
        return (
            f"manufacture units match (design {design_units}, "
            f"manufacture {comparison.active_id})"
        )
    return (
        f"manufacture units differ - design {design_units} wants "
        f"{comparison.target_id}, manufacture is on {comparison.active_id}"
    )
