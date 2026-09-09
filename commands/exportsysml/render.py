# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.
"""Renderers for the Export SysML command: a SysML v2 model and an ADD.

Like ``model.py`` this imports no ``adsk``, so both documents can be produced
and asserted outside Fusion (see ``tests/test_exportsysml_render.py``).

Two text formats come from one model:

* ``sysml_document`` writes SysML v2 *textual* notation. Text was the point of
  choosing it over XMI: it diffs, it reviews, and it needs no serialiser.
* ``add_document`` writes the Architecture Design Document that frames the model
  in the 4+1 View Model. It is a generated artefact describing the user's
  design, unrelated to this repository's own ``docs/arch/`` notes, and so it
  carries a PowerTools attribution rather than an IMA copyright footer.

Every name and value reaching either renderer came from a document somebody else
authored, so all of it is escaped, never interpolated raw. That is the same
reasoning as ``_csv_cell`` in ``exportbomcsv``, and there are four contexts with
four different rules, which is why they are four functions:

* ``quoted_name`` -- a declared or referenced SysML name.
* ``sysml_string`` -- a double-quoted attribute value.
* ``comment_text`` -- anything inside ``//`` or ``/* */``. Neutralising ``*/``
  matters most: a component description containing it would close the block
  comment early and truncate the model file.
* ``md_cell`` -- a Markdown table cell.

Unit conversion lives here so it is covered by tests. Fusion hands out
centimetres, kilograms, cubic centimetres and square centimetres; lengths are
published in millimetres because that is the mechanical default, and mass,
volume and area keep Fusion's units with the unit named in the attribute.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from . import model as m

# Attributes are plain ScalarValues types with the unit in the attribute name,
# rather than ISQ quantity types. ScalarValues is part of the kernel library and
# always resolves; ISQ comes from the systems library, and a tool without it on
# the default path fails to parse rather than warning. The trade is that a
# consumer reads the unit from the attribute name, so the doc block says so.
UNIT_NOTE = "Units: length mm, mass kg, volume cm^3, area cm^2."

# Reserved words that must not be emitted as a bare identifier. Declared names
# are always quoted, so this guards only the usage identifiers this module
# generates itself -- which is why an incomplete list cannot break a file.
RESERVED = frozenset(
    {
        "about",
        "abstract",
        "accept",
        "action",
        "alias",
        "all",
        "allocate",
        "allocation",
        "analysis",
        "and",
        "as",
        "assert",
        "assign",
        "assume",
        "attribute",
        "bind",
        "binding",
        "by",
        "calc",
        "case",
        "comment",
        "concern",
        "connect",
        "connection",
        "constraint",
        "decide",
        "def",
        "default",
        "dependency",
        "derived",
        "do",
        "doc",
        "else",
        "end",
        "entry",
        "enum",
        "event",
        "exhibit",
        "exit",
        "expose",
        "false",
        "filter",
        "first",
        "flow",
        "for",
        "fork",
        "frame",
        "from",
        "if",
        "implies",
        "import",
        "in",
        "include",
        "individual",
        "inout",
        "interface",
        "item",
        "join",
        "language",
        "loop",
        "merge",
        "message",
        "metadata",
        "nonunique",
        "not",
        "null",
        "objective",
        "occurrence",
        "of",
        "or",
        "ordered",
        "out",
        "package",
        "parallel",
        "part",
        "perform",
        "port",
        "private",
        "protected",
        "public",
        "readonly",
        "redefines",
        "ref",
        "references",
        "render",
        "rendering",
        "rep",
        "require",
        "requirement",
        "return",
        "satisfy",
        "send",
        "snapshot",
        "specializes",
        "stakeholder",
        "state",
        "subject",
        "subsets",
        "succession",
        "then",
        "timeslice",
        "to",
        "transition",
        "true",
        "until",
        "use",
        "variant",
        "variation",
        "verify",
        "verification",
        "view",
        "viewpoint",
        "while",
        "xor",
    }
)

_BARE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# C0 and C1 control characters. Stripped from every context: they are invisible
# in a diff, and a newline smuggled into a name is how a "//" comment becomes
# two lines, the second of which is whatever the name's author wanted.
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f-\x9f]")

# Characters Windows rejects in a filename, plus both separators. Applied on
# every platform: an export made on macOS is routinely opened on Windows, and a
# name legal on one and not the other is a bug waiting for the handoff.
_ILLEGAL_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

# Filename stems are capped well short of any filesystem limit, because the
# command appends its own suffix and the user's chosen folder is prepended.
MAX_FILENAME_STEM = 120

# Fusion's internal length unit is the centimetre.
_MM_PER_CM = 10.0


def quoted_name(text, fallback: str = "Unnamed") -> str:
    """Render *text* as a single-quoted SysML v2 unrestricted name.

    Always quoted, never conditionally. Fusion component names routinely carry
    spaces, colons, parentheses and version suffixes, and they can equal a SysML
    keyword; quoting unconditionally makes every one of those cases structurally
    harmless and removes the need for a keyword list to be complete.

    ``exportmermaid`` takes the other route and strips offending characters,
    which silently renames the user's parts. Quoting preserves them.
    """
    value = "" if text is None else str(text)
    cleaned = re.sub(r"\s+", " ", _CONTROL_CHARS.sub(" ", value)).strip()
    if not cleaned:
        cleaned = fallback
    escaped = cleaned.replace("\\", "\\\\").replace("'", "\\'")
    return f"'{escaped}'"


def sysml_string(text) -> str:
    """Render *text* as a double-quoted SysML v2 string literal."""
    value = "" if text is None else str(text)
    cleaned = re.sub(r"\s+", " ", _CONTROL_CHARS.sub(" ", value)).strip()
    escaped = cleaned.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def comment_text(text) -> str:
    """Render *text* safely inside a ``//`` or ``/* */`` comment.

    Both comment terminators are broken up, not just the closing one: ``/*``
    inside a block comment nests in some parsers and not others, and the point
    is that no component description can change the file's structure.
    """
    value = "" if text is None else str(text)
    cleaned = _CONTROL_CHARS.sub(" ", value)
    cleaned = cleaned.replace("*/", "* /").replace("/*", "/ *")
    return re.sub(r"\s+", " ", cleaned).strip()


def number(value) -> str:
    """Format a float as a SysML literal without inventing or losing precision.

    Fixed point is preferred, so an ordinary dimension reads as ``120.5`` rather
    than ``1.205e+02``. The one case that falls back to exponent notation is a
    value too small to show at six decimal places: a 0.0000001 kg part must not
    be published as a flat ``0``, which would be indistinguishable from a real
    zero and from a missing reading.
    """
    numeric = float(value)
    if numeric == 0.0:
        return "0"
    fixed = f"{numeric:.6f}".rstrip("0").rstrip(".")
    if fixed in ("", "0", "-0"):
        return f"{numeric:.6g}"
    return fixed


# Below this magnitude a coordinate or an axis component is treated as zero.
# A joint origin comes out of a transform multiply, so a coordinate that is
# mathematically zero arrives as float noise around 1e-13 mm; ``number`` would
# then print ``5.68989e-15`` rather than ``0``, which reads as a measurement and
# makes two exports of an unchanged design diff against each other. A picometre
# is nine orders of magnitude below anything a CAD assembly measures, so nothing
# real is lost.
#
# Mass deliberately does *not* get this treatment: a 1e-7 kg part is a real if
# tiny reading, and flattening it would be the plausible wrong answer.
GEOMETRY_EPSILON = 1e-9


def coordinate(value) -> str:
    """Format a length or an axis component, snapping float noise to zero."""
    numeric = float(value)
    if abs(numeric) < GEOMETRY_EPSILON:
        return "0"
    return number(numeric)


def identifier(text, used: set) -> str:
    """A unique bare lower-camel usage identifier derived from *text*.

    Usage identifiers are generated rather than quoted because ``connect a to b``
    reads better with bare names and because this module controls them entirely.
    Two distinct components may share a display name, and two usages in one
    definition body must not collide, so a repeat gains a numeric suffix.
    ``used`` is mutated, which is what makes repeated calls in one scope stable.
    """
    cleaned = re.sub(r"[^A-Za-z0-9]+", " ", "" if text is None else str(text)).strip()
    if not cleaned:
        cleaned = "component"
    words = cleaned.split()
    candidate = words[0].lower() + "".join(
        word[:1].upper() + word[1:] for word in words[1:]
    )
    if not _BARE_IDENTIFIER.match(candidate) or candidate.lower() in RESERVED:
        candidate = f"c{candidate}"
    base = candidate
    suffix = 2
    while candidate in used:
        candidate = f"{base}{suffix}"
        suffix += 1
    used.add(candidate)
    return candidate


def safe_filename(name) -> str:
    """A filename stem safe on macOS and Windows alike.

    Trailing dots and spaces go as well as illegal characters: Windows silently
    drops them, which would turn ``Bracket .md`` into a file the command reports
    writing under a name that does not exist.
    """
    value = "" if name is None else str(name)
    cleaned = _ILLEGAL_FILENAME.sub("_", value).strip().rstrip(". ")
    cleaned = cleaned[:MAX_FILENAME_STEM].rstrip(". ")
    return cleaned or "Untitled"


def connection_def_name(joint_type: str) -> str:
    """The connection definition name for a joint type, e.g. ``RevoluteJoint``."""
    cleaned = re.sub(r"[^A-Za-z0-9]+", "", joint_type or "") or "Unknown"
    return f"{cleaned}Joint"


# Names for the two definitions this renderer invents. Both are kept clear of
# every component name in the design: SysML treats a single-quoted name as the
# same name as the bare identifier, so a component genuinely called "FusionJoint"
# would otherwise redefine the schema out from under the model.
COMPONENT_DEF_BASE = "FusionComponent"
JOINT_DEF_BASE = "FusionJoint"


@dataclass(frozen=True)
class SchemaNames:
    """The definition names the emitter uses for its own joint schema."""

    component: str
    joint: str
    kinds: dict


def _unclashed(base: str, taken: set) -> str:
    """*base*, suffixed if needed, so it is not already a name in the model."""
    if base not in taken:
        taken.add(base)
        return base
    index = 2
    while f"{base}{index}" in taken:
        index += 1
    taken.add(f"{base}{index}")
    return f"{base}{index}"


def definition_names(assembly) -> dict:
    """``{component key: part def name}``, distinguishable within the package.

    Two different Fusion components can carry the same display name -- that is
    the whole reason identity is keyed on ``Component.id`` rather than the name.
    SysML requires the members of a namespace to be distinguishable, so emitting
    both as ``part def 'Bracket'`` produces a model a parser rejects outright
    (``RES017``), which was reaching the output until a real SysML v2 validator
    was pointed at it. The second and later collisions are suffixed.

    Matching is case-sensitive, because SysML namespaces are: ``Bracket`` and
    ``bracket`` are two names, and folding them would rename a pair the model is
    entitled to keep apart.

    Assigned in one pass up front because every name is needed twice: once to
    declare the definition, and again on each usage that references it.
    """
    names: dict = {}
    taken: set = set()
    for key in m.definition_order(assembly):
        node = assembly.node(key)
        if node is None:
            continue
        base = (node.name or "").strip() or "Component"
        candidate = base
        index = 2
        while candidate in taken:
            candidate = f"{base} ({index})"
            index += 1
        taken.add(candidate)
        names[key] = candidate
    return names


def schema_names(assembly, joint_types, def_names=None) -> SchemaNames:
    """Schema definition names for *assembly*, clear of every component name.

    Allocated together and up front because they have to agree everywhere they
    appear -- the base definition, the specialisations that name it, and the
    ``:>`` on every component definition.

    The names to stay clear of are the ones actually emitted, not the raw
    component names, since a collision is resolved by suffixing and a suffixed
    name could otherwise land on the schema.
    """
    if def_names is None:
        def_names = definition_names(assembly)
    taken = set(def_names.values())
    component = _unclashed(COMPONENT_DEF_BASE, taken)
    joint = _unclashed(JOINT_DEF_BASE, taken)
    kinds = {
        joint_type: _unclashed(connection_def_name(joint_type), taken)
        for joint_type in joint_types
    }
    return SchemaNames(component=component, joint=joint, kinds=kinds)


def usage_names(assembly) -> dict:
    """``{(parent key, child key): usage identifier}`` for every declared usage.

    Assigned in one pass up front because the renderer needs each name twice:
    once to declare the usage inside its definition, and again to spell a dotted
    path through it for a connection end further down the tree. Deriving them
    twice risked the path and the declaration disagreeing whenever two
    same-named children collided and ``identifier`` had to disambiguate.
    """
    names: dict = {}
    for key in m.definition_order(assembly):
        node = assembly.node(key)
        if node is None:
            continue
        used: set = set()
        for ref in node.children:
            child = assembly.node(ref.key)
            if child is None:
                continue
            names[(key, ref.key)] = identifier(child.name, used)
    return names


def dotted_path(names: dict, owner_key: str, path) -> str | None:
    """The dotted usage path for *path* under *owner_key*, or ``None``.

    ``None`` when any hop has no declared usage, which happens when the walk
    recorded an edge to a component it never recorded a node for. Returning it
    rather than a partial path is what stops a malformed ``connect a. to b``.
    """
    parts: list = []
    parent = owner_key
    for child_key in path:
        name = names.get((parent, child_key))
        if name is None:
            return None
        parts.append(name)
        parent = child_key
    return ".".join(parts) or None


def joint_def_lines(names: SchemaNames, joint_types) -> list:
    """The joint schema: an abstract base, then one definition per kind in play.

    The base carries the two ends and the degree-of-freedom attributes; each kind
    redefines the counts. Writing them into the definitions rather than onto
    every connection is what lets a reader tell a revolute from a ball without
    opening Fusion, and costs one line per kind rather than two per joint.

    Ends are typed by a locally declared abstract component definition, so the
    schema needs nothing outside the kernel library -- the same constraint that
    keeps the attributes on plain ScalarValues types.
    """
    lines: list = []
    lines.append("    // Every component definition below specialises this, so a")
    lines.append("    // joint's ends have a type without depending on a library")
    lines.append("    // outside the kernel.")
    lines.append(f"    abstract part def {names.component};")
    lines.append("")
    lines.append("    // Joint kinds used below, as connection definitions.")
    lines.append("    // occurrenceOne is the occurrence Fusion lists first: the one")
    lines.append("    // that moves relative to the second. Degrees of freedom are")
    lines.append("    // fixed by the joint kind, so they live here, not on each")
    lines.append("    // connection; a kind whose motion its name does not fix omits")
    lines.append("    // them rather than claiming zero.")
    lines.append(f"    abstract connection def {names.joint} {{")
    lines.append(f"        end part occurrenceOne : {names.component};")
    lines.append(f"        end part occurrenceTwo : {names.component};")
    lines.append("        attribute rotationalDOF : Integer;")
    lines.append("        attribute translationalDOF : Integer;")
    lines.append("        // Where the joint sits and which way it acts, in the")
    lines.append("        // coordinate space of the component that owns it -- not")
    lines.append("        // the root's. Fusion reads joints natively, and a native")
    lines.append("        // object has no assembly context to place it in, which is")
    lines.append("        // also what makes the value correct for every instance of")
    lines.append("        // a component used more than once. Two origins under")
    lines.append("        // different definitions are therefore not comparable")
    lines.append("        // without composing the occurrence transforms between")
    lines.append("        // them. Declared here and redefined per connection; a")
    lines.append("        // joint whose geometry Fusion did not supply leaves these")
    lines.append("        // unset rather than claiming the origin.")
    lines.append("        attribute originXMm : Real;")
    lines.append("        attribute originYMm : Real;")
    lines.append("        attribute originZMm : Real;")
    lines.append("        attribute axisX : Real;")
    lines.append("        attribute axisY : Real;")
    lines.append("        attribute axisZ : Real;")
    lines.append("        attribute axisRole : String;")
    lines.append("    }")
    for joint_type in joint_types:
        dof = m.joint_dof(joint_type)
        name = names.kinds[joint_type]
        lines.append("")
        if dof is None:
            lines.append(
                "    // Degrees of freedom depend on this joint's own motion, "
                "not its kind."
            )
            lines.append(f"    connection def {name} :> {names.joint};")
            continue
        lines.append(f"    connection def {name} :> {names.joint} {{")
        lines.append(f"        attribute :>> rotationalDOF = {dof[0]};")
        lines.append(f"        attribute :>> translationalDOF = {dof[1]};")
        lines.append("    }")
    return lines


def _placement_lines(joint) -> list:
    """Origin and axis redefinitions for one connection, or an empty list.

    Emitted as a body on the connection only when there is something to say. A
    rigid joint has no axis and a joint whose geometry Fusion could not read has
    no origin; leaving the inherited attributes unset says exactly that, whereas
    writing zeros would put an origin at the model origin and an axis pointing
    nowhere, neither distinguishable from a measurement.
    """
    lines: list = []
    if joint.origin_cm is not None:
        for label, value in zip("XYZ", joint.origin_cm, strict=True):
            lines.append(
                f"attribute :>> origin{label}Mm = {coordinate(value * _MM_PER_CM)};"
            )
    if joint.axis is not None:
        for label, value in zip("XYZ", joint.axis, strict=True):
            lines.append(f"attribute :>> axis{label} = {coordinate(value)};")
        if joint.axis_role:
            lines.append(f"attribute :>> axisRole = {sysml_string(joint.axis_role)};")
    return lines


def extents_mm(node) -> tuple | None:
    """Bounding-box sides in millimetres, largest first, or ``None``."""
    sides = m.extents_cm(node)
    if sides is None:
        return None
    return tuple(side * _MM_PER_CM for side in sides)


def _attribute_lines(node) -> list:
    """Attribute declarations for one component, omitting what Fusion lacked.

    A missing value is left out entirely rather than written as ``0``. Zero is a
    legitimate reading, so publishing it for "unknown" would put a number in the
    model that nobody could distinguish from a measurement.
    """
    lines = []
    if node.part_number:
        lines.append(
            f"attribute partNumber : String = {sysml_string(node.part_number)};"
        )
    if node.description:
        lines.append(
            f"attribute description : String = {sysml_string(node.description)};"
        )
    if node.material:
        lines.append(f"attribute material : String = {sysml_string(node.material)};")
    lines.append(
        f"attribute classification : String = {sysml_string(m.classify(node))};"
    )
    if node.is_referenced:
        lines.append("attribute isExternalReference : Boolean = true;")
    if node.body_count:
        lines.append(f"attribute bodyCount : Integer = {node.body_count};")
    if node.mass_kg is not None:
        lines.append(f"attribute massKg : Real = {number(node.mass_kg)};")
    if node.volume_cm3 is not None:
        lines.append(f"attribute volumeCm3 : Real = {number(node.volume_cm3)};")
    if node.area_cm2 is not None:
        lines.append(f"attribute areaCm2 : Real = {number(node.area_cm2)};")
    extents = extents_mm(node)
    if extents is not None:
        lines.append(f"attribute bboxLengthMm : Real = {number(extents[0])};")
        lines.append(f"attribute bboxWidthMm : Real = {number(extents[1])};")
        lines.append(f"attribute bboxHeightMm : Real = {number(extents[2])};")
    return lines


def sysml_document(assembly) -> str:
    """Render the Physical View of *assembly* as SysML v2 textual notation.

    One ``part def`` per unique component, each carrying its own attributes, its
    child ``part`` usages and the joints it owns; then a single root usage.
    Keeping composition in the definitions is what stops a subassembly used
    three times from being written three times, and what lets a hybrid component
    hold attributes for its own bodies alongside usages for its children.
    """
    meta = assembly.meta
    root = assembly.root
    placed = m.placed_joints(assembly)
    unplaced = m.unplaced_joints(assembly)
    counts = m.total_counts(assembly)
    joint_types = sorted({j.joint_type for group in placed.values() for j in group})
    defs = definition_names(assembly)
    names = schema_names(assembly, joint_types, defs)
    usages = usage_names(assembly)

    out: list = []
    out.append("// Generated by PowerTools -- Export SysML Architecture Document.")
    source = f"Autodesk Fusion document {comment_text(meta.document_name)}"
    if meta.version is not None:
        source += f" v{meta.version}"
    if meta.exported_at:
        source += f", exported {comment_text(meta.exported_at)}"
    out.append(f"// Physical View of {source}.")
    out.append("// Generated file -- edit the Fusion design, not this file.")

    out.append(f"package {quoted_name(f'{meta.document_name} Physical View')} {{")
    out.append("    doc")
    out.append("    /*")
    out.append(
        "     * Physical View (4+1 View Model) of the Autodesk Fusion design "
        f"{comment_text(meta.document_name)}."
    )
    if meta.design_type:
        out.append(f"     * Design type: {comment_text(meta.design_type)}.")
    out.append(f"     * {UNIT_NOTE}")
    out.append("     * One part def per unique component; composition lives in the")
    out.append("     * definitions, so a component used many times appears once.")
    out.append("     * An attribute is omitted where Fusion could not evaluate it:")
    out.append("     * a missing attribute means unknown, not zero.")
    out.append("     * Mass, volume, area and the bounding box include the")
    out.append("     * component's children, so a subassembly's figures cover")
    out.append("     * everything inside it and must not be added together.")
    if joint_types:
        out.append("     * Each Fusion joint becomes a connection carrying the")
        out.append("     * degrees of freedom its kind permits, and where it is.")
        out.append("     * Ends are given in Fusion's order -- occurrenceOne")
        out.append("     * first -- and may name a nested usage by a dotted path,")
        out.append("     * so a joint crossing a subassembly boundary is expressed.")
    out.append("     */")
    out.append("")
    out.append("    private import ScalarValues::*;")

    if joint_types:
        out.append("")
        out.extend(joint_def_lines(names, joint_types))

    for key in m.definition_order(assembly):
        node = assembly.node(key)
        if node is None:
            continue
        out.append("")
        total = counts.get(key)
        if total:
            out.append(f"    // {total} instance(s) in the assembly.")
        specialises = f" :> {names.component}" if joint_types else ""
        out.append(f"    part def {quoted_name(defs[key])}{specialises} {{")
        for line in _attribute_lines(node):
            out.append(f"        {line}")

        if node.children:
            out.append("")
        for ref in node.children:
            child = assembly.node(ref.key)
            if child is None:
                continue
            name = usages.get((key, ref.key))
            if name is None:
                continue
            multiplicity = f"[{ref.count}]" if ref.count != 1 else ""
            out.append(
                f"        part {name} : {quoted_name(defs[ref.key])}{multiplicity};"
            )

        emitted = []
        for joint in placed.get(key, ()):
            one = dotted_path(usages, key, m.usage_path(assembly, key, joint.one_key))
            two = dotted_path(usages, key, m.usage_path(assembly, key, joint.two_key))
            if one and two:
                emitted.append((joint, one, two))
        if emitted:
            out.append("")
            for joint, one, two in emitted:
                # The occurrence names Fusion gave the two ends. A definition
                # holds one usage per component, so a joint on the second of two
                # identical bearings connects the same usage as a joint on the
                # first; without this the two connections would be
                # indistinguishable, and the architecture document -- which does
                # print occurrence names -- would look like it disagreed.
                one_label = comment_text(joint.one_label)
                two_label = comment_text(joint.two_label)
                if one_label and two_label:
                    out.append(
                        f"        // Fusion occurrences: {one_label} -> {two_label}"
                    )
                declaration = (
                    f"        connection {quoted_name(joint.name, 'Joint')} : "
                    f"{names.kinds[joint.joint_type]} "
                    f"connect {one} to {two}"
                )
                placement = _placement_lines(joint)
                if not placement:
                    out.append(f"{declaration};")
                    continue
                out.append(f"{declaration} {{")
                # Definitions sit at four spaces and their members at eight, so
                # a connection's own members belong at twelve.
                out.extend(f"            {line}" for line in placement)
                out.append("        }")
        out.append("    }")

    if root is not None:
        out.append("")
        out.append("    // The design itself.")
        out.append(
            f"    part {identifier(root.name, set())} : {quoted_name(defs[assembly.root_key])};"
        )

    if unplaced:
        out.append("")
        out.append("    // Joints not expressed as connections, and why. Listed so")
        out.append("    // the omission is visible rather than silent; the")
        out.append("    // architecture document tabulates the same joints.")
        for joint, reason in unplaced:
            one = comment_text(joint.one_label) or "(unresolved)"
            two = comment_text(joint.two_label) or "(unresolved)"
            out.append(
                f"    // {comment_text(joint.joint_type)} "
                f"{comment_text(joint.name)}: {one} <-> {two} -- {reason}"
            )

    out.append("}")
    out.append("")
    return "\n".join(out)


# Wording for the views a Fusion design cannot supply. Defined as constants so
# the tests can assert them verbatim, and so the document never leaves a heading
# standing empty or implies the export produced a complete 4+1 architecture.
LOGICAL_VIEW_NOTE = (
    "**Not derived from the Fusion document.** The Logical View describes the "
    "functional decomposition of the system: the abstractions, what each is "
    "responsible for, and how they relate. A Fusion design records geometry and "
    "assembly structure, not function, so none of this view can be generated "
    "from it. Author it by hand; the component inventory below is the intended "
    "starting point."
)

SCENARIOS_VIEW_NOTE = (
    '**Not derived from the Fusion document.** The Scenarios view (the "+1") '
    "records the use cases the other four views are validated against. Fusion "
    "holds no use-case, requirement or operating-condition data, so none of this "
    "view can be generated from it. Author it by hand; each scenario should name "
    "the components it involves."
)


def md_cell(text) -> str:
    """Escape a value for a Markdown table cell.

    Brackets are escaped as well as pipes: a component named ``[click](evil)``
    would otherwise render as a link in a document someone else reads.
    """
    value = "" if text is None else str(text)
    cleaned = re.sub(r"\s+", " ", _CONTROL_CHARS.sub(" ", value)).strip()
    return (
        cleaned.replace("\\", "\\\\")
        .replace("|", "\\|")
        .replace("[", "\\[")
        .replace("]", "\\]")
        .replace("`", "\\`")
    )


def _mass_sums(assembly, counts):
    """``(naive column sum, assembly total)`` in kg, or ``(None, None)``.

    The naive figure is what a reader gets by adding the inventory's Mass
    column over every row times its quantity. Because a subassembly's mass
    already includes its contents, that double-counts; quoting both numbers
    side by side is the shortest way to stop someone doing it. Returns nothing
    when the root has no mass, since there would be nothing to compare against.
    """
    root = assembly.root
    if root is None or root.mass_kg is None:
        return None, None
    naive = 0.0
    for key, node in assembly.nodes.items():
        if node.mass_kg is not None:
            naive += node.mass_kg * counts.get(key, 0)
    return naive, root.mass_kg


def _md_point(point, factor: float = 1.0) -> str:
    """A three-component value for a table cell, or an em dash when absent."""
    if point is None:
        return "—"
    return ", ".join(coordinate(value * factor) for value in point)


def _md_axis(joint) -> str:
    """The joint's axis and what it governs, or an em dash.

    A rigid joint has no axis, and saying so with a dash is the point: the empty
    cell distinguishes "does not move" from "moves, direction unknown".
    """
    if joint.axis is None:
        return "—"
    vector = _md_point(joint.axis)
    return f"{vector} ({md_cell(joint.axis_role)})" if joint.axis_role else vector


def _md_number(value) -> str:
    """A table-ready number, or an em dash when the value is unknown."""
    if value is None:
        return "—"
    return number(value)


def add_document(assembly, sysml_filename: str) -> str:
    """Render the Architecture Design Document for *assembly*.

    Structured on the 4+1 View Model. The Physical View is generated in full;
    the Process and Development Views carry what Fusion genuinely supports
    (joints and linked documents); the Logical View and Scenarios say plainly
    that they are not derivable and must be written by a person.
    """
    meta = assembly.meta
    rows = m.walk(assembly)
    counts = m.total_counts(assembly)
    root = assembly.root
    joints = assembly.joints
    unplaced = m.unplaced_joints(assembly)

    out: list = []
    out.append(f"# {md_cell(meta.document_name)} — Architecture Design Document")
    out.append("")
    out.append(
        "> Generated file. Regenerate it with **File › Export SysML Architecture "
        "Document...** in Autodesk Fusion rather than editing the generated "
        "sections by hand."
    )
    out.append("")

    out.append("## Document control")
    out.append("")
    out.append("| Field | Value |")
    out.append("| --- | --- |")
    out.append(f"| Source document | {md_cell(meta.document_name)} |")
    out.append(f"| Version | {'—' if meta.version is None else meta.version} |")
    out.append(f"| Design type | {md_cell(meta.design_type) or '—'} |")
    out.append(f"| Root component | {md_cell(root.name) if root else '—'} |")
    out.append(f"| Exported | {md_cell(meta.exported_at) or '—'} |")
    out.append(
        f"| Document length unit | {md_cell(meta.length_units) or '—'} "
        "(recorded for reference; this document uses fixed units) |"
    )
    out.append("| Generator | PowerTools — Export SysML Architecture Document |")
    out.append("")

    out.append("## Architectural representation")
    out.append("")
    out.append(
        "This document uses the 4+1 View Model. A CAD assembly is the "
        "authoritative source for exactly one of the five views — the Physical "
        "View — which is generated here in full. Two more are partly derivable "
        "and carry what the design actually records. The remaining two require "
        "human intent and are left for an author."
    )
    out.append("")
    out.append("| View | Source | Status |")
    out.append("| --- | --- | --- |")
    out.append("| Logical | — | Author manually |")
    out.append("| Process | Fusion joints | Derived |")
    out.append("| Development | Fusion external references | Derived |")
    out.append("| Physical | Fusion assembly structure | Generated |")
    out.append("| Scenarios | — | Author manually |")
    out.append("")
    out.append(f"- {UNIT_NOTE}")
    out.append(
        "- Components are identified by their persistent Fusion component id, so "
        "two parts sharing a display name stay distinct."
    )
    out.append(
        "- An em dash (—) in a table means Fusion could not evaluate that value. "
        "It does not mean zero."
    )
    out.append("")

    out.append("## 1. Logical View")
    out.append("")
    out.append(LOGICAL_VIEW_NOTE)
    out.append("")

    out.append("## 2. Process View")
    out.append("")
    if joints:
        out.append(
            "Derived from the design's joints, which are what a Fusion model "
            "records about behaviour: they constrain how the assembly can move. "
            "This is kinematic structure, not runtime process behaviour — "
            "sequencing, concurrency and control must be authored."
        )
        out.append("")
        out.append("| Joint | Type | Connects | Origin (mm) | Axis | State |")
        out.append("| --- | --- | --- | --- | --- | --- |")
        for joint in joints:
            one = md_cell(joint.one_label) or "(unresolved)"
            two = md_cell(joint.two_label) or "(unresolved)"
            state = "Suppressed" if joint.is_suppressed else "Active"
            if joint.is_as_built:
                state += ", as-built"
            out.append(
                f"| {md_cell(joint.name)} | {md_cell(joint.joint_type)} | "
                f"{one} → {two} | {_md_point(joint.origin_cm, _MM_PER_CM)} | "
                f"{_md_axis(joint)} | {state} |"
            )
        out.append("")
        movable = [
            j
            for j in joints
            if j.joint_type not in ("Rigid", "") and not j.is_suppressed
        ]
        out.append(
            f"{len(joints)} joint(s) recorded; {len(movable)} permit relative "
            "motion in the built configuration."
        )
        # An as-built joint is defined by where its components already sit
        # rather than by picked geometry, so Fusion records no origin for it.
        # Said here because a table of em dashes otherwise reads as a failure
        # to collect rather than as nothing to collect.
        as_built = [joint for joint in joints if joint.is_as_built]
        if as_built:
            out.append("")
            out.append(
                f"{len(as_built)} of them are as-built joints, which record no "
                "origin: an as-built joint is defined by the position its "
                "components were already in, not by geometry someone picked, so "
                "there is no point for Fusion to report."
            )
    else:
        out.append(
            "The design records no joints, so no motion is derivable. Author this "
            "view by hand, or add joints to the assembly and export again."
        )
    out.append("")

    out.append("## 3. Development View")
    out.append("")
    refs = assembly.external_refs
    if refs:
        out.append(
            "Derived from the design's external references. Each linked document "
            "is versioned and edited independently, which makes this the design's "
            "real module structure."
        )
        out.append("")
        out.append("| Linked document | Version | Instances | Status |")
        out.append("| --- | --- | --- | --- |")
        for ref in refs:
            version = "—" if ref.version is None else str(ref.version)
            if ref.is_out_of_date is None:
                status = "—"
            elif ref.is_out_of_date:
                status = "Out of date"
            else:
                status = "Current"
            out.append(
                f"| {md_cell(ref.label)} | {version} | "
                f"{ref.instance_count} | {status} |"
            )
    else:
        out.append(
            "Every component is local to this document — there are no linked "
            "documents, so the design is a single development unit."
        )
    out.append("")

    out.append("## 4. Physical View")
    out.append("")
    out.append(
        "Generated from the assembly. This is the view the CAD model owns: what "
        "physically exists, how it nests, how many there are, and what each one "
        "weighs and occupies."
    )
    out.append("")

    out.append("### 4.1 Assembly hierarchy")
    out.append("")
    out.append("```")
    for row in rows:
        indent = "  " * row.depth
        multiplicity = f" x{row.count}" if row.count != 1 else ""
        marker = "  [not expanded further]" if row.truncated else ""
        out.append(
            f"{indent}{row.node.name}{multiplicity} ({m.classify(row.node)}){marker}"
        )
    out.append("```")
    out.append("")
    if any(row.truncated for row in rows):
        out.append(
            "> Branches marked *not expanded further* either recurse into one of "
            "their own ancestors or reach this export's depth limit."
        )
        out.append("")

    out.append("### 4.2 Component inventory")
    out.append("")
    out.append("| Component | Part number | Class | Qty | Mass (kg) | Material |")
    out.append("| --- | --- | --- | --- | --- | --- |")
    for key in m.definition_order(assembly):
        node = assembly.node(key)
        if node is None:
            continue
        out.append(
            f"| {md_cell(node.name)} | {md_cell(node.part_number) or '—'} | "
            f"{m.classify(node)} | {counts.get(key, 0)} | "
            f"{_md_number(node.mass_kg)} | {md_cell(node.material) or '—'} |"
        )
    out.append("")
    naive, total = _mass_sums(assembly, counts)
    if naive is not None and total is not None:
        out.append(
            "> **The Mass column does not sum.** A subassembly's mass includes "
            "everything inside it, so adding this column over every row counts "
            f"each subassembly's contents again: it gives {number(naive)} kg "
            f"for an assembly that weighs {number(total)} kg. The assembly "
            "total is the root's own figure, below."
        )
        out.append("")

    out.append("### 4.3 Mass and envelope")
    out.append("")
    out.append(f"- Unique components: {len(assembly.nodes)}")
    out.append(f"- Total instances: {sum(counts.values())}")
    if root is not None:
        out.append(f"- Assembly mass: {_md_number(root.mass_kg)} kg")
        out.append(f"- Assembly volume: {_md_number(root.volume_cm3)} cm^3")
        out.append(f"- Assembly surface area: {_md_number(root.area_cm2)} cm^2")
        extents = extents_mm(root)
        if extents is None:
            out.append("- Assembly envelope: —")
        else:
            sides = " x ".join(number(side) for side in extents)
            out.append(f"- Assembly envelope (L x W x H): {sides} mm")
    out.append("")
    out.append(
        "> Mass, volume, area and the envelope all include a component's "
        "children. The figures above are therefore the assembly's own totals "
        "as Fusion reports them for the root, not something this export added "
        "up — and adding them up is exactly what would go wrong, since every "
        "subassembly already contains its parts."
    )
    out.append("")

    out.append("### 4.4 Physical interfaces")
    out.append("")
    if joints:
        placed_count = len(joints) - len(unplaced)
        out.append(
            f"{placed_count} of {len(joints)} joint(s) are expressed as SysML "
            "connections in the model file. A joint becomes a connection when "
            "both of its ends sit somewhere below the component that owns it "
            "and the joint is not suppressed; an end deeper than a direct child "
            "is named by a dotted path."
        )
        if unplaced:
            out.append("")
            out.append("| Joint | Type | Not expressed because |")
            out.append("| --- | --- | --- |")
            for joint, reason in unplaced:
                out.append(
                    f"| {md_cell(joint.name)} | {md_cell(joint.joint_type)} | "
                    f"{md_cell(reason)} |"
                )
    else:
        out.append("The design records no joints.")
    out.append("")

    out.append("### 4.5 SysML model")
    out.append("")
    out.append(
        f"The generated model is `{md_cell(sysml_filename)}`, in SysML v2 "
        "textual notation, alongside this document. It carries one `part def` "
        "per unique component, with composition held in the definitions."
    )
    out.append("")

    out.append("## 5. Scenarios (+1)")
    out.append("")
    out.append(SCENARIOS_VIEW_NOTE)
    out.append("")

    out.append("## Appendix A — Collection notes")
    out.append("")
    if assembly.notes:
        out.append(
            "Values this export could not read from the design. Each one is a "
            "gap in the tables above, not a zero."
        )
        out.append("")
        for note in assembly.notes:
            out.append(f"- {md_cell(note)}")
    else:
        out.append("Every value in this document was read from the design cleanly.")
    out.append("")

    out.append("## Appendix B — Regeneration")
    out.append("")
    out.append(
        "The Physical View and the SysML model are generated, and edits to them "
        "are lost on the next export. Change the Fusion design and re-run the "
        "command. The Logical View and Scenarios are authored by hand, so export "
        "into a new folder and copy them across rather than overwriting a "
        "document you have written into."
    )
    out.append("")
    return "\n".join(out)
