"""Unit tests for the Manufacture-side Match Units logic.

The Manufacture workspace's unit system is neither read nor written through the
Fusion API — the CAM product has no settable units manager — so both directions
go through text commands. That makes ``UnitSystems.List`` output a parsing
contract with Fusion's own diagnostic text rather than with a documented
interface, and :data:`CAPTURED_LIST` below is the verbatim output observed on
Fusion on ADSKMVG91G2F5W, 2026-09-12, with Manufacture active and set to inches.
Keeping it verbatim is the point: if a future build reformats that output, these
tests are what notices.

``mfg.py`` imports no ``adsk`` module. The enum classes it resolves families
against are stood in for by the plain class below, because the test harness
fabricates ``adsk`` as a MagicMock whose attributes answer with mocks rather
than integers.
"""

import importlib
from pathlib import Path

PT_PKG = Path(__file__).resolve().parent.parent.name
logic = importlib.import_module(f"{PT_PKG}.commands.matchunits.logic")
mfg = importlib.import_module(f"{PT_PKG}.commands.matchunits.mfg")


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


FAMILIES = mfg.build_families(DistanceUnits)

# The distance-unit label table logic.py builds, needed for the wording tests.
DISTANCE_LABELS = logic.build_tables(
    DistanceUnits, type("MassUnits", (), {"GramMassUnits": 0}), type("Sys", (), {})
).distance

MM = DistanceUnits.MillimeterDistanceUnits
CM = DistanceUnits.CentimeterDistanceUnits
INCH = DistanceUnits.InchDistanceUnits
FOOT = DistanceUnits.FootDistanceUnits

# Verbatim `UnitSystems.List` output. Do not tidy this; it is a fixture of
# Fusion's real formatting, parenthesised debug dump and all.
CAPTURED_LIST = """UnitSystem name: mm modeling length with MKS (m, kg, second, celsius) units id: MmMKS initialized: 1 (base ManagedGroupEntity (base ManagedEntity (base Entity type UnitSystemMetaType id: 36 ) : HasParent: 1) children : 18)
UnitSystem name: inch modeling length with imperial (foot, lbmass, second, fahrenheit) units id: InchImperial initialized: 1 (base ManagedGroupEntity (base ManagedEntity (base Entity type UnitSystemMetaType id: 55 ) : HasParent: 1) children : 15)

The active unit system is inch modeling length with imperial (foot, lbmass, second, fahrenheit) units
    UnitSystemChoiceById Id : ModelingLength (base UnitSystemChoice units: inch name: Modeling Length (base ManagedEntity (base Entity type UnitSystemChoiceByIdMetaType id: 56 ) : HasParent: 1))
    UnitSystemChoiceByUnit : (base UnitSystemChoice units: foot name: Length (base ManagedEntity (base Entity type UnitSystemChoiceByUnitMetaType id: 57 ) : HasParent: 1))
    UnitSystemChoiceByUnit : (base UnitSystemChoice units: lbmass name: Mass (base ManagedEntity (base Entity type UnitSystemChoiceByUnitMetaType id: 58 ) : HasParent: 1))
"""


# -- Families ------------------------------------------------------------------


def test_every_distance_unit_has_a_family() -> None:
    """A unit added to logic.DISTANCE_UNITS without a family never prompts.

    That failure is silent in Fusion, so it is caught here instead.
    """
    named = {name for name, _short, _long in logic.DISTANCE_UNITS}

    assert named == set(mfg.DISTANCE_FAMILY), (
        f"missing a family: {named - set(mfg.DISTANCE_FAMILY)}; "
        f"unknown name: {set(mfg.DISTANCE_FAMILY) - named}"
    )


def test_families_resolve_against_the_live_enum() -> None:
    assert FAMILIES[MM] == mfg.METRIC
    assert FAMILIES[CM] == mfg.METRIC
    assert FAMILIES[INCH] == mfg.IMPERIAL
    assert FAMILIES[FOOT] == mfg.IMPERIAL
    assert len(FAMILIES) == len(mfg.DISTANCE_FAMILY)


def test_a_unit_this_build_does_not_name_is_skipped() -> None:
    """A dropped enum member is absent from the map, not guessed at."""
    trimmed = type(
        "Trimmed",
        (),
        {
            name: value
            for name, value in vars(DistanceUnits).items()
            if not name.startswith("_") and name != "YardDistanceUnits"
        },
    )

    families = mfg.build_families(trimmed)

    assert DistanceUnits.YardDistanceUnits not in families
    assert families[INCH] == mfg.IMPERIAL


def test_every_family_has_a_manufacture_system() -> None:
    for family in set(mfg.DISTANCE_FAMILY.values()):
        assert mfg.system_for_family(family) is not None


# -- Parsing UnitSystems.List --------------------------------------------------


def test_the_captured_output_parses() -> None:
    report = mfg.parse_unit_systems(CAPTURED_LIST)

    assert report.ids == ("MmMKS", "InchImperial")
    assert report.active_id == "InchImperial"
    assert report.active_length_unit == "inch"


def test_the_system_name_survives_its_own_punctuation() -> None:
    """A name contains commas, parentheses and the word "units"."""
    report = mfg.parse_unit_systems(CAPTURED_LIST)
    names = dict((name, sid) for name, sid in report.systems)

    assert (
        names["mm modeling length with MKS (m, kg, second, celsius) units"] == "MmMKS"
    )
    assert (
        names[
            "inch modeling length with imperial "
            "(foot, lbmass, second, fahrenheit) units"
        ]
        == "InchImperial"
    )


def test_the_active_system_is_resolved_by_name_not_position() -> None:
    """Fusion names the active system; the id has to be looked back up.

    Here the active one is the *first* declared, so a parser that assumed the
    last-seen system was active would pass the captured fixture and fail this.
    """
    swapped = CAPTURED_LIST.replace(
        "The active unit system is inch modeling length with imperial "
        "(foot, lbmass, second, fahrenheit) units",
        "The active unit system is mm modeling length with MKS "
        "(m, kg, second, celsius) units",
    )

    assert mfg.parse_unit_systems(swapped).active_id == "MmMKS"


def test_an_unknown_active_name_yields_no_id_but_keeps_the_name() -> None:
    """A name matching no declared system must not resolve to a guess."""
    text = CAPTURED_LIST.replace(
        "The active unit system is inch modeling", "The active unit system is odd"
    )

    report = mfg.parse_unit_systems(text)

    assert report.active_id is None
    assert report.active_name is not None
    assert report.ids == ("MmMKS", "InchImperial")


def test_a_third_system_is_reported_not_dropped() -> None:
    """More systems on a future build must show up, so the log can say so."""
    text = CAPTURED_LIST.replace(
        "\nThe active unit system is",
        "\nUnitSystem name: cm modeling length units id: CmMKS initialized: 1 (base x)"
        "\n\nThe active unit system is",
    )

    assert mfg.parse_unit_systems(text).ids == ("MmMKS", "InchImperial", "CmMKS")


def test_unparseable_input_is_empty_never_a_guess() -> None:
    for text in ("", None, "   ", "garbage", 42, "UnitSystem name: no id here"):
        report = mfg.parse_unit_systems(text)

        assert report.active_id is None
        assert report.systems == () or report.ids == ()


def test_a_missing_active_line_yields_no_active_id() -> None:
    text = "\n".join(
        line
        for line in CAPTURED_LIST.splitlines()
        if not line.startswith("The active unit system is")
    )

    report = mfg.parse_unit_systems(text)

    assert report.ids == ("MmMKS", "InchImperial")
    assert report.active_id is None
    assert report.active_name is None


# -- The measured cross-check --------------------------------------------------


def test_scale_identifies_each_system() -> None:
    assert mfg.system_for_scale(0.1) == "MmMKS"
    assert mfg.system_for_scale(2.54) == "InchImperial"


def test_scale_tolerates_float_representation() -> None:
    """0.1 and 2.54 are not exactly representable; this is never an == test."""
    assert mfg.system_for_scale(0.1 + 1e-12) == "MmMKS"
    assert mfg.system_for_scale(2.54 - 1e-12) == "InchImperial"


def test_the_error_sentinel_is_not_a_scale() -> None:
    """evaluateExpression returns -1 on error without raising.

    Treating that as a measurement would compare as "differs" against every
    real system and prompt a rewrite off a failed read.
    """
    assert mfg.system_for_scale(-1) is None
    assert mfg.system_for_scale(-1.0) is None
    assert mfg.system_for_scale(0) is None
    assert mfg.system_for_scale(None) is None


def test_an_unmatched_scale_is_unrecognized() -> None:
    assert mfg.system_for_scale(1.0) is None  # centimetres: no MFG system
    assert mfg.system_for_scale(100.0) is None  # metres


# -- Comparing -----------------------------------------------------------------


def test_matching_families_match() -> None:
    comparison = mfg.compare(FAMILIES, MM, "MmMKS")

    assert comparison.matches


def test_differing_families_do_not() -> None:
    comparison = mfg.compare(FAMILIES, MM, "InchImperial")

    assert not comparison.matches
    assert comparison.target_id == "MmMKS"


def test_a_metric_design_is_satisfied_by_millimetres() -> None:
    """The re-prompt trap: a cm design wants MmMKS and must then be satisfied.

    Comparing the design *unit* against the Manufacture *system* would leave
    a centimetre design permanently mismatched, prompting on every single
    workspace switch forever.
    """
    assert mfg.compare(FAMILIES, CM, "MmMKS").matches
    assert mfg.compare(FAMILIES, DistanceUnits.MeterDistanceUnits, "MmMKS").matches
    assert mfg.compare(FAMILIES, DistanceUnits.MicronDistanceUnits, "MmMKS").matches


def test_an_imperial_design_is_satisfied_by_inches() -> None:
    assert mfg.compare(FAMILIES, FOOT, "InchImperial").matches
    assert mfg.compare(FAMILIES, DistanceUnits.MilDistanceUnits, "InchImperial").matches


def test_every_design_unit_reaches_a_satisfied_state() -> None:
    """No design unit may be permanently unsatisfiable."""
    for value in FAMILIES:
        target = mfg.system_for_family(FAMILIES[value])

        assert mfg.compare(FAMILIES, value, target).matches


def test_an_unreadable_active_system_cannot_be_compared() -> None:
    assert mfg.compare(FAMILIES, MM, None) is None
    assert mfg.compare(FAMILIES, MM, "") is None


def test_an_unrecognized_active_system_cannot_be_compared() -> None:
    """A system this module cannot classify has no family, so it says nothing."""
    assert mfg.compare(FAMILIES, MM, "Bogus") is None


def test_a_custom_active_system_cannot_be_compared() -> None:
    """Custom is an arbitrary pair of units, so it has no family.

    Fusion declares it on the Design product, and classifying it either way
    would be a guess in front of a document rewrite.
    """
    assert "Custom" not in mfg.SYSTEM_FAMILY
    assert mfg.compare(FAMILIES, MM, "Custom") is None


def test_a_design_unit_with_no_family_cannot_be_compared() -> None:
    assert mfg.compare(FAMILIES, 999, "MmMKS") is None
    assert mfg.compare(FAMILIES, None, "MmMKS") is None


# -- Wording -------------------------------------------------------------------


def test_the_prompt_names_the_document_and_both_sides() -> None:
    comparison = mfg.compare(FAMILIES, MM, "InchImperial")

    text = mfg.prompt_text(DISTANCE_LABELS, comparison, "Bracket v12")

    assert "Bracket v12" in text
    assert "millimeters" in text
    assert "inches" in text
    assert text.rstrip().endswith("?")


def test_the_prompt_names_the_target_not_the_design_unit() -> None:
    """A cm design is told Manufacture becomes millimetres, not centimetres."""
    comparison = mfg.compare(FAMILIES, CM, "InchImperial")

    text = mfg.prompt_text(DISTANCE_LABELS, comparison, "Part")

    assert "centimeters" in text  # what the design is in
    assert "millimeters" in text  # what Manufacture will become


def test_every_reported_string_is_ascii() -> None:
    """These reach a Fusion dialog."""
    comparison = mfg.compare(FAMILIES, CM, "InchImperial")
    texts = (
        mfg.prompt_text(DISTANCE_LABELS, comparison, "Part"),
        mfg.applied_text(comparison),
        mfg.already_matching_text(comparison),
        mfg.log_line(DISTANCE_LABELS, comparison),
    )

    for text in texts:
        assert text.isascii(), text


def test_an_unrecognized_system_label_is_an_admission() -> None:
    assert mfg.short_system_label("Bogus") == logic.UNKNOWN_SHORT
    assert mfg.long_system_label("Custom") == logic.UNKNOWN_LONG


def test_a_non_target_system_still_has_a_readable_label() -> None:
    """A prompt has to be able to name what Manufacture is currently on, even
    when that system is not one it can be switched to."""
    assert mfg.short_system_label("Imperial") == "ft"
    assert mfg.long_system_label("CmMKS") == "centimeters"


def test_the_log_line_distinguishes_the_two_outcomes() -> None:
    matched = mfg.log_line(DISTANCE_LABELS, mfg.compare(FAMILIES, MM, "MmMKS"))
    differing = mfg.log_line(DISTANCE_LABELS, mfg.compare(FAMILIES, MM, "InchImperial"))

    assert "match" in matched
    assert "differ" in differing
    assert "InchImperial" in differing and "MmMKS" in differing


# -- The wider system classification -------------------------------------------


def test_every_design_product_system_is_classified_or_deliberately_not() -> None:
    """The six systems UnitSystems.List declares on the Design product.

    Five classify; Custom deliberately does not.
    """
    declared = ("CmMKS", "MmMKS", "MMKS", "InchImperial", "Imperial", "Custom")

    classified = {name: mfg.family_of_system(name) for name in declared}

    assert classified == {
        "CmMKS": mfg.METRIC,
        "MmMKS": mfg.METRIC,
        "MMKS": mfg.METRIC,
        "InchImperial": mfg.IMPERIAL,
        "Imperial": mfg.IMPERIAL,
        "Custom": None,
    }


def test_every_activatable_target_is_also_classified() -> None:
    """MFG_SYSTEMS is a subset of what SYSTEM_FAMILY can classify."""
    for _family, system_id, _short, _long in mfg.MFG_SYSTEMS:
        assert mfg.family_of_system(system_id) is not None


def test_a_foot_based_manufacture_system_is_a_real_mismatch() -> None:
    """Imperial is not an activatable target but must still be seen as imperial.

    Reading it as "unrecognized" would silently miss a genuine mismatch
    against a millimetre design.
    """
    comparison = mfg.compare(FAMILIES, MM, "Imperial")

    assert comparison is not None
    assert not comparison.matches
    assert comparison.target_id == "MmMKS"


def test_the_verdict_is_by_family_not_by_id() -> None:
    """A metric Manufacture system satisfies a metric design.

    Comparing ids would leave Manufacture-on-CmMKS against a mm design
    permanently mismatched and prompting on every switch.
    """
    comparison = mfg.compare(FAMILIES, MM, "CmMKS")

    assert comparison.active_id != comparison.target_id
    assert comparison.matches


def test_activating_the_target_always_reaches_a_match() -> None:
    """Whatever Manufacture starts on, activating the target must settle it."""
    for start in ("MmMKS", "InchImperial", "CmMKS", "MMKS", "Imperial"):
        for design_unit in FAMILIES:
            first = mfg.compare(FAMILIES, design_unit, start)
            if first.matches:
                continue
            settled = mfg.compare(FAMILIES, design_unit, first.target_id)

            assert settled.matches, (design_unit, start, first.target_id)


# -- The Design product's own list ---------------------------------------------

# Verbatim `UnitSystems.List` with the DESIGN product active, same document and
# session as CAPTURED_LIST. Note the naming difference: "Celsius" here against
# "celsius" under the CAM product, for the same MmMKS id.
CAPTURED_DESIGN_LIST = """UnitSystem name: cm modeling length with MKS (m, kg, second, Celsius) units id: CmMKS initialized: 1 (base x children : 19)
UnitSystem name: mm modeling length with MKS (m, kg, second, Celsius) units id: MmMKS initialized: 1 (base x children : 19)
UnitSystem name: standard MKS (m, kg, second, Celsius) units id: MMKS initialized: 1 (base x children : 19)
UnitSystem name: inch modeling length with imperial (foot, lbmass, second, Fahrenheit) units id: InchImperial initialized: 1 (base x children : 16)
UnitSystem name: Imperial (foot, lbmass, second, Fahrenheit) units id: Imperial initialized: 1 (base x children : 16)
UnitSystem name: Custom units id: Custom initialized: 1 (base x children : 19)

The active unit system is inch modeling length with imperial (foot, lbmass, second, Fahrenheit) units
    UnitSystemChoiceById Id : ModelingLength (base UnitSystemChoice units: inch name: Modeling Length (base x))
    UnitSystemChoiceById Id : ModelingMass (base UnitSystemChoice units: ouncemass name: Modeling Mass (base x))
    UnitSystemChoiceByUnit : (base UnitSystemChoice units: foot name: Length (base x))
"""


def test_the_design_products_six_systems_parse() -> None:
    report = mfg.parse_unit_systems(CAPTURED_DESIGN_LIST)

    assert report.ids == (
        "CmMKS",
        "MmMKS",
        "MMKS",
        "InchImperial",
        "Imperial",
        "Custom",
    )
    assert report.active_id == "InchImperial"


def test_a_modeling_mass_choice_does_not_displace_modeling_length() -> None:
    """The Design product reports both choices; only the length one counts."""
    report = mfg.parse_unit_systems(CAPTURED_DESIGN_LIST)

    assert report.active_length_unit == "inch"


def test_a_system_named_without_parentheses_still_parses() -> None:
    """ "Custom units" has no parenthesised unit list."""
    report = mfg.parse_unit_systems(CAPTURED_DESIGN_LIST)

    assert ("Custom units", "Custom") in report.systems
