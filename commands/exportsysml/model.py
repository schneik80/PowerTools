# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.
"""Plain-data model of a Fusion assembly, for the Export SysML command.

Nothing here imports ``adsk``: ``entry.py`` flattens the live Fusion topology
into the frozen records below, and every decision about quantities,
classification and traversal order is made here so it can be unit tested
outside Fusion (see ``tests/test_exportsysml_model.py``).

Component identity is an opaque string built by ``entry.py`` from
``Component.id`` — never ``entityToken``, whose own API docstring warns that the
token for one entity "can be different over time" and must never be compared,
and never the display name, which Fusion does not guarantee to be unique. This
module only ever compares the strings it is handed.

Every physical quantity is optional and is ``None`` when Fusion could not
evaluate it. Callers must omit a ``None`` rather than substituting zero: a
plausible wrong mass is worse than an absent one.

Units in this module are Fusion's internal ones — centimetres, kilograms,
cubic centimetres, square centimetres. Conversion to the units the output
advertises happens in ``render.py``.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

# How a component is described in the Physical View. "hybrid" is the case the
# BOM export silently drops: a component carrying its own solid bodies *and*
# child occurrences, which is neither a pure part nor a pure subassembly.
# "empty" is a real and common Fusion state -- a component created but not yet
# modelled -- and calling it a part would be a plausible wrong answer.
PART = "part"
SUBASSEMBLY = "subassembly"
HYBRID = "hybrid"
EMPTY = "empty"

# Hard ceiling on recursion depth. A Fusion assembly cannot legally contain
# itself, but a corrupt or mid-update document can present one, and the ancestor
# check alone would not stop a pathologically deep tree from exhausting the
# stack while the user waits.
MAX_DEPTH = 64

# Degrees of freedom each Fusion joint kind permits, as
# ``(rotational, translational)``. These are properties of the kind rather than
# of one joint, so they are written into the connection definitions instead of
# being read per joint.
#
# "Inferred" and "Unknown" are deliberately absent: their motion is not fixed by
# the kind, and a plausible wrong degree-of-freedom count is worse than an
# absent one -- the same reasoning that omits an unevaluated mass.
JOINT_DOF = {
    "Rigid": (0, 0),
    "Revolute": (1, 0),
    "Slider": (0, 1),
    "Cylindrical": (1, 1),
    "PinSlot": (1, 1),
    "Planar": (1, 2),
    "Ball": (3, 0),
}

# Which vector on a ``JointMotion`` describes the joint's primary axis, and what
# that axis means, per joint kind: ``{kind: (property name, role)}``.
#
# The property differs by kind -- a revolute joint has ``rotationAxisVector``, a
# slider ``slideDirectionVector`` -- so the mapping is data here rather than a
# chain of ``isinstance`` checks in ``entry.py``, which keeps it testable and
# leaves the Fusion side a single ``getattr``.
#
# Rigid is absent because it permits no motion, and Inferred because its motion
# is not fixed by the kind. Neither gets an axis rather than getting a wrong one.
# A pin-slot and a planar joint have a second axis as well; only the primary one
# is exported, and the role says which it is.
JOINT_AXIS = {
    "Revolute": ("rotationAxisVector", "rotation"),
    "Slider": ("slideDirectionVector", "translation"),
    "Cylindrical": ("rotationAxisVector", "rotation"),
    "PinSlot": ("rotationAxisVector", "rotation"),
    "Planar": ("normalDirectionVector", "normal"),
    "Ball": ("pitchDirectionVector", "pitch"),
}


def joint_axis_property(joint_type: str) -> tuple[str, str] | None:
    """``(property name, role)`` for *joint_type*'s axis, or ``None``."""
    return JOINT_AXIS.get(joint_type)


def unit_vector(vector) -> tuple[float, float, float] | None:
    """*vector* scaled to unit length, or ``None`` when it has no direction.

    Fusion's axis vectors are expected to be unit already, but normalising is
    cheap and makes the exported direction independent of that assumption. A
    zero-length vector has no direction to report, and reporting ``(0, 0, 0)``
    as an axis would be a plausible wrong answer.
    """
    if vector is None:
        return None
    try:
        x, y, z = (float(component) for component in vector)
    except (TypeError, ValueError):
        return None
    length = (x * x + y * y + z * z) ** 0.5
    if length <= 0.0:
        return None
    return (x / length, y / length, z / length)


@dataclass(frozen=True)
class ChildRef:
    """One parent-to-child edge, with the child's multiplicity under *that* parent.

    ``count`` is per-parent, not global: a fastener used twice in one bracket and
    three times in another is two edges of 2 and 3, and its total of five is
    derived by :func:`total_counts`.
    """

    key: str
    count: int


@dataclass(frozen=True)
class CompNode:
    """A unique component: its identity, its metadata and its own physical facts.

    The physical values describe the component *once*, not once per instance —
    they are read a single time per unique component, which is why a repeated
    subassembly costs one physical-properties evaluation rather than one per
    occurrence.
    """

    key: str
    name: str
    part_number: str = ""
    description: str = ""
    material: str = ""
    is_referenced: bool = False
    body_count: int = 0
    children: tuple[ChildRef, ...] = ()
    mass_kg: float | None = None
    volume_cm3: float | None = None
    area_cm2: float | None = None
    center_of_mass_cm: tuple[float, float, float] | None = None
    bbox_min_cm: tuple[float, float, float] | None = None
    bbox_max_cm: tuple[float, float, float] | None = None


@dataclass(frozen=True)
class JointEdge:
    """A joint or as-built joint, as a connection between two components.

    ``one_key`` / ``two_key`` are ``None`` when the joint anchors to geometry
    that belongs to no occurrence — a joint made against root-level geometry has
    no occurrence on that side, and Fusion returns nothing there rather than
    raising. Such a joint is still reported, with the missing side labelled, but
    cannot be emitted as a connection between two parts.
    """

    name: str
    joint_type: str
    owner_key: str | None = None
    one_key: str | None = None
    two_key: str | None = None
    one_label: str = ""
    two_label: str = ""
    is_as_built: bool = False
    is_suppressed: bool = False
    # Where the joint is and which way it acts, in the coordinate space of the
    # component that owns it -- Fusion reads joints natively, and a native object
    # carries no assembly context to place it in. That is what makes the value
    # correct for every instance of a repeated component, and what stops two
    # origins under different owners being comparable.
    # ``origin_cm`` in centimetres, ``axis`` a unit vector, ``axis_role`` naming
    # what the axis governs ("rotation", "translation", "normal", "pitch").
    # All three are ``None``/empty when Fusion did not supply them -- a rigid
    # joint has no axis, and a joint whose geometry could not be read has no
    # origin. An axis of (0, 0, 0) is never emitted.
    origin_cm: tuple[float, float, float] | None = None
    axis: tuple[float, float, float] | None = None
    axis_role: str = ""

    @property
    def is_connectable(self) -> bool:
        """True when both ends resolved, so this can become a SysML connection."""
        return bool(self.one_key) and bool(self.two_key)


@dataclass(frozen=True)
class ExternalRef:
    """A linked document the design depends on, aggregated over its instances."""

    label: str
    version: int | None = None
    is_out_of_date: bool | None = None
    instance_count: int = 1


@dataclass(frozen=True)
class DocMeta:
    """Provenance of the export.

    ``exported_at`` is supplied by the caller rather than read from the clock
    here, so a rendered document is reproducible under test.
    """

    document_name: str
    design_type: str = ""
    length_units: str = ""
    exported_at: str = ""
    version: int | None = None


@dataclass(frozen=True)
class AssemblyModel:
    """The whole export: metadata, the component graph, joints and references."""

    meta: DocMeta
    root_key: str
    nodes: dict[str, CompNode] = field(default_factory=dict)
    joints: tuple[JointEdge, ...] = ()
    external_refs: tuple[ExternalRef, ...] = ()
    # Anything the collection pass could not read, in the order it happened.
    # Surfaced in an appendix of the document: an export that quietly swallowed
    # a failed read would leave the reader unable to tell an absent value from
    # an unread one.
    notes: tuple[str, ...] = ()

    def node(self, key: str) -> CompNode | None:
        """The node for *key*, or ``None`` when the walk never recorded it."""
        return self.nodes.get(key)

    @property
    def root(self) -> CompNode | None:
        """The root component's node, or ``None`` on an empty model."""
        return self.nodes.get(self.root_key)


@dataclass(frozen=True)
class Row:
    """One line of the rendered assembly hierarchy.

    ``truncated`` marks a node whose children were deliberately not expanded —
    either it recurses into one of its own ancestors or it sits at the depth cap.
    The renderers surface that rather than presenting a silently short tree.
    """

    depth: int
    node: CompNode
    count: int
    truncated: bool = False


def classify(node: CompNode) -> str:
    """Describe *node* as a part, a subassembly, or a hybrid of both.

    A component with bodies *and* children is a hybrid: its own geometry is real
    and so is its decomposition, and reporting it as either alone loses one of
    them. ``exportbomcsv`` drops these rows entirely, which is the behaviour this
    classification exists to avoid repeating.
    """
    has_children = bool(node.children)
    has_bodies = node.body_count > 0
    if has_children and has_bodies:
        return HYBRID
    if has_children:
        return SUBASSEMBLY
    if has_bodies:
        return PART
    return EMPTY


def walk(model: AssemblyModel, max_depth: int = MAX_DEPTH) -> list:
    """Depth-first rows for the assembly hierarchy, deepest nesting expanded once.

    A component reachable by two different paths appears under each parent, which
    is what a hierarchy is for. A component reachable from *itself* is expanded
    only until the cycle closes, and one that sits at *max_depth* is not expanded
    at all; both are flagged ``truncated`` so the caller can say so out loud.

    Arguments:
    model -- The assembly to walk.
    max_depth -- Deepest level expanded; the root is level 0.

    Returns:
    A list of :class:`Row`, in display order.
    """
    rows: list = []
    root = model.root
    if root is None:
        return rows

    def visit(node: CompNode, depth: int, count: int, ancestors: frozenset) -> None:
        recurses = node.key in ancestors
        at_cap = depth >= max_depth
        blocked = bool(node.children) and (recurses or at_cap)
        rows.append(Row(depth=depth, node=node, count=count, truncated=blocked))
        if blocked:
            return
        deeper = ancestors | {node.key}
        for ref in node.children:
            child = model.node(ref.key)
            if child is None:
                continue
            visit(child, depth + 1, ref.count, deeper)

    visit(root, 0, 1, frozenset())
    return rows


def total_counts(model: AssemblyModel, max_depth: int = MAX_DEPTH) -> dict:
    """Total instances of every component across the whole assembly.

    Multiplicities multiply down the tree, so a bracket used twice that itself
    holds four screws contributes eight screws. The root counts as one. A cyclic
    edge is counted once and then not followed, so the total stays finite.
    """
    counts: dict = {}
    root = model.root
    if root is None:
        return counts

    def visit(node: CompNode, multiplier: int, depth: int, ancestors: frozenset):
        counts[node.key] = counts.get(node.key, 0) + multiplier
        if node.key in ancestors or depth >= max_depth:
            return
        deeper = ancestors | {node.key}
        for ref in node.children:
            child = model.node(ref.key)
            if child is None:
                continue
            visit(child, multiplier * ref.count, depth + 1, deeper)

    visit(root, 1, 0, frozenset())
    return counts


def definition_order(model: AssemblyModel, max_depth: int = MAX_DEPTH) -> list:
    """Component keys ordered children-first, then any node the walk never reached.

    SysML v2 does not require a definition to precede its use, but a stable order
    keeps the emitted file diffable between exports, and children-first reads the
    way a parts list does. Unreachable nodes are appended by name so nothing
    collected is silently dropped from the model.
    """
    ordered: list = []
    seen: set = set()

    def visit(key: str, depth: int, ancestors: frozenset) -> None:
        node = model.node(key)
        if node is None or key in seen:
            return
        if key not in ancestors and depth < max_depth:
            deeper = ancestors | {key}
            for ref in node.children:
                visit(ref.key, depth + 1, deeper)
        if key not in seen:
            seen.add(key)
            ordered.append(key)

    if model.root is not None:
        visit(model.root_key, 0, frozenset())
    for key in sorted(model.nodes, key=lambda k: (model.nodes[k].name, k)):
        if key not in seen:
            seen.add(key)
            ordered.append(key)
    return ordered


def joint_dof(joint_type: str) -> tuple[int, int] | None:
    """``(rotational, translational)`` DOF for *joint_type*, or ``None``.

    ``None`` means the kind does not fix the motion -- Fusion's inferred joints,
    and any kind a future Fusion release adds that this module has not been
    taught. Callers must omit the attributes rather than write zeros, which
    would claim the joint is rigid.
    """
    return JOINT_DOF.get(joint_type or "")


def usage_path(
    model: AssemblyModel,
    owner_key: str | None,
    target_key: str | None,
    max_depth: int = MAX_DEPTH,
) -> tuple[str, ...] | None:
    """Child keys leading from *owner_key* down to *target_key*, or ``None``.

    The returned tuple excludes the owner and ends with the target, so it is the
    chain of usages a SysML connection end has to name -- one entry for a direct
    child, more for a component nested deeper.

    A SysML connection end may name a nested part by a dotted path, so two ends
    in different subassemblies are still expressible from their common ancestor.
    That is why this searches for a *descendant* rather than a direct child, and
    it is what lets a joint between a shaft in one subassembly and a bearing in
    another become a connection instead of a comment.

    Breadth-first, so the shortest path wins and ties break on the order the
    children were declared, which keeps the emitted path stable between exports.
    A component reachable from itself is enqueued once, and the walk stops at
    *max_depth*, so a cyclic or pathologically deep document still terminates.
    """
    if not owner_key or not target_key:
        return None
    queue: deque = deque([(owner_key, ())])
    seen: set = {owner_key}
    while queue:
        key, path = queue.popleft()
        if len(path) >= max_depth:
            continue
        node = model.node(key)
        if node is None:
            continue
        for ref in node.children:
            if ref.key == target_key:
                return path + (ref.key,)
            if ref.key in seen:
                continue
            seen.add(ref.key)
            queue.append((ref.key, path + (ref.key,)))
    return None


def unplaced_reason(model: AssemblyModel, joint: JointEdge) -> str:
    """Why *joint* cannot be emitted as a connection, or ``""`` when it can.

    A SysML connection joins two *usages* nameable from one scope, and a
    connection end may reach a nested usage by a dotted path. So both ends only
    have to be *descendants* of the joint's owner, not children of it -- an
    earlier version of this function required direct children and dropped every
    joint that crossed a subassembly boundary, which in a real hub assembly was
    a third of the joints that had two resolved ends.

    Fusion also lets a joint anchor to geometry owned by no occurrence, and lets
    a joint be suppressed. Suppression is a deliberate exclusion rather than a
    failure: a suppressed joint is not part of the built configuration, so
    emitting ``connect`` for it would assert a physical interface the design says
    is not there.
    """
    if joint.is_suppressed:
        return "suppressed in the design, so not part of the built configuration"
    if not joint.is_connectable:
        return "an end is anchored to geometry owned by no occurrence"
    if not joint.owner_key:
        return "the owning component could not be identified"
    owner = model.node(joint.owner_key)
    if owner is None:
        return "the owning component is not part of the exported structure"
    one = usage_path(model, joint.owner_key, joint.one_key)
    two = usage_path(model, joint.owner_key, joint.two_key)
    if one is None or two is None:
        return "an end is not reachable from the component that owns the joint"
    return ""


def placed_joints(model: AssemblyModel) -> dict:
    """Emittable joints, grouped under the component whose definition holds them."""
    grouped: dict = {}
    for joint in model.joints:
        if not unplaced_reason(model, joint):
            grouped.setdefault(joint.owner_key, []).append(joint)
    return {key: tuple(value) for key, value in grouped.items()}


def unplaced_joints(model: AssemblyModel) -> tuple:
    """``(joint, reason)`` for every joint that cannot become a connection.

    Kept as a first-class result rather than dropped: a joint the export could
    not express is exactly the sort of omission a reader needs told about.
    """
    pairs = []
    for joint in model.joints:
        reason = unplaced_reason(model, joint)
        if reason:
            pairs.append((joint, reason))
    return tuple(pairs)


def extents_cm(node: CompNode) -> tuple[float, float, float] | None:
    """Bounding-box side lengths in centimetres, or ``None`` without a box.

    Returned largest-first so the three numbers read as length, width, height
    regardless of how the component happens to be oriented in its own space.
    """
    if node.bbox_min_cm is None or node.bbox_max_cm is None:
        return None
    try:
        sides = [
            abs(node.bbox_max_cm[axis] - node.bbox_min_cm[axis]) for axis in range(3)
        ]
    except (IndexError, TypeError):
        return None
    sides.sort(reverse=True)
    return (sides[0], sides[1], sides[2])
