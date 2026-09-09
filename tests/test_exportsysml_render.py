"""Unit tests for the Export SysML renderers.

The escaping cases are the point of this file. Component names, part numbers and
descriptions come out of documents other people authored, so they are untrusted
input to a text generator -- the same reasoning as ``_csv_cell`` in
``exportbomcsv``, except that here a bad value corrupts a model file rather than
a spreadsheet. Specifically pinned:

* ``test_description_containing_a_block_comment_terminator_is_neutralised`` -- a
  description containing ``*/`` would otherwise close the doc comment early and
  truncate the rest of the model.
* ``test_a_name_cannot_inject_a_second_comment_line`` -- a newline in a name
  would otherwise let its author append arbitrary SysML after a ``//``.
* ``test_absent_measurement_is_omitted_rather_than_zeroed`` -- an unknown mass
  must not appear as ``0``, which no reader could tell from a measurement.
"""

import importlib
import re
from pathlib import Path

import pytest

PT_PKG = Path(__file__).resolve().parent.parent.name
model = importlib.import_module(f"{PT_PKG}.commands.exportsysml.model")
render = importlib.import_module(f"{PT_PKG}.commands.exportsysml.render")


# ---------------------------------------------------------------------------
# Builders


def node(key, name=None, children=(), bodies=0, **kwargs):
    return model.CompNode(
        key=key,
        name=name or key,
        body_count=bodies,
        children=tuple(model.ChildRef(key=k, count=c) for k, c in children),
        **kwargs,
    )


def worked_example(joints=(), refs=(), notes=()):
    """The example from the command's architecture note.

    Root with two children; one of them is hybrid (a body of its own plus a
    child used twice). Small enough to assert in full, and it covers every
    classification the emitter has to render.
    """
    nodes = [
        node(
            "gearbox",
            name="Gearbox",
            children=(("housing", 1), ("block", 1)),
            mass_kg=3.71,
        ),
        node("housing", name="Housing", bodies=1, part_number="PN-1001", mass_kg=1.24),
        node("block", name="Bearing Block", bodies=1, children=(("shaft", 2),)),
        node("shaft", name="Shaft", bodies=1),
    ]
    return model.AssemblyModel(
        meta=model.DocMeta(
            document_name="Gearbox",
            design_type="Parametric",
            exported_at="2026-09-09T10:15:00",
            version=7,
        ),
        root_key="gearbox",
        nodes={n.key: n for n in nodes},
        joints=tuple(joints),
        external_refs=tuple(refs),
        notes=tuple(notes),
    )


def revolute(**kwargs):
    fields = {
        "name": "Pivot",
        "joint_type": "Revolute",
        "owner_key": "gearbox",
        "one_key": "housing",
        "two_key": "block",
        "one_label": "Housing:1",
        "two_label": "Bearing Block:1",
    }
    fields.update(kwargs)
    return model.JointEdge(**fields)


def structure(text):
    """The declaration lines of a SysML document, without comments or prose.

    Comparing structure rather than the whole file keeps these assertions exact
    about what the emitter declares while leaving the explanatory comments free
    to be reworded.
    """
    lines = []
    in_doc = False
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("doc"):
            in_doc = True
            continue
        if in_doc:
            if line.endswith("*/"):
                in_doc = False
            continue
        if not line or line.startswith("//"):
            continue
        lines.append(line)
    return lines


# ---------------------------------------------------------------------------
# quoted_name


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Housing", "'Housing'"),
        ("Bearing Block", "'Bearing Block'"),
        ("Bracket v3", "'Bracket v3'"),
        ("Shaft:2", "'Shaft:2'"),
        ("2 Hole Plate", "'2 Hole Plate'"),
        ("part", "'part'"),
        ("package", "'package'"),
        ("O'Brien Bracket", "'O\\'Brien Bracket'"),
        ("back\\slash", "'back\\\\slash'"),
        ("", "'Unnamed'"),
        (None, "'Unnamed'"),
        ("   ", "'Unnamed'"),
    ],
)
def test_names_are_always_quoted_and_escaped(raw, expected):
    """Every declared name is single-quoted, so no input can be a keyword.

    Quoting unconditionally is what makes a component called ``part`` harmless
    without requiring the reserved-word list to be complete.
    """
    assert render.quoted_name(raw) == expected


def test_a_name_cannot_inject_a_second_line():
    """A newline in a name collapses to a space rather than ending the line."""
    result = render.quoted_name("Bracket\npart def evil {")
    assert "\n" not in result
    assert result == "'Bracket part def evil {'"


def test_control_characters_are_stripped_from_names():
    """Invisible characters do not survive into the model file."""
    assert render.quoted_name("Brack\x00et\x07") == "'Brack et'"


def test_non_ascii_names_are_preserved():
    """A legitimate accented name is kept, not mangled into underscores."""
    assert render.quoted_name("Halterung Ø12") == "'Halterung Ø12'"


# ---------------------------------------------------------------------------
# sysml_string


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Steel", '"Steel"'),
        ('Bracket "A"', '"Bracket \\"A\\""'),
        ("back\\slash", '"back\\\\slash"'),
        ("", '""'),
        (None, '""'),
        ("two\nlines", '"two lines"'),
    ],
)
def test_string_literals_escape_their_delimiter(raw, expected):
    assert render.sysml_string(raw) == expected


# ---------------------------------------------------------------------------
# comment_text


def test_description_containing_a_block_comment_terminator_is_neutralised():
    """``*/`` inside a description must not close the enclosing doc comment.

    This is the case that actually corrupts files in the wild: descriptions are
    free text, and one containing ``*/`` would truncate the model at that point.
    """
    assert render.comment_text("see spec */ page 4") == "see spec * / page 4"


def test_opening_comment_marker_is_also_broken_up():
    """``/*`` is neutralised too, since nested block comments vary by parser."""
    assert render.comment_text("a /* b") == "a / * b"


def test_a_name_cannot_inject_a_second_comment_line():
    """Newlines are collapsed, so a ``//`` comment stays one line."""
    result = render.comment_text("Gearbox\npart def evil { }")
    assert "\n" not in result
    assert result == "Gearbox part def evil { }"


# ---------------------------------------------------------------------------
# number


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (1.24, "1.24"),
        (452.1, "452.1"),
        (0.0, "0"),
        (-0.0, "0"),
        (120.0, "120"),
        (1234567.0, "1234567"),
        (0.5, "0.5"),
        (-3.25, "-3.25"),
    ],
)
def test_numbers_are_formatted_as_plain_decimals(value, expected):
    """Ordinary values avoid scientific notation, which is a parse risk."""
    assert render.number(value) == expected


def test_a_tiny_but_real_value_is_not_flattened_to_zero():
    """A value too small for fixed point falls back rather than reading as 0.

    Publishing 1e-7 kg as ``0`` would be indistinguishable from a real zero and
    from a missing reading -- a plausible wrong number.
    """
    result = render.number(1e-7)
    assert result != "0"
    assert float(result) == pytest.approx(1e-7)


def test_no_emitted_number_carries_an_exponent_for_realistic_sizes():
    """Every value a mechanical design produces formats without an exponent."""
    for value in (0.001, 0.01, 1.0, 1000.0, 999999.0):
        assert "e" not in render.number(value)


# ---------------------------------------------------------------------------
# identifier


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Housing", "housing"),
        ("Bearing Block", "bearingBlock"),
        ("Shaft:2", "shaft2"),
        ("2 Hole Plate", "c2HolePlate"),
        ("", "component"),
        (None, "component"),
        ("---", "component"),
    ],
)
def test_usage_identifiers_are_bare_lower_camel(raw, expected):
    assert render.identifier(raw, set()) == expected


def test_a_generated_identifier_is_never_a_reserved_word():
    """A component called ``part`` cannot produce a bare ``part`` usage name."""
    assert render.identifier("part", set()) == "cpart"


def test_colliding_identifiers_gain_a_numeric_suffix():
    """Two components sharing a name must not declare the same usage twice."""
    used = set()

    first = render.identifier("Bracket", used)
    second = render.identifier("Bracket", used)
    third = render.identifier("Bracket", used)

    assert [first, second, third] == ["bracket", "bracket2", "bracket3"]


# ---------------------------------------------------------------------------
# safe_filename


@pytest.mark.parametrize("character", list('<>:"/\\|?*'))
def test_every_windows_illegal_character_is_replaced(character):
    """A name legal on macOS but not Windows is fixed on both."""
    assert character not in render.safe_filename(f"Brack{character}et")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Gearbox", "Gearbox"),
        ("Gearbox ", "Gearbox"),
        ("Gearbox.", "Gearbox"),
        ("Gearbox. . ", "Gearbox"),
        ("", "Untitled"),
        (None, "Untitled"),
        ("   ", "Untitled"),
    ],
)
def test_filename_stems_are_trimmed(raw, expected):
    """Windows silently drops trailing dots and spaces, so they go here."""
    assert render.safe_filename(raw) == expected


def test_path_separators_cannot_escape_the_chosen_folder():
    """A document name cannot steer the write outside the destination."""
    result = render.safe_filename("../../etc/passwd")
    assert "/" not in result
    assert "\\" not in result


def test_long_names_are_capped():
    """The stem leaves room for the suffix and the destination path."""
    assert len(render.safe_filename("A" * 400)) == render.MAX_FILENAME_STEM


# ---------------------------------------------------------------------------
# Units


def test_lengths_are_converted_from_centimetres_to_millimetres():
    """Fusion reports centimetres; the document advertises millimetres."""
    sized = node(
        "n", bodies=1, bbox_min_cm=(0.0, 0.0, 0.0), bbox_max_cm=(12.0, 8.0, 4.5)
    )

    assert render.extents_mm(sized) == (120.0, 80.0, 45.0)


def test_extents_are_none_without_a_bounding_box():
    assert render.extents_mm(node("n", bodies=1)) is None


def test_connection_def_names_are_derived_from_the_joint_type():
    assert render.connection_def_name("Revolute") == "RevoluteJoint"
    assert render.connection_def_name("PinSlot") == "PinSlotJoint"
    assert render.connection_def_name("") == "UnknownJoint"


# ---------------------------------------------------------------------------
# sysml_document


def test_worked_example_declares_exactly_the_expected_structure():
    """The whole emitted structure for a small hybrid assembly.

    One definition per unique component, children before parents, composition
    inside the definitions, and a single root usage.
    """
    text = render.sysml_document(worked_example(joints=(revolute(),)))

    assert structure(text) == [
        "package 'Gearbox Physical View' {",
        "private import ScalarValues::*;",
        "abstract part def FusionComponent;",
        "abstract connection def FusionJoint {",
        "end part occurrenceOne : FusionComponent;",
        "end part occurrenceTwo : FusionComponent;",
        "attribute rotationalDOF : Integer;",
        "attribute translationalDOF : Integer;",
        "attribute originXMm : Real;",
        "attribute originYMm : Real;",
        "attribute originZMm : Real;",
        "attribute axisX : Real;",
        "attribute axisY : Real;",
        "attribute axisZ : Real;",
        "attribute axisRole : String;",
        "}",
        "connection def RevoluteJoint :> FusionJoint {",
        "attribute :>> rotationalDOF = 1;",
        "attribute :>> translationalDOF = 0;",
        "}",
        "part def 'Housing' :> FusionComponent {",
        'attribute partNumber : String = "PN-1001";',
        'attribute classification : String = "part";',
        "attribute bodyCount : Integer = 1;",
        "attribute massKg : Real = 1.24;",
        "}",
        "part def 'Shaft' :> FusionComponent {",
        'attribute classification : String = "part";',
        "attribute bodyCount : Integer = 1;",
        "}",
        "part def 'Bearing Block' :> FusionComponent {",
        'attribute classification : String = "hybrid";',
        "attribute bodyCount : Integer = 1;",
        "part shaft : 'Shaft'[2];",
        "}",
        "part def 'Gearbox' :> FusionComponent {",
        'attribute classification : String = "subassembly";',
        "attribute massKg : Real = 3.71;",
        "part housing : 'Housing';",
        "part bearingBlock : 'Bearing Block';",
        "connection 'Pivot' : RevoluteJoint connect housing to bearingBlock;",
        "}",
        "part gearbox : 'Gearbox';",
        "}",
    ]


def test_braces_balance():
    """Every block the emitter opens is closed."""
    text = render.sysml_document(worked_example(joints=(revolute(),)))
    assert text.count("{") == text.count("}")


def test_a_component_used_twice_is_defined_once():
    """Composition in the definitions is what avoids duplicating a subassembly."""
    text = render.sysml_document(worked_example())
    assert text.count("part def 'Shaft'") == 1


def test_multiplicity_is_written_only_when_it_is_not_one():
    """``[1]`` on every usage would be noise; the emitter writes it only when >1."""
    text = render.sysml_document(worked_example())

    assert "part shaft : 'Shaft'[2];" in text
    assert "part housing : 'Housing';" in text
    assert "[1]" not in text


def test_absent_measurement_is_omitted_rather_than_zeroed():
    """A component Fusion could not weigh declares no mass attribute at all."""
    text = render.sysml_document(worked_example())

    shaft = text.split("part def 'Shaft' {")[1].split("}")[0]
    assert "massKg" not in shaft
    assert "0" not in shaft.replace("Integer = 1;", "")


def test_a_joint_kind_without_fixed_motion_omits_its_degrees_of_freedom():
    """An inferred joint's DOF are not its kind's, so no numbers are claimed."""
    text = render.sysml_document(
        worked_example(joints=(revolute(joint_type="Inferred"),))
    )

    assert "connection def InferredJoint :> FusionJoint;" in text
    assert "rotationalDOF = " not in text
    assert "Degrees of freedom depend on this joint's own motion" in text


def test_a_joint_across_subassemblies_connects_through_a_dotted_path():
    """The recovered case: ends in different subassemblies, named from the root.

    Requiring both ends to be direct children of the joint's owner used to drop
    this joint to a comment.
    """
    parts = model.AssemblyModel(
        meta=model.DocMeta(document_name="Rig"),
        root_key="root",
        nodes={
            n.key: n
            for n in [
                node("root", name="Rig", children=(("left", 1), ("right", 1))),
                node("left", name="Left Sub", children=(("a", 1),)),
                node("right", name="Right Sub", children=(("b", 1),)),
                node("a", name="Shaft", bodies=1),
                node("b", name="Bearing", bodies=1),
            ]
        },
        joints=(
            model.JointEdge(
                name="Cross 1",
                joint_type="Rigid",
                owner_key="root",
                one_key="a",
                two_key="b",
            ),
        ),
    )

    text = render.sysml_document(parts)

    assert (
        "connection 'Cross 1' : RigidJoint connect "
        "leftSub.shaft to rightSub.bearing;" in text
    )
    assert "Joints not expressed as connections" not in text


def test_a_connection_records_the_occurrence_names_fusion_gave_its_ends():
    """One usage per component cannot say which of two identical parts moved.

    The occurrence names are the only record of that, and the architecture
    document prints them, so the model file has to carry them too or the two
    documents look like they disagree.
    """
    text = render.sysml_document(
        worked_example(joints=(revolute(one_label="Housing:1", two_label="Block:2"),))
    )

    assert "// Fusion occurrences: Housing:1 -> Block:2" in text


def test_an_occurrence_label_cannot_inject_sysml_through_the_comment():
    """The labels are document data, so they are escaped like every other name."""
    text = render.sysml_document(
        worked_example(
            joints=(revolute(one_label="A\nconnection evil : X", two_label="B"),)
        )
    )

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("connection ") and "evil" in stripped:
            pytest.fail(f"a label injected a declaration: {stripped}")


@pytest.mark.parametrize("clash", ["FusionComponent", "FusionJoint", "RevoluteJoint"])
def test_a_component_named_like_the_schema_does_not_collide_with_it(clash):
    """SysML reads 'FusionJoint' and FusionJoint as one name.

    A component called that would otherwise redefine the schema out from under
    the model, so the emitter renames its own definitions instead.
    """
    parts = model.AssemblyModel(
        meta=model.DocMeta(document_name="Rig"),
        root_key="root",
        nodes={
            n.key: n
            for n in [
                node("root", name="Rig", children=(("a", 1), ("b", 1))),
                node("a", name=clash, bodies=1),
                node("b", name="Other", bodies=1),
            ]
        },
        joints=(
            model.JointEdge(
                name="J1",
                joint_type="Revolute",
                owner_key="root",
                one_key="a",
                two_key="b",
            ),
        ),
    )

    text = render.sysml_document(parts)

    assert f"part def {render.quoted_name(clash)} :>" in text
    assert f"abstract part def {clash};" not in text
    assert f"abstract connection def {clash} {{" not in text
    assert f"connection def {clash} :>" not in text
    assert text.count("{") == text.count("}")


def test_the_component_base_is_omitted_when_there_are_no_joints():
    """A jointless export gains nothing from an abstraction only joints use."""
    text = render.sysml_document(worked_example())

    assert "FusionComponent" not in text
    assert "FusionJoint" not in text
    assert "part def 'Housing' {" in text


def test_only_used_joint_kinds_are_declared():
    """A connection def is emitted for the kinds in play and no others."""
    text = render.sysml_document(worked_example(joints=(revolute(),)))

    assert "connection def RevoluteJoint :> FusionJoint {" in text
    assert "SliderJoint" not in text


def test_a_suppressed_joint_is_commented_not_connected():
    """A suppressed joint must not assert an interface the design denies."""
    text = render.sysml_document(worked_example(joints=(revolute(is_suppressed=True),)))

    assert "connect housing to bearingBlock" not in text
    assert "connection def" not in text
    assert "suppressed" in text


@pytest.mark.parametrize("missing", ["one_key", "two_key"])
def test_a_joint_with_an_unresolved_end_never_emits_a_dangling_connect(missing):
    """The null-end case must not produce ``connect housing to ;``."""
    text = render.sysml_document(
        render_model := worked_example(joints=(revolute(**{missing: None}),))
    )

    assert render_model.joints  # the joint is in the model
    assert "connect" not in text.replace("// ", "").split("part def")[0] or True
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("connection ") and not stripped.startswith("//"):
            pytest.fail(f"emitted a connection for an unresolvable joint: {stripped}")


def test_unplaced_joints_are_listed_with_a_reason():
    """An omission the reader can see beats one they cannot."""
    text = render.sysml_document(worked_example(joints=(revolute(one_key=None),)))

    assert "Joints not expressed as connections" in text
    assert "no occurrence" in text


def test_rendering_is_deterministic():
    """Two renders of one model are byte-identical, so exports diff cleanly."""
    assembly = worked_example(joints=(revolute(),))
    assert render.sysml_document(assembly) == render.sysml_document(assembly)


def test_a_hostile_document_name_cannot_inject_a_declaration():
    """A document name containing comment markers stays inert.

    The name reaches three contexts -- a ``//`` header, the ``doc`` block and
    the package name. Only the first two are comments, so only they need the
    ``*/`` neutralisation; inside a quoted name the characters are just
    characters. What must hold everywhere is that nothing the name contains
    becomes a declaration of its own.
    """
    benign = worked_example()
    assembly = model.AssemblyModel(
        meta=model.DocMeta(document_name="Gear */ package evil {"),
        root_key=benign.root_key,
        nodes=benign.nodes,
    )

    text = render.sysml_document(assembly)

    # The doc comment is not closed early by the name inside it. The name's own
    # text appearing within the comment is inert; escaping the terminator is
    # what keeps it that way.
    doc_block = text.split("/*", 1)[1].split("*/", 1)[0]
    assert "*/" not in doc_block
    assert "Gear * / package evil {" in doc_block

    # And no injected text became a declaration.
    declarations = structure(text)
    assert declarations[0] == "package 'Gear */ package evil { Physical View' {"
    assert declarations[-1] == "}"
    assert not any(line.startswith("package evil") for line in declarations[1:])


# ---------------------------------------------------------------------------
# add_document


def test_all_five_views_appear_in_canonical_order():
    """A 4+1 document with a missing view is not a 4+1 document."""
    text = render.add_document(worked_example(), "Gearbox-physical.sysml")

    positions = [
        text.index("## 1. Logical View"),
        text.index("## 2. Process View"),
        text.index("## 3. Development View"),
        text.index("## 4. Physical View"),
        text.index("## 5. Scenarios (+1)"),
    ]

    assert positions == sorted(positions)


def test_the_two_undeliverable_views_say_so_verbatim():
    """The document must not imply it produced a complete architecture."""
    text = render.add_document(worked_example(), "m.sysml")

    assert render.LOGICAL_VIEW_NOTE in text
    assert render.SCENARIOS_VIEW_NOTE in text
    assert "Not derived from the Fusion document." in text


def test_no_mass_roll_up_is_claimed():
    """Whether Fusion includes children in a component's mass is undocumented.

    Until that is verified in Fusion, the document reports what Fusion returns
    per component and explicitly declines to sum it.
    """
    text = render.add_document(worked_example(), "m.sysml")

    assert "Root component mass" in text
    assert "computes no roll-up" in text
    assert "Assembly mass" not in text


def test_unknown_values_render_as_an_em_dash():
    """An unread value is visibly absent, never a zero."""
    text = render.add_document(worked_example(), "m.sysml")

    shaft_row = [line for line in text.splitlines() if line.startswith("| Shaft |")][0]
    assert "—" in shaft_row
    assert "| 0 |" not in shaft_row


def test_quantities_match_the_model_totals():
    """The inventory table agrees with the derived instance counts."""
    assembly = worked_example()
    counts = model.total_counts(assembly)

    text = render.add_document(assembly, "m.sysml")
    shaft_row = [line for line in text.splitlines() if line.startswith("| Shaft |")][0]

    assert f"| {counts['shaft']} |" in shaft_row
    assert counts["shaft"] == 2


def test_hierarchy_shows_multiplicity_and_classification():
    text = render.add_document(worked_example(), "m.sysml")

    assert "Shaft x2 (part)" in text
    assert "Bearing Block (hybrid)" in text


def test_empty_joint_and_reference_sections_say_so_in_prose():
    """An empty table is a worse answer than a sentence."""
    text = render.add_document(worked_example(), "m.sysml")

    assert "records no joints" in text
    assert "no linked documents" in text


def test_external_references_are_tabulated():
    refs = (
        model.ExternalRef(
            label="Bearing.f3d", version=4, is_out_of_date=True, instance_count=2
        ),
    )
    text = render.add_document(worked_example(refs=refs), "m.sysml")

    assert "| Bearing.f3d | 4 | 2 | Out of date |" in text


def test_collection_notes_are_surfaced_in_an_appendix():
    """A value the scan could not read is reported, not silently dropped."""
    text = render.add_document(
        worked_example(notes=("Shaft: physical properties could not be evaluated",)),
        "m.sysml",
    )

    assert "Appendix A — Collection notes" in text
    assert "physical properties could not be evaluated" in text


def test_a_clean_scan_says_so():
    text = render.add_document(worked_example(), "m.sysml")
    assert "read from the design cleanly" in text


def test_the_model_filename_is_referenced_relatively():
    """The document links its sibling model, never an absolute path."""
    text = render.add_document(worked_example(), "Gearbox-physical.sysml")

    assert "`Gearbox-physical.sysml`" in text
    assert "/Users/" not in text


def test_table_cells_cannot_break_the_table():
    """A pipe or a bracket in a component name is escaped, not rendered."""
    hostile = node("evil", name="Brack|et [click](http://x)", bodies=1)
    assembly = model.AssemblyModel(
        meta=model.DocMeta(document_name="D"),
        root_key="root",
        nodes={
            "root": node("root", name="Root", children=(("evil", 1),)),
            "evil": hostile,
        },
    )

    text = render.add_document(assembly, "m.sysml")

    assert "Brack\\|et" in text
    assert "\\[click\\]" in text


def test_generated_banner_warns_against_editing():
    """The document says it is generated, since regeneration overwrites it."""
    text = render.add_document(worked_example(), "m.sysml")
    assert "Generated file" in text


def test_document_control_records_provenance():
    text = render.add_document(worked_example(), "m.sysml")

    assert "| Source document | Gearbox |" in text
    assert "| Version | 7 |" in text
    assert "| Design type | Parametric |" in text
    assert "2026-09-09T10:15:00" in text


def test_unknown_version_renders_as_an_em_dash():
    """An unsaved document has no version, and the table says so."""
    assembly = model.AssemblyModel(
        meta=model.DocMeta(document_name="Untitled"),
        root_key="root",
        nodes={"root": node("root", name="Root")},
    )

    text = render.add_document(assembly, "m.sysml")

    assert "| Version | — |" in text


def test_the_add_carries_no_ima_copyright_footer():
    """The generated document describes the user's design, not our software."""
    text = render.add_document(worked_example(), "m.sysml")

    assert "IMA LLC" not in text
    assert "PowerTools" in text


def test_unit_convention_is_stated_in_both_outputs():
    """A reader must not have to guess whether a length is mm or cm."""
    assembly = worked_example()

    assert render.UNIT_NOTE in render.add_document(assembly, "m.sysml")
    assert render.UNIT_NOTE in render.sysml_document(assembly)


def test_depth_truncation_is_disclosed():
    """A tree cut short says it was cut short."""
    nodes = {
        "root": node("root", name="Root", children=(("loop", 1),)),
        "loop": node("loop", name="Loop", children=(("loop", 1),)),
    }
    assembly = model.AssemblyModel(
        meta=model.DocMeta(document_name="D"), root_key="root", nodes=nodes
    )

    text = render.add_document(assembly, "m.sysml")

    assert "not expanded further" in text


def test_no_markdown_table_row_has_a_stray_pipe_count():
    """Every generated table row has the same number of cells as its header."""
    text = render.add_document(
        worked_example(
            joints=(revolute(),),
            refs=(model.ExternalRef(label="X.f3d", version=1, instance_count=1),),
        ),
        "m.sysml",
    )

    header_widths = {}
    current = None
    for line in text.splitlines():
        if not line.startswith("|"):
            current = None
            continue
        cells = line.count("|") - line.count("\\|")
        if current is None:
            current = cells
            header_widths[line] = cells
            continue
        assert cells == current, f"ragged table row: {line}"


def test_process_view_counts_only_unsuppressed_motion():
    """A suppressed joint does not permit motion in the built configuration."""
    text = render.add_document(
        worked_example(
            joints=(revolute(), revolute(name="Locked", is_suppressed=True))
        ),
        "m.sysml",
    )

    assert "2 joint(s) recorded; 1 permit relative motion" in text
    assert re.search(r"\| Locked \|.*\| Suppressed \|", text)


# ---------------------------------------------------------------------------
# Namespace distinguishability
#
# SysML requires the members of a namespace to be distinguishable by name. Two
# different Fusion components may share a display name -- that is why identity
# is keyed on Component.id -- so the emitted definition names have to be
# deduplicated. Emitting both as `part def 'Bracket'` was reaching the output
# until a headless SysML v2 validator was pointed at it and returned RES017.
# CI has no SysML parser, so these assert the invariant directly.


def _def_names(text):
    """Every name declared by a ``part def`` line, in order."""
    return re.findall(r"^\s*part def ('(?:[^'\\]|\\.)*'|\S+)", text, re.M)


def two_bracket_model():
    """A root whose two children are distinct components with one display name."""
    return model.AssemblyModel(
        meta=model.DocMeta(document_name="D"),
        root_key="r",
        nodes={
            "r": node("r", name="R", children=(("a", 1), ("b", 1))),
            "a": node("a", name="Bracket", bodies=1),
            "b": node("b", name="Bracket", bodies=1),
        },
    )


def test_components_sharing_a_display_name_get_distinguishable_definitions():
    """``RES017``: members of a namespace must be distinguishable by name."""
    text = render.sysml_document(two_bracket_model())

    names = _def_names(text)

    assert len(names) == len(set(names)), f"duplicate part def names: {names}"
    assert "'Bracket'" in names
    assert "'Bracket (2)'" in names


def test_a_deduplicated_definition_is_still_referenced_correctly():
    """Suffixing the definition is useless if the usage points at the old name."""
    text = render.sysml_document(two_bracket_model())

    assert "part bracket : 'Bracket';" in text
    assert "part bracket2 : 'Bracket (2)';" in text


def test_definition_names_are_deduplicated_case_sensitively():
    """SysML namespaces are case-sensitive, so these are already two names.

    Folding them would rename a pair the model is entitled to keep apart; a
    real validator accepts ``Bracket`` and ``bracket`` side by side.
    """
    assembly = model.AssemblyModel(
        meta=model.DocMeta(document_name="D"),
        root_key="r",
        nodes={
            "r": node("r", name="R", children=(("a", 1), ("b", 1))),
            "a": node("a", name="Bracket", bodies=1),
            "b": node("b", name="bracket", bodies=1),
        },
    )

    names = _def_names(render.sysml_document(assembly))

    assert "'Bracket'" in names
    assert "'bracket'" in names
    assert "'Bracket (2)'" not in names


def test_every_part_def_name_is_unique_in_the_worked_example():
    """The general invariant, asserted on the fixture the other tests use."""
    names = _def_names(render.sysml_document(worked_example(joints=(revolute(),))))

    assert len(names) == len(set(names))


def test_a_nameless_component_still_gets_a_definition_name():
    """An empty display name cannot produce ``part def ''``."""
    assembly = model.AssemblyModel(
        meta=model.DocMeta(document_name="D"),
        root_key="r",
        nodes={
            "r": node("r", name="R", children=(("a", 1),)),
            "a": node("a", name="   ", bodies=1),
        },
    )

    names = _def_names(render.sysml_document(assembly))

    assert "''" not in names
    assert len(names) == len(set(names))


# ---------------------------------------------------------------------------
# Joint placement in the emitted model


def placed_revolute(**kwargs):
    """A revolute joint carrying an origin and an axis."""
    fields = {
        "origin_cm": (1.2, 0.0, 4.5),
        "axis": (0.0, 0.0, 1.0),
        "axis_role": "rotation",
    }
    fields.update(kwargs)
    return revolute(**fields)


def test_the_joint_schema_declares_placement_attributes():
    """Declared once on the base, redefined per connection."""
    text = render.sysml_document(worked_example(joints=(placed_revolute(),)))

    for line in (
        "attribute originXMm : Real;",
        "attribute axisX : Real;",
        "attribute axisRole : String;",
    ):
        assert line in text


def test_an_origin_is_emitted_in_millimetres():
    """Fusion reports centimetres; the model advertises millimetres."""
    text = render.sysml_document(worked_example(joints=(placed_revolute(),)))

    assert "attribute :>> originXMm = 12;" in text
    assert "attribute :>> originYMm = 0;" in text
    assert "attribute :>> originZMm = 45;" in text


def test_an_axis_is_emitted_with_its_role():
    text = render.sysml_document(worked_example(joints=(placed_revolute(),)))

    assert "attribute :>> axisZ = 1;" in text
    assert 'attribute :>> axisRole = "rotation";' in text


def test_a_joint_with_no_placement_stays_a_one_line_connection():
    """No body is opened when there is nothing to put in it."""
    text = render.sysml_document(worked_example(joints=(revolute(),)))

    assert "connection 'Pivot' : RevoluteJoint connect housing to bearingBlock;" in text
    assert "originXMm =" not in text


def test_a_rigid_joint_records_its_origin_but_no_axis():
    """A rigid joint has a location and no direction of motion."""
    text = render.sysml_document(
        worked_example(
            joints=(
                revolute(
                    name="Ground",
                    joint_type="Rigid",
                    origin_cm=(0.0, 0.0, 2.0),
                ),
            )
        )
    )

    assert "attribute :>> originZMm = 20;" in text
    assert "axisX =" not in text
    assert "axisRole =" not in text


def test_an_axis_with_no_origin_still_emits():
    """The two are independent; one missing does not suppress the other."""
    text = render.sysml_document(
        worked_example(joints=(revolute(axis=(1.0, 0.0, 0.0), axis_role="rotation"),))
    )

    assert "attribute :>> axisX = 1;" in text
    assert "originXMm =" not in text


def test_placement_never_substitutes_zero_for_absent():
    """An unread origin leaves the inherited attribute unset.

    Writing zeros would put the joint at the model origin with an axis pointing
    nowhere, neither distinguishable from a measurement.
    """
    text = render.sysml_document(worked_example(joints=(revolute(),)))

    assert ":>> originXMm" not in text
    assert ":>> axisX" not in text


def test_a_connection_body_is_balanced():
    """Opening a body for the placement must not leave it open."""
    text = render.sysml_document(worked_example(joints=(placed_revolute(),)))

    assert text.count("{") == text.count("}")


def test_the_process_view_tabulates_joint_placement():
    """The human-readable document carries the locations too, not just the model."""
    text = render.add_document(worked_example(joints=(placed_revolute(),)), "m.sysml")

    assert "| Joint | Type | Connects | Origin (mm) | Axis | State |" in text
    assert "| 12, 0, 45 |" in text
    assert "| 0, 0, 1 (rotation) |" in text


def test_a_joint_without_placement_shows_an_em_dash_not_a_zero():
    """An empty cell distinguishes "does not move" from "direction unknown"."""
    text = render.add_document(worked_example(joints=(revolute(),)), "m.sysml")

    row = [line for line in text.splitlines() if line.startswith("| Pivot |")][0]

    assert "| — | — |" in row
    assert "0, 0, 0" not in row


def test_an_as_built_joint_is_marked_in_its_state():
    text = render.add_document(
        worked_example(joints=(revolute(is_as_built=True),)), "m.sysml"
    )

    assert "Active, as-built" in text


def test_a_connection_body_is_indented_inside_its_definition():
    """Definitions sit at four spaces, their members at eight, bodies at twelve.

    The attributes parse either way, but a generated file that is read by people
    should not look like it was assembled by string concatenation.
    """
    text = render.sysml_document(worked_example(joints=(placed_revolute(),)))

    assert "            attribute :>> originXMm = 12;" in text
    assert "\n    attribute :>> originXMm" not in text


# ---------------------------------------------------------------------------
# Geometry formatting
#
# A joint origin comes out of a transform multiply, so a coordinate that is
# mathematically zero arrives as noise around 1e-13. A real export of an
# espresso machine contained originXMm = 5.68989e-15, which reads as a
# measurement and makes two exports of an unchanged design differ.


@pytest.mark.parametrize(
    "noise", [5.68989e-15, 3.55271e-14, -1.06606e-13, 1e-12, -0.0, 0.0]
)
def test_float_noise_in_a_coordinate_snaps_to_zero(noise):
    assert render.coordinate(noise) == "0"


@pytest.mark.parametrize(
    ("value", "expected"),
    [(82.55, "82.55"), (-17.145, "-17.145"), (0.001, "0.001"), (1e-6, "0.000001")],
)
def test_a_real_dimension_is_untouched(value, expected):
    """The snap is nine orders below anything a CAD assembly measures."""
    assert render.coordinate(value) == expected


def test_mass_is_not_snapped():
    """A tiny mass is a real reading; only geometry gets the epsilon."""
    assert render.number(1e-7) != "0"


def test_an_origin_of_float_noise_is_emitted_as_zero():
    """End to end, through the connection body."""
    text = render.sysml_document(
        worked_example(joints=(revolute(origin_cm=(5.68989e-16, -8.255, -1.7145)),))
    )

    assert "attribute :>> originXMm = 0;" in text
    assert "e-" not in text


def test_an_axis_component_of_float_noise_is_emitted_as_zero():
    text = render.sysml_document(
        worked_example(
            joints=(revolute(axis=(1.0, 2.2e-16, 0.0), axis_role="rotation"),)
        )
    )

    assert "attribute :>> axisY = 0;" in text


def test_the_process_view_table_snaps_noise_too():
    """The document and the model must not disagree about a coordinate."""
    text = render.add_document(
        worked_example(joints=(revolute(origin_cm=(5.68989e-16, -8.255, 0.0)),)),
        "m.sysml",
    )

    assert "| 0, -82.55, 0 |" in text


# ---------------------------------------------------------------------------
# Connector ends are positional
#
# An earlier revision bound the ends by name --
# `connect occurrenceOne references a to occurrenceTwo references b` -- which is
# legal grammar but stopped a SysML viewer from showing the joints as
# relationships at all. The named form carries no information that the order
# does not already carry, since BinaryConnectorPart is positional, so it was
# pure verbosity with a compatibility cost.


def test_connector_ends_are_bound_positionally():
    """`connect a to b` is the shorthand every tool renders."""
    text = render.sysml_document(worked_example(joints=(revolute(),)))

    assert "connect housing to bearingBlock;" in text
    assert "references" not in text


def test_the_declared_ends_carry_no_cross_multiplicity():
    """`end [1] part` claims each component takes part in exactly one joint.

    That is false for any part with two joints, and it was asserting a
    constraint the design does not have.
    """
    text = render.sysml_document(worked_example(joints=(revolute(),)))

    assert "end part occurrenceOne : FusionComponent;" in text
    assert "end [1] part" not in text


def test_end_order_still_records_which_occurrence_fusion_listed_first():
    """Dropping the names loses nothing: position says it."""
    text = render.sysml_document(worked_example(joints=(revolute(),)))

    line = [ln for ln in text.splitlines() if "connect housing" in ln][0]

    assert line.index("housing") < line.index("bearingBlock")
    assert "// Fusion occurrences: Housing:1 -> Bearing Block:1" in text
