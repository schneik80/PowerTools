# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.
"""Units comparison for Match Units. Imports no ``adsk`` module.

Every decision about what counts as a mismatch, which predefined unit system a
pair of units corresponds to, and how the outcome reads in a dialog lives here.
``entry.py`` holds only the Fusion contact: reading the two sides and writing
the document's units back.

The unit tables are keyed by the ``adsk.fusion`` enum **member name**, not by
its integer value, and are resolved against the live enum classes once at
start-up (:func:`build_tables`). Hardcoding the integers would mean a silently
mislabelled unit if Autodesk ever renumbered ``DistanceUnits``, and a plausible
wrong unit on a dialog that offers to rewrite the document is worse than an
error. A name this build's enum does not carry is dropped and reported in
``UnitTables.unknown_names`` rather than guessed at.

Labels are deliberately ASCII: they end up in a Fusion tooltip, which is why
the micron is ``um`` and not the SI symbol.
"""

from dataclasses import dataclass

# (enum member name, short label, sentence label) for adsk.fusion.DistanceUnits.
DISTANCE_UNITS = (
    ("MillimeterDistanceUnits", "mm", "millimeters"),
    ("CentimeterDistanceUnits", "cm", "centimeters"),
    ("MeterDistanceUnits", "m", "meters"),
    ("InchDistanceUnits", "in", "inches"),
    ("FootDistanceUnits", "ft", "feet"),
    ("YardDistanceUnits", "yd", "yards"),
    ("MicronDistanceUnits", "um", "microns"),
    ("HectometerDistanceUnits", "hm", "hectometers"),
    ("MileDistanceUnits", "mi", "miles"),
    ("MilDistanceUnits", "mil", "mils"),
    ("NauticalMileDistanceUnits", "nmi", "nautical miles"),
)

# The same, for adsk.fusion.MassUnits.
MASS_UNITS = (
    ("GramMassUnits", "g", "grams"),
    ("KilogramMassUnits", "kg", "kilograms"),
    ("PoundMassUnits", "lb", "pounds"),
    ("OunceMassUnits", "oz", "ounces"),
    ("TonMassUnits", "ton", "tons"),
    ("SlugMassUnits", "slug", "slugs"),
)

# The (distance, mass) pairs Fusion exposes as a single adsk.fusion.UnitSystems
# value, as (system name, distance name, mass name). Assigning one of these to
# unitSystem sets both halves at once; any other pair has to be written field by
# field, which leaves unitSystem reporting Custom. CustomUnitSystem is
# deliberately absent -- it is the result of a field-by-field write, never a
# target.
UNIT_SYSTEMS = (
    ("MillimeterGramUnitSystem", "MillimeterDistanceUnits", "GramMassUnits"),
    ("CentimeterGramUnitSystem", "CentimeterDistanceUnits", "GramMassUnits"),
    ("MeterKilogramUnitSystem", "MeterDistanceUnits", "KilogramMassUnits"),
    ("InchOunceUnitSystem", "InchDistanceUnits", "OunceMassUnits"),
    ("FootPoundUnitSystem", "FootDistanceUnits", "PoundMassUnits"),
)

# Stand-ins for a unit this build's enum does not name. They read as an
# admission rather than as a unit, which is the point: the command would rather
# say it does not recognize a unit than put a plausible wrong one in front of
# someone about to rewrite a document.
UNKNOWN_SHORT = "unknown"
UNKNOWN_LONG = "an unrecognized unit"


@dataclass(frozen=True)
class UnitNames:
    """The two ways one unit is written.

    Attributes:
        short: Abbreviation for a tooltip or a log line, e.g. ``mm``.
        long: Sentence form for a prompt, e.g. ``millimeters``.
    """

    short: str
    long: str


@dataclass(frozen=True)
class UnitTables:
    """Enum values resolved against this Fusion build, ready to look up.

    Attributes:
        distance: ``DistanceUnits`` value -> :class:`UnitNames`.
        mass: ``MassUnits`` value -> :class:`UnitNames`.
        systems: ``(distance value, mass value)`` -> ``UnitSystems`` value, for
            the pairs Fusion can set in one assignment.
        unknown_names: Enum member names absent from this build -- distance,
            then mass, then unit systems. Non-empty means the build moved and
            this module needs a look; the affected units fall back to
            :data:`UNKNOWN_SHORT` / :data:`UNKNOWN_LONG`.
    """

    distance: dict
    mass: dict
    systems: dict
    unknown_names: tuple


def build_tables(distance_enum, mass_enum, system_enum) -> UnitTables:
    """Resolve the name-keyed tables above against the live enum classes.

    Args:
        distance_enum: ``adsk.fusion.DistanceUnits``.
        mass_enum: ``adsk.fusion.MassUnits``.
        system_enum: ``adsk.fusion.UnitSystems``.

    Returns:
        The populated :class:`UnitTables`. Names the enums do not carry are
        skipped and collected in ``unknown_names`` instead of raising, so an
        API that gained or lost a unit cannot stop the command from loading.
    """
    missing = []

    def resolve(enum_class, table):
        out = {}
        for name, short, sentence in table:
            value = getattr(enum_class, name, None)
            if value is None:
                missing.append(name)
                continue
            out[value] = UnitNames(short, sentence)
        return out

    distance = resolve(distance_enum, DISTANCE_UNITS)
    mass = resolve(mass_enum, MASS_UNITS)

    systems = {}
    for system_name, distance_name, mass_name in UNIT_SYSTEMS:
        system_value = getattr(system_enum, system_name, None)
        distance_value = getattr(distance_enum, distance_name, None)
        mass_value = getattr(mass_enum, mass_name, None)
        if system_value is None or distance_value is None or mass_value is None:
            missing.append(system_name)
            continue
        systems[(distance_value, mass_value)] = system_value

    return UnitTables(
        distance=distance,
        mass=mass,
        systems=systems,
        unknown_names=tuple(missing),
    )


@dataclass(frozen=True)
class UnitsState:
    """One side of the comparison: a length unit and a mass unit.

    Attributes:
        distance: A ``DistanceUnits`` value, or None if it could not be read.
        mass: A ``MassUnits`` value, or None if it could not be read.
    """

    distance: object = None
    mass: object = None

    @property
    def is_known(self) -> bool:
        """True when both halves were read."""
        return self.distance is not None and self.mass is not None


@dataclass(frozen=True)
class Comparison:
    """A document's units set against the application default.

    Attributes:
        document: What the open design is in.
        application: What Fusion's Default Units preference says a new design
            should be in.
    """

    document: UnitsState
    application: UnitsState

    @property
    def distance_matches(self) -> bool:
        return self.document.distance == self.application.distance

    @property
    def mass_matches(self) -> bool:
        return self.document.mass == self.application.mass

    @property
    def matches(self) -> bool:
        """True when there is nothing to change."""
        return self.distance_matches and self.mass_matches

    @property
    def differences(self) -> tuple:
        """Which halves differ, as ``("length", "mass")`` in that order."""
        out = []
        if not self.distance_matches:
            out.append("length")
        if not self.mass_matches:
            out.append("mass")
        return tuple(out)


def compare(document: UnitsState, application: UnitsState):
    """Pair the two sides up for reporting.

    Args:
        document: The open design's units.
        application: The application default units.

    Returns:
        A :class:`Comparison`, or None when either side is incomplete. A
        half-read side cannot be compared, and guessing at the missing half
        would either prompt for a change that is not needed or stay silent
        about one that is.
    """
    if not (document.is_known and application.is_known):
        return None
    return Comparison(document, application)


@dataclass(frozen=True)
class ChangePlan:
    """How to write the application default onto the document.

    Exactly one shape is ever populated: ``system`` for a pair Fusion names as
    a unit system, otherwise ``distance`` and/or ``mass`` for the halves that
    actually differ.

    Attributes:
        system: A ``UnitSystems`` value to assign to
            ``FusionUnitsManager.unitSystem``, or None.
        distance: A ``DistanceUnits`` value to assign to
            ``distanceDisplayUnits``, or None to leave it alone.
        mass: A ``MassUnits`` value to assign to ``massDisplayUnits``, or None
            to leave it alone.
    """

    system: object = None
    distance: object = None
    mass: object = None

    @property
    def is_empty(self) -> bool:
        """True when there is nothing to write."""
        return self.system is None and self.distance is None and self.mass is None


def change_plan(tables: UnitTables, comparison: Comparison) -> ChangePlan:
    """Work out the smallest set of writes that makes the document match.

    Prefers the single ``unitSystem`` assignment when the target pair is one
    Fusion names, because that is what the user sees in Document Settings; a
    field-by-field write reaches the same units but reports the system as
    Custom.

    Args:
        tables: Tables from :func:`build_tables`.
        comparison: The comparison to satisfy.

    Returns:
        The plan. Empty when the units already match.
    """
    if comparison.matches:
        return ChangePlan()

    target = comparison.application
    system = tables.systems.get((target.distance, target.mass))
    if system is not None:
        return ChangePlan(system=system)

    return ChangePlan(
        distance=None if comparison.distance_matches else target.distance,
        mass=None if comparison.mass_matches else target.mass,
    )


# -- Text ---------------------------------------------------------------------


def short_label(table: dict, value) -> str:
    """Abbreviated name for *value*, or :data:`UNKNOWN_SHORT`."""
    names = table.get(value)
    return names.short if names else UNKNOWN_SHORT


def long_label(table: dict, value) -> str:
    """Sentence-form name for *value*, or :data:`UNKNOWN_LONG`."""
    names = table.get(value)
    return names.long if names else UNKNOWN_LONG


def describe(tables: UnitTables, state: UnitsState) -> str:
    """Compact form for a tooltip or a log line, e.g. ``mm, g``."""
    return (
        f"{short_label(tables.distance, state.distance)}, "
        f"{short_label(tables.mass, state.mass)}"
    )


def describe_long(tables: UnitTables, state: UnitsState) -> str:
    """Sentence form for a prompt, e.g. ``millimeters and grams``."""
    return (
        f"{long_label(tables.distance, state.distance)} and "
        f"{long_label(tables.mass, state.mass)}"
    )


def prompt_text(tables: UnitTables, comparison: Comparison, document_name: str) -> str:
    """The yes/no question asked when a mismatched document opens."""
    return (
        f'"{document_name}" is in {describe_long(tables, comparison.document)}.\n'
        f"Your Fusion default units are "
        f"{describe_long(tables, comparison.application)}.\n\n"
        "Change this document to match your default units?"
    )


def tooltip_text(tables: UnitTables, comparison: Comparison) -> str:
    """State-dependent tooltip for the Inspect panel button. ASCII only."""
    if comparison.matches:
        return (
            f"Document units match your Fusion default "
            f"({describe(tables, comparison.application)})."
        )
    return (
        f"Document is in {describe(tables, comparison.document)}; your Fusion "
        f"default is {describe(tables, comparison.application)}. Click to "
        "change the document to match."
    )


def applied_text(tables: UnitTables, comparison: Comparison) -> str:
    """Confirmation of a change that was made."""
    return (
        f"Document units changed from {describe(tables, comparison.document)} "
        f"to {describe(tables, comparison.application)}."
    )


def already_matching_text(tables: UnitTables, comparison: Comparison) -> str:
    """Report for a click on a document that already matches."""
    return (
        f"This document is already in "
        f"{describe_long(tables, comparison.application)}, matching your "
        "Fusion default units. Nothing to change."
    )


def log_line(tables: UnitTables, comparison: Comparison) -> str:
    """One-line comparison for the DEBUG log."""
    if comparison.matches:
        return f"units match ({describe(tables, comparison.document)})"
    return (
        f"units differ in {' and '.join(comparison.differences)} - "
        f"document {describe(tables, comparison.document)}, "
        f"default {describe(tables, comparison.application)}"
    )
