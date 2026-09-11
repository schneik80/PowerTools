"""Unit tests for the Match Units pure-logic helpers.

Exercises the decision the command turns on -- whether a document's units agree
with the application default, and the smallest set of writes that makes them
agree -- plus the wording it reports with.

``logic.py`` imports no ``adsk`` module, but it does have to resolve its
name-keyed unit tables against the live ``adsk.fusion`` enum classes. The
conftest fabricates ``adsk`` as a MagicMock, whose attribute access answers
every name with a new mock rather than with an integer, so the enums are stood
in for by the plain classes below -- which is also what lets a test drop a
member and check that the table degrades instead of raising.
"""

import importlib
from pathlib import Path

PT_PKG = Path(__file__).resolve().parent.parent.name
logic = importlib.import_module(f"{PT_PKG}.commands.matchunits.logic")


class DistanceUnits:
    """Stand-in for adsk.fusion.DistanceUnits, values as documented."""

    MillimeterDistanceUnits = 0
    CentimeterDistanceUnits = 1
    MeterDistanceUnits = 2
    InchDistanceUnits = 3
    FootDistanceUnits = 4
    YardDistanceUnits = 5
    MicronDistanceUnits = 6
    HectometerDistanceUnits = 7
    MileDistanceUnits = 8
    MilDistanceUnits = 9
    NauticalMileDistanceUnits = 10


class MassUnits:
    """Stand-in for adsk.fusion.MassUnits."""

    GramMassUnits = 0
    KilogramMassUnits = 1
    PoundMassUnits = 2
    OunceMassUnits = 3
    TonMassUnits = 4
    SlugMassUnits = 5


class UnitSystems:
    """Stand-in for adsk.fusion.UnitSystems."""

    CustomUnitSystem = 0
    MillimeterGramUnitSystem = 1
    CentimeterGramUnitSystem = 2
    MeterKilogramUnitSystem = 3
    InchOunceUnitSystem = 4
    FootPoundUnitSystem = 5


TABLES = logic.build_tables(DistanceUnits, MassUnits, UnitSystems)


def without(enum_class, *names):
    """A copy of *enum_class* with the named members removed.

    ``del`` on a subclass cannot remove an inherited attribute, so the trimmed
    stand-in is rebuilt from the original's members rather than derived from it.
    """
    members = {
        name: value
        for name, value in vars(enum_class).items()
        if not name.startswith("_") and name not in names
    }
    return type(f"Trimmed{enum_class.__name__}", (), members)


MM_G = logic.UnitsState(DistanceUnits.MillimeterDistanceUnits, MassUnits.GramMassUnits)
IN_OZ = logic.UnitsState(DistanceUnits.InchDistanceUnits, MassUnits.OunceMassUnits)
MM_KG = logic.UnitsState(
    DistanceUnits.MillimeterDistanceUnits, MassUnits.KilogramMassUnits
)
IN_G = logic.UnitsState(DistanceUnits.InchDistanceUnits, MassUnits.GramMassUnits)


# -- Tables -------------------------------------------------------------------


def test_tables_cover_every_documented_unit() -> None:
    """Every name in the module's tables resolves against the real enums."""
    assert TABLES.unknown_names == ()
    assert len(TABLES.distance) == len(logic.DISTANCE_UNITS)
    assert len(TABLES.mass) == len(logic.MASS_UNITS)
    assert len(TABLES.systems) == len(logic.UNIT_SYSTEMS)


def test_a_unit_this_build_does_not_name_is_reported_not_guessed() -> None:
    """A dropped enum member degrades to a report, never to a wrong label."""

    tables = logic.build_tables(
        without(DistanceUnits, "MilDistanceUnits"), MassUnits, UnitSystems
    )

    assert "MilDistanceUnits" in tables.unknown_names
    assert logic.short_label(tables.distance, DistanceUnits.MilDistanceUnits) == (
        logic.UNKNOWN_SHORT
    )
    # The units that are still named keep working.
    assert logic.short_label(tables.distance, DistanceUnits.InchDistanceUnits) == "in"


def test_a_missing_unit_system_drops_only_that_system() -> None:
    """A system whose parts cannot be resolved is skipped, not half-built."""

    tables = logic.build_tables(
        DistanceUnits, MassUnits, without(UnitSystems, "FootPoundUnitSystem")
    )

    assert tables.unknown_names == ("FootPoundUnitSystem",)
    assert (
        DistanceUnits.FootDistanceUnits,
        MassUnits.PoundMassUnits,
    ) not in tables.systems
    assert (
        tables.systems[(DistanceUnits.MillimeterDistanceUnits, MassUnits.GramMassUnits)]
        == UnitSystems.MillimeterGramUnitSystem
    )


def test_unknown_names_come_out_in_table_order() -> None:
    """Distance first, then mass, then systems -- the order they are declared."""

    tables = logic.build_tables(
        without(DistanceUnits, "YardDistanceUnits"),
        without(MassUnits, "SlugMassUnits"),
        UnitSystems,
    )

    assert tables.unknown_names == ("YardDistanceUnits", "SlugMassUnits")


# -- Comparing -----------------------------------------------------------------


def test_identical_units_match() -> None:
    comparison = logic.compare(MM_G, MM_G)

    assert comparison.matches
    assert comparison.differences == ()


def test_both_halves_can_differ() -> None:
    comparison = logic.compare(IN_OZ, MM_G)

    assert not comparison.matches
    assert comparison.differences == ("length", "mass")


def test_mass_alone_can_differ() -> None:
    """Length agreeing is not enough; the mass unit is part of the comparison."""
    comparison = logic.compare(MM_KG, MM_G)

    assert not comparison.matches
    assert comparison.differences == ("mass",)
    assert comparison.distance_matches
    assert not comparison.mass_matches


def test_length_alone_can_differ() -> None:
    comparison = logic.compare(IN_G, MM_G)

    assert comparison.differences == ("length",)


def test_a_half_read_side_cannot_be_compared() -> None:
    """Missing either half yields None, so nothing is prompted on a guess."""
    assert logic.compare(logic.UnitsState(None, MassUnits.GramMassUnits), MM_G) is None
    assert (
        logic.compare(MM_G, logic.UnitsState(DistanceUnits.InchDistanceUnits, None))
        is None
    )
    assert logic.compare(logic.UnitsState(), logic.UnitsState()) is None


def test_a_zero_valued_unit_is_a_real_reading() -> None:
    """Millimeter and gram are both enum value 0; neither counts as unread."""
    assert MM_G.is_known
    assert logic.compare(MM_G, MM_G) is not None


# -- Planning the change -------------------------------------------------------


def test_matching_units_plan_no_writes() -> None:
    plan = logic.change_plan(TABLES, logic.compare(MM_G, MM_G))

    assert plan.is_empty


def test_a_predefined_pair_is_set_in_one_assignment() -> None:
    """Both halves named by a UnitSystems value go through unitSystem."""
    plan = logic.change_plan(TABLES, logic.compare(IN_OZ, MM_G))

    assert plan.system == UnitSystems.MillimeterGramUnitSystem
    assert plan.distance is None
    assert plan.mass is None
    assert not plan.is_empty


def test_the_predefined_pair_is_chosen_by_the_target_not_the_document() -> None:
    """The plan aims at the application default, whatever the document is in."""
    plan = logic.change_plan(TABLES, logic.compare(MM_G, IN_OZ))

    assert plan.system == UnitSystems.InchOunceUnitSystem


def test_a_custom_pair_is_set_field_by_field() -> None:
    """No UnitSystems value covers mm + kg, so both fields are written."""
    plan = logic.change_plan(TABLES, logic.compare(IN_OZ, MM_KG))

    assert plan.system is None
    assert plan.distance == DistanceUnits.MillimeterDistanceUnits
    assert plan.mass == MassUnits.KilogramMassUnits


def test_a_custom_pair_leaves_the_half_that_already_agrees_alone() -> None:
    """Only the differing half is written, so nothing is set redundantly."""
    plan = logic.change_plan(TABLES, logic.compare(MM_G, MM_KG))

    assert plan.system is None
    assert plan.distance is None
    assert plan.mass == MassUnits.KilogramMassUnits


def test_every_predefined_system_is_reachable_as_a_plan() -> None:
    """Each documented pair resolves to its own system, none to Custom."""
    for pair, system in TABLES.systems.items():
        target = logic.UnitsState(*pair)
        plan = logic.change_plan(TABLES, logic.compare(IN_OZ, target))

        if target == IN_OZ:
            assert plan.is_empty
            continue
        assert plan.system == system
        assert plan.system != UnitSystems.CustomUnitSystem


# -- Wording -------------------------------------------------------------------


def test_short_and_long_descriptions() -> None:
    assert logic.describe(TABLES, MM_G) == "mm, g"
    assert logic.describe_long(TABLES, IN_OZ) == "inches and ounces"


def test_the_prompt_names_the_document_and_both_sides() -> None:
    text = logic.prompt_text(TABLES, logic.compare(IN_OZ, MM_G), "Bracket v12")

    assert "Bracket v12" in text
    assert "inches and ounces" in text
    assert "millimeters and grams" in text
    assert text.rstrip().endswith("?")


def test_the_tooltip_says_which_state_it_is_in() -> None:
    matched = logic.tooltip_text(TABLES, logic.compare(MM_G, MM_G))
    differing = logic.tooltip_text(TABLES, logic.compare(IN_OZ, MM_G))

    assert "match" in matched
    assert "in, oz" in differing and "mm, g" in differing
    assert differing != matched


def test_every_reported_string_is_ascii() -> None:
    """These land in a Fusion tooltip, which is why the micron is ``um``."""
    comparison = logic.compare(
        logic.UnitsState(DistanceUnits.MicronDistanceUnits, MassUnits.SlugMassUnits),
        MM_G,
    )
    texts = (
        logic.tooltip_text(TABLES, comparison),
        logic.prompt_text(TABLES, comparison, "Part"),
        logic.applied_text(TABLES, comparison),
        logic.already_matching_text(TABLES, comparison),
        logic.log_line(TABLES, comparison),
    )

    for text in texts:
        assert text.isascii(), text


def test_the_log_line_distinguishes_the_two_outcomes() -> None:
    assert "units match" in logic.log_line(TABLES, logic.compare(MM_G, MM_G))
    assert "length and mass" in logic.log_line(TABLES, logic.compare(IN_OZ, MM_G))
    assert "mass" in logic.log_line(TABLES, logic.compare(MM_KG, MM_G))
