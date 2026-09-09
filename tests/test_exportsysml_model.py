"""Unit tests for the Export SysML assembly model.

These pin the decisions that would otherwise produce a plausible wrong number in
a document a systems engineer reads as authoritative:

* ``test_hybrid_component_is_classified_as_hybrid`` -- a component with bodies
  AND children is the case ``exportbomcsv`` silently drops from its output.
* ``test_empty_component_is_not_called_a_part`` -- a component with neither
  bodies nor children is a real Fusion state, and calling it a part is a lie.
* ``test_instance_totals_multiply_down_the_tree`` -- quantities are derived by
  multiplying edge multiplicities, not by counting occurrences.
* ``test_self_referencing_component_terminates`` -- the cycle guard.

The module imports no ``adsk``, but it does use package-relative imports from
its siblings, so it is loaded by its full package path with the ``conftest.py``
scaffolding in place.
"""

import importlib
from pathlib import Path

import pytest

PT_PKG = Path(__file__).resolve().parent.parent.name
model = importlib.import_module(f"{PT_PKG}.commands.exportsysml.model")


# ---------------------------------------------------------------------------
# Builders


def node(key, name=None, children=(), bodies=0, **kwargs):
    """A CompNode with the noise defaulted away.

    ``children`` takes ``(key, count)`` pairs so a test reads as the assembly
    shape it is describing rather than as a pile of constructors.
    """
    return model.CompNode(
        key=key,
        name=name or key,
        body_count=bodies,
        children=tuple(model.ChildRef(key=k, count=c) for k, c in children),
        **kwargs,
    )


def assembly(*nodes, root=None, joints=(), refs=(), notes=()):
    """An AssemblyModel over *nodes*, rooted at the first unless told otherwise."""
    mapping = {n.key: n for n in nodes}
    return model.AssemblyModel(
        meta=model.DocMeta(document_name="Test"),
        root_key=root or nodes[0].key,
        nodes=mapping,
        joints=tuple(joints),
        external_refs=tuple(refs),
        notes=tuple(notes),
    )


def joint(name="J1", one="a", two="b", owner="root", **kwargs):
    """A JointEdge between two sibling components; *kwargs* override any field."""
    fields = {
        "name": name,
        "joint_type": "Revolute",
        "owner_key": owner,
        "one_key": one,
        "two_key": two,
        "one_label": one or "",
        "two_label": two or "",
    }
    fields.update(kwargs)
    return model.JointEdge(**fields)


# ---------------------------------------------------------------------------
# classify


@pytest.mark.parametrize(
    ("bodies", "children", "expected"),
    [
        (2, (), model.PART),
        (0, (("child", 1),), model.SUBASSEMBLY),
        (3, (("child", 1),), model.HYBRID),
        (0, (), model.EMPTY),
    ],
)
def test_classification_covers_every_combination(bodies, children, expected):
    """Every (bodies, children) combination has its own label."""
    assert model.classify(node("n", bodies=bodies, children=children)) == expected


def test_hybrid_component_is_classified_as_hybrid():
    """A component with its own geometry AND children is neither of the two.

    ``exportbomcsv`` keeps only rows whose child count is below one, so a hybrid
    component's bodies never reach its CSV. The Physical View must name it.
    """
    hybrid = node("bearing", bodies=1, children=(("shaft", 2),))
    assert model.classify(hybrid) == model.HYBRID


def test_empty_component_is_not_called_a_part():
    """An empty component reports as empty, not as a part with no bodies."""
    assert model.classify(node("placeholder")) == model.EMPTY


# ---------------------------------------------------------------------------
# total_counts


def test_root_counts_as_one_instance():
    """The root exists exactly once, however many children it has."""
    counts = model.total_counts(assembly(node("root", children=(("a", 4),)), node("a")))
    assert counts["root"] == 1


def test_instance_totals_multiply_down_the_tree():
    """A bracket used twice, each holding four screws, yields eight screws."""
    parts = assembly(
        node("root", children=(("bracket", 2),)),
        node("bracket", children=(("screw", 4),)),
        node("screw", bodies=1),
    )

    counts = model.total_counts(parts)

    assert counts["bracket"] == 2
    assert counts["screw"] == 8


def test_shared_subassembly_totals_sum_across_parents():
    """A component reached from two parents totals the sum of both paths."""
    parts = assembly(
        node("root", children=(("left", 1), ("right", 1))),
        node("left", children=(("pin", 2),)),
        node("right", children=(("pin", 3),)),
        node("pin", bodies=1),
    )

    assert model.total_counts(parts)["pin"] == 5


def test_missing_child_node_is_skipped_not_fatal():
    """An edge to a component the walk never recorded does not raise."""
    counts = model.total_counts(assembly(node("root", children=(("ghost", 2),))))
    assert counts == {"root": 1}


# ---------------------------------------------------------------------------
# Cycle and depth guards


def test_self_referencing_component_terminates():
    """A component that contains itself is counted once, then not followed.

    Fusion cannot legally build this, but a corrupt or mid-update document can
    present it, and an export that hangs is worse than one that stops early.
    """
    parts = assembly(
        node("root", children=(("loop", 1),)),
        node("loop", children=(("loop", 1),)),
    )

    counts = model.total_counts(parts)
    rows = model.walk(parts)

    assert counts["loop"] == 2  # once as root's child, once as its own
    assert any(row.truncated for row in rows)


def test_mutual_recursion_terminates():
    """Two components that contain each other do not recurse forever."""
    parts = assembly(
        node("root", children=(("a", 1),)),
        node("a", children=(("b", 1),)),
        node("b", children=(("a", 1),)),
    )

    assert model.walk(parts)  # the assertion is that this returns at all
    assert model.total_counts(parts)["a"] >= 1


def test_depth_cap_stops_expansion_and_is_flagged():
    """A chain deeper than the cap stops, and says it stopped."""
    chain = [node("root", children=(("c0", 1),))]
    for index in range(10):
        child = (f"c{index + 1}", 1)
        chain.append(node(f"c{index}", children=(child,)))
    chain.append(node("c10"))

    rows = model.walk(assembly(*chain), max_depth=3)

    assert max(row.depth for row in rows) == 3
    assert any(row.truncated for row in rows)


def test_walk_on_empty_model_returns_no_rows():
    """A model whose root was never recorded yields nothing rather than raising."""
    empty = model.AssemblyModel(
        meta=model.DocMeta(document_name="Test"), root_key="missing"
    )
    assert model.walk(empty) == []
    assert model.total_counts(empty) == {}


# ---------------------------------------------------------------------------
# walk shape


def test_walk_reports_per_parent_multiplicity_not_totals():
    """A row's count is the multiplicity under its own parent."""
    parts = assembly(
        node("root", children=(("bracket", 2),)),
        node("bracket", children=(("screw", 4),)),
        node("screw", bodies=1),
    )

    rows = {row.node.key: row for row in model.walk(parts)}

    assert rows["bracket"].count == 2
    assert rows["screw"].count == 4  # four per bracket, not eight in total


def test_shared_component_appears_under_each_parent():
    """A hierarchy shows a shared component once per place it is used."""
    parts = assembly(
        node("root", children=(("left", 1), ("right", 1))),
        node("left", children=(("pin", 1),)),
        node("right", children=(("pin", 1),)),
        node("pin", bodies=1),
    )

    keys = [row.node.key for row in model.walk(parts)]

    assert keys.count("pin") == 2


# ---------------------------------------------------------------------------
# definition_order


def test_definition_order_puts_children_before_parents():
    """Definitions are emitted children-first, so the file reads bottom-up."""
    parts = assembly(
        node("root", children=(("bracket", 1),)),
        node("bracket", children=(("screw", 1),)),
        node("screw", bodies=1),
    )

    order = model.definition_order(parts)

    assert order.index("screw") < order.index("bracket") < order.index("root")


def test_definition_order_emits_each_component_once():
    """A component used twice is defined once."""
    parts = assembly(
        node("root", children=(("left", 1), ("right", 1))),
        node("left", children=(("pin", 1),)),
        node("right", children=(("pin", 1),)),
        node("pin", bodies=1),
    )

    order = model.definition_order(parts)

    assert order.count("pin") == 1
    assert sorted(order) == sorted(parts.nodes)


def test_definition_order_includes_unreachable_nodes():
    """A recorded component the walk never reached is still defined.

    Dropping it would mean the model file silently omits something the scan
    collected, which is the class of omission this export must not make.
    """
    parts = assembly(node("root"), node("orphan", bodies=1))
    assert "orphan" in model.definition_order(parts)


def test_two_components_sharing_a_name_stay_distinct():
    """Identity is the key, never the display name."""
    parts = assembly(
        node("root", children=(("k1", 1), ("k2", 1))),
        node("k1", name="Bracket", bodies=1),
        node("k2", name="Bracket", bodies=1),
    )

    assert len(model.definition_order(parts)) == 3
    assert model.total_counts(parts)["k1"] == 1
    assert model.total_counts(parts)["k2"] == 1


# ---------------------------------------------------------------------------
# Joint placement


def test_joint_between_two_siblings_is_placeable():
    """The ordinary case: both ends are children of the joint's owner."""
    parts = assembly(
        node("root", children=(("a", 1), ("b", 1))),
        node("a", bodies=1),
        node("b", bodies=1),
        joints=(joint(),),
    )

    assert model.unplaced_reason(parts, parts.joints[0]) == ""
    assert model.placed_joints(parts)["root"] == parts.joints[0:1]
    assert model.unplaced_joints(parts) == ()


@pytest.mark.parametrize("missing", ["one_key", "two_key"])
def test_joint_with_an_unresolved_end_is_not_placed(missing):
    """A joint anchored to root geometry has no occurrence on that side.

    Fusion returns nothing there rather than raising, so an unguarded emitter
    would write ``connect a to ;`` and break the model file.
    """
    parts = assembly(
        node("root", children=(("a", 1), ("b", 1))),
        node("a", bodies=1),
        node("b", bodies=1),
        joints=(joint(**{missing: None}),),
    )

    reason = model.unplaced_reason(parts, parts.joints[0])

    assert "no occurrence" in reason
    assert model.placed_joints(parts) == {}
    assert model.unplaced_joints(parts)[0][1] == reason


def test_suppressed_joint_is_reported_but_never_connected():
    """A suppressed joint is not part of the built configuration.

    Emitting ``connect`` for it would assert a physical interface the design
    says is not there.
    """
    parts = assembly(
        node("root", children=(("a", 1), ("b", 1))),
        node("a", bodies=1),
        node("b", bodies=1),
        joints=(joint(is_suppressed=True),),
    )

    assert "suppressed" in model.unplaced_reason(parts, parts.joints[0])
    assert model.placed_joints(parts) == {}
    assert len(model.unplaced_joints(parts)) == 1


def test_joint_across_subassemblies_is_placed_by_a_dotted_path():
    """Two ends in different subassemblies share an ancestor, so they connect.

    This used to be rejected for sharing "no common parent". A SysML connection
    end may name a nested usage by a dotted path, so a common *ancestor* is
    enough -- and requiring a common parent dropped a third of the joints that
    had two resolved ends in a real hub assembly.
    """
    parts = assembly(
        node("root", children=(("left", 1), ("right", 1))),
        node("left", children=(("a", 1),)),
        node("right", children=(("b", 1),)),
        node("a", bodies=1),
        node("b", bodies=1),
        joints=(joint(one="a", two="b", owner="root"),),
    )

    assert model.unplaced_reason(parts, parts.joints[0]) == ""
    assert model.usage_path(parts, "root", "a") == ("left", "a")
    assert model.usage_path(parts, "root", "b") == ("right", "b")


def test_joint_whose_end_is_not_below_its_owner_is_not_placed():
    """An end outside the owner's subtree cannot be named from the owner."""
    parts = assembly(
        node("root", children=(("left", 1), ("b", 1))),
        node("left", children=(("a", 1),)),
        node("a", bodies=1),
        node("b", bodies=1),
        joints=(joint(one="a", two="b", owner="left"),),
    )

    reason = model.unplaced_reason(parts, parts.joints[0])

    assert "not reachable from the component that owns the joint" in reason
    assert model.placed_joints(parts) == {}


# ---------------------------------------------------------------------------
# usage_path


def test_usage_path_finds_a_direct_child():
    parts = assembly(node("root", children=(("a", 1),)), node("a", bodies=1))
    assert model.usage_path(parts, "root", "a") == ("a",)


def test_usage_path_returns_none_for_an_unreachable_target():
    parts = assembly(
        node("root", children=(("a", 1),)), node("a", bodies=1), node("far", bodies=1)
    )
    assert model.usage_path(parts, "root", "far") is None


def test_usage_path_returns_none_for_the_owner_itself():
    """The owner is not one of its own usages, so there is no path to it."""
    parts = assembly(node("root", children=(("a", 1),)), node("a", bodies=1))
    assert model.usage_path(parts, "root", "root") is None


@pytest.mark.parametrize("absent", ["owner", "target"])
def test_usage_path_tolerates_a_missing_key(absent):
    parts = assembly(node("root", children=(("a", 1),)), node("a", bodies=1))
    owner = None if absent == "owner" else "root"
    target = None if absent == "target" else "a"
    assert model.usage_path(parts, owner, target) is None


def test_usage_path_prefers_the_shortest_route():
    """A component reachable directly and through a subassembly takes the direct one."""
    parts = assembly(
        node("root", children=(("deep", 1), ("a", 1))),
        node("deep", children=(("a", 1),)),
        node("a", bodies=1),
    )
    assert model.usage_path(parts, "root", "a") == ("a",)


def test_usage_path_terminates_on_a_cycle():
    """A document presenting a component inside itself must not hang the export."""
    parts = assembly(
        node("root", children=(("a", 1),)),
        node("a", children=(("root", 1),), bodies=1),
    )
    assert model.usage_path(parts, "root", "a") == ("a",)
    assert model.usage_path(parts, "root", "missing") is None


def test_usage_path_stops_at_the_depth_cap():
    """Beyond the cap the path is not reported, matching what walk() expands."""
    nodes = [node(f"n{i}", children=((f"n{i + 1}", 1),)) for i in range(4)]
    nodes.append(node("n4", bodies=1))
    parts = assembly(*nodes, root="n0")

    assert model.usage_path(parts, "n0", "n4", max_depth=4) == ("n1", "n2", "n3", "n4")
    assert model.usage_path(parts, "n0", "n4", max_depth=2) is None


# ---------------------------------------------------------------------------
# joint_dof


@pytest.mark.parametrize(
    ("joint_type", "expected"),
    [
        ("Rigid", (0, 0)),
        ("Revolute", (1, 0)),
        ("Slider", (0, 1)),
        ("Cylindrical", (1, 1)),
        ("PinSlot", (1, 1)),
        ("Planar", (1, 2)),
        ("Ball", (3, 0)),
    ],
)
def test_joint_dof_covers_every_fusion_joint_kind(joint_type, expected):
    assert model.joint_dof(joint_type) == expected


@pytest.mark.parametrize("joint_type", ["Inferred", "Unknown", "", None])
def test_joint_dof_is_none_when_the_kind_does_not_fix_the_motion(joint_type):
    """An inferred joint's motion is not its kind, and a wrong DOF beats no DOF."""
    assert model.joint_dof(joint_type) is None


def test_joint_whose_owner_was_not_recorded_is_not_placed():
    """A joint owned by a component outside the export degrades gracefully."""
    parts = assembly(
        node("root", children=(("a", 1),)),
        node("a", bodies=1),
        joints=(joint(owner="elsewhere"),),
    )

    assert "not part of the exported structure" in model.unplaced_reason(
        parts, parts.joints[0]
    )


# ---------------------------------------------------------------------------
# extents_cm


def test_extents_are_returned_largest_first():
    """The three sides read as length, width, height whatever the orientation."""
    sized = node(
        "n",
        bodies=1,
        bbox_min_cm=(0.0, 0.0, 0.0),
        bbox_max_cm=(2.0, 12.0, 8.0),
    )

    assert model.extents_cm(sized) == (12.0, 8.0, 2.0)


def test_extents_handle_a_box_that_straddles_the_origin():
    """Sides are absolute differences, not coordinate maxima."""
    sized = node(
        "n", bodies=1, bbox_min_cm=(-5.0, -1.0, -2.0), bbox_max_cm=(5.0, 1.0, 2.0)
    )

    assert model.extents_cm(sized) == (10.0, 4.0, 2.0)


@pytest.mark.parametrize(
    ("minimum", "maximum"),
    [(None, (1.0, 1.0, 1.0)), ((0.0, 0.0, 0.0), None), (None, None)],
)
def test_extents_are_none_without_both_corners(minimum, maximum):
    """A half-read bounding box yields nothing rather than a wrong size."""
    sized = node("n", bodies=1, bbox_min_cm=minimum, bbox_max_cm=maximum)
    assert model.extents_cm(sized) is None


def test_extents_survive_a_malformed_corner():
    """A corner that is not a 3-tuple is refused, not indexed into."""
    sized = node("n", bodies=1, bbox_min_cm=(0.0,), bbox_max_cm=(1.0, 2.0, 3.0))
    assert model.extents_cm(sized) is None


# ---------------------------------------------------------------------------
# Optional physical data


def test_absent_physical_data_stays_absent():
    """``None`` survives the model unchanged; nothing substitutes a zero."""
    plain = node("n", bodies=1)

    assert plain.mass_kg is None
    assert plain.volume_cm3 is None
    assert plain.area_cm2 is None
    assert plain.center_of_mass_cm is None


# ---------------------------------------------------------------------------
# Joint placement: origin and axis
#
# The axis property differs by joint kind, so the mapping lives here as data
# rather than as a chain of isinstance checks in entry.py. A kind whose motion
# its name does not fix gets no axis rather than a wrong one.


@pytest.mark.parametrize(
    ("kind", "prop", "role"),
    [
        ("Revolute", "rotationAxisVector", "rotation"),
        ("Slider", "slideDirectionVector", "translation"),
        ("Cylindrical", "rotationAxisVector", "rotation"),
        ("PinSlot", "rotationAxisVector", "rotation"),
        ("Planar", "normalDirectionVector", "normal"),
        ("Ball", "pitchDirectionVector", "pitch"),
    ],
)
def test_each_moving_joint_kind_names_its_axis_property(kind, prop, role):
    """The property name is what ``entry.py`` reads off the JointMotion."""
    assert model.joint_axis_property(kind) == (prop, role)


@pytest.mark.parametrize("kind", ["Rigid", "Inferred", "Unknown", ""])
def test_a_kind_with_no_fixed_axis_gets_none(kind):
    """A rigid joint has no axis; an inferred one has none the kind fixes."""
    assert model.joint_axis_property(kind) is None


def test_every_kind_with_an_axis_also_has_a_degree_of_freedom():
    """A joint that moves about an axis must report that it moves."""
    for kind in model.JOINT_AXIS:
        rotational, translational = model.JOINT_DOF[kind]
        assert rotational + translational > 0, kind


@pytest.mark.parametrize(
    ("vector", "expected"),
    [
        ((0.0, 0.0, 1.0), (0.0, 0.0, 1.0)),
        ((0.0, 0.0, 5.0), (0.0, 0.0, 1.0)),
        ((3.0, 4.0, 0.0), (0.6, 0.8, 0.0)),
        ((-2.0, 0.0, 0.0), (-1.0, 0.0, 0.0)),
    ],
)
def test_axis_vectors_are_normalised(vector, expected):
    """The exported direction does not depend on Fusion handing back unit length."""
    result = model.unit_vector(vector)

    assert result == pytest.approx(expected)


@pytest.mark.parametrize("vector", [None, (0.0, 0.0, 0.0), (), "nope", (1.0, 2.0)])
def test_a_vector_with_no_direction_is_none(vector):
    """A zero-length or unreadable vector has no axis to report.

    Returning ``(0, 0, 0)`` would be a plausible wrong answer -- indistinguishable
    from a real direction to anything reading the model.
    """
    assert model.unit_vector(vector) is None


def test_joint_placement_defaults_to_absent():
    """A joint records no placement until Fusion supplies one."""
    edge = joint()

    assert edge.origin_cm is None
    assert edge.axis is None
    assert edge.axis_role == ""
