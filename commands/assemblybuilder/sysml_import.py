# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.
"""Read a SysML v2 Physical View back into an Assembly Builder graph.

This is the inverse of the Export SysML Architecture Document command, but it
reads more than that command writes, because SysML v2 has two idiomatic ways to
record composition and real models use both:

* **In the definitions.** ``part def Gearbox { part housing : Housing; }`` --
  what the export command emits, since it writes one definition per unique
  component.
* **In the usage tree.** ``part rm500 : MowerProduct { part mower :
  MowerAssembly { part chassis : ChassisAssembly { ... } } }`` -- how a
  hand-authored physical architecture usually reads, as one nested instance
  tree under a single top-level usage.

Both say the same thing: the enclosing component contains the enclosed one. So
the parser tracks an *owner* while it walks -- the component a statement sits
inside, whether that came from a ``part def`` header or from the type of an
enclosing usage -- and every ``part`` usage it meets becomes a child of the
current owner. A usage at package level, with no owner, is a candidate for the
root instead.

Nothing here imports ``adsk``. ``entry.py`` reads the file and hands the text
over; everything about parsing, kind inference, root selection and the shape of
the resulting graph is decided here and unit tested outside Fusion (see
``tests/test_assemblybuilder_sysml_import.py``).

Two deliberate exclusions:

* Only ``part`` contributes structure. ``item`` does not: SysML models use
  items for things that flow and for material definitions, and a physical
  architecture that declares ``item pa6gf30 : Material`` must not import
  glass-filled nylon as a component.
* Anything the parser does not recognise is skipped rather than treated as an
  error. A real model carries ports, interfaces, concerns, requirements,
  allocations, variation points, views and metadata, none of which say anything
  about assembly composition.

Two properties of the target editor shape the output:

* Drawflow's ``addConnection`` refuses a duplicate parent-to-child link, so a
  usage with multiplicity above one cannot be represented as repeated edges.
  Those multiplicities are collapsed to a single edge and reported, rather than
  being silently dropped or faked as separate components.
* A node in the editor is a unique component and several parents mean a shared
  component, so the output is a DAG keyed by component name.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Node types the Assembly Builder editor understands. These are the keys of
# ``nodeTypes`` in the palette page and of ``INTENT_MAP`` in ``entry.py``.
KIND_PART = "part"
KIND_ASSEMBLY = "assembly"
KIND_HYBRID = "hybrid"

# ``classification`` values written by the export command, plus the spellings a
# hand-written model is likely to use. "empty" becomes a part: a component with
# neither bodies nor children is still a leaf in the editor.
CLASSIFICATION_KINDS = {
    "part": KIND_PART,
    "leaf": KIND_PART,
    "empty": KIND_PART,
    "assembly": KIND_ASSEMBLY,
    "subassembly": KIND_ASSEMBLY,
    "hybrid": KIND_HYBRID,
}

# Guard against a model whose usages form a cycle. A component cannot contain
# itself in Fusion, but nothing stops a text file from saying it does.
MAX_DEPTH = 64

_IDENTIFIER = r"[A-Za-z_][A-Za-z0-9_]*"
# A SysML name is a bare identifier, a qualified one, or a single-quoted
# unrestricted name with backslash escapes.
_NAME = rf"(?:'(?:[^'\\]|\\.)*'|{_IDENTIFIER}(?:\s*::\s*{_IDENTIFIER})*)"

# An optional ``<'SHORT-NAME'>`` alias may precede the declared name.
_SHORT_NAME = rf"(?:<\s*{_NAME}\s*>\s*)?"

_PACKAGE_RE = re.compile(rf"^package\s+{_SHORT_NAME}({_NAME})")
_PART_DEF_RE = re.compile(rf"^part\s+def\s+{_SHORT_NAME}({_NAME})")
# Matched as a prefix on purpose: a usage header continues with specialisation
# (``:> subItems``), redefinition, or a body, none of which change what it is.
_USAGE_RE = re.compile(rf"^part\s+({_NAME})\s*:\s*({_NAME})\s*(?:\[([^\]]*)\])?")
_BARE_USAGE_RE = re.compile(rf"^part\s+({_NAME})\s*$")
_ATTRIBUTE_RE = re.compile(rf"^attribute\s+({_NAME})\s*(?::[^=]*)?=\s*(.+)$")
_INTEGER_RE = re.compile(r"\d+")

# Modifiers that turn a usage into something other than a fitted child. A
# variation point and its variants are alternatives, so importing them all
# would overstate the assembly.
_VARIANT_PREFIXES = ("variation ", "variant ")


@dataclass(frozen=True)
class Usage:
    """One ``part`` usage inside an owner: which type, and how many."""

    type_name: str
    count: int = 1
    usage_name: str = ""


@dataclass(frozen=True)
class Definition:
    """One component: its name, what it is, and what it contains."""

    name: str
    kind: str = KIND_PART
    children: tuple[Usage, ...] = ()
    classification: str = ""
    is_external_reference: bool = False
    is_declared: bool = True


@dataclass
class ImportResult:
    """Everything the parse found, plus what the reader should be told about."""

    package_name: str = ""
    root: str = ""
    definitions: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)


@dataclass
class _Accum:
    """A component under construction while the file is being walked.

    Children accumulate from every site that declares one, because in a usage
    tree the same type can be expanded in more than one place, and a definition
    can be declared after it is first used.
    """

    name: str
    declared: bool = False
    classification: str = ""
    is_reference: bool = False
    has_bodies: bool = False
    children: list = field(default_factory=list)


def _skip_quoted(text: str, index: int) -> int:
    """Index just past the quoted run starting at *index*.

    Quoted spans are skipped wholesale when scanning for statement delimiters,
    so a semicolon or a brace inside a component name cannot be mistaken for
    structure.
    """
    quote = text[index]
    index += 1
    length = len(text)
    while index < length:
        if text[index] == "\\":
            index += 2
            continue
        if text[index] == quote:
            return index + 1
        index += 1
    return length


def strip_comments(text: str) -> str:
    """Remove ``//`` and ``/* */`` comments, leaving quoted spans untouched.

    Comments are dropped before anything else is parsed, which is also what
    makes a ``doc /* ... */`` block disappear -- its ``doc`` keyword is then a
    statement with nothing after it and is skipped as unrecognised.
    """
    out = []
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if char in "'\"":
            end = _skip_quoted(text, index)
            out.append(text[index:end])
            index = end
            continue
        if text.startswith("//", index):
            newline = text.find("\n", index)
            index = length if newline == -1 else newline
            continue
        if text.startswith("/*", index):
            end = text.find("*/", index + 2)
            index = length if end == -1 else end + 2
            out.append(" ")
            continue
        out.append(char)
        index += 1
    return "".join(out)


def _split_statements(body: str) -> list:
    """Split a block body into ``(head, block)`` pairs.

    ``head`` is the text before a ``;`` or a ``{``; ``block`` is the balanced
    brace body, or ``None`` for a simple statement. Quoted spans are skipped so
    punctuation inside a name never ends a statement.
    """
    statements = []
    start = 0
    index = 0
    length = len(body)
    while index < length:
        char = body[index]
        if char in "'\"":
            index = _skip_quoted(body, index)
            continue
        if char == ";":
            statements.append((body[start:index].strip(), None))
            index += 1
            start = index
            continue
        if char == "{":
            depth = 1
            cursor = index + 1
            while cursor < length and depth:
                inner = body[cursor]
                if inner in "'\"":
                    cursor = _skip_quoted(body, cursor)
                    continue
                if inner == "{":
                    depth += 1
                elif inner == "}":
                    depth -= 1
                cursor += 1
            statements.append((body[start:index].strip(), body[index + 1 : cursor - 1]))
            index = cursor
            start = index
            continue
        if char == "}":
            # An unbalanced closer: stop rather than reading the rest as one
            # long statement.
            break
        index += 1
    tail = body[start:].strip()
    if tail:
        statements.append((tail, None))
    return statements


def unquote(name: str) -> str:
    """The readable form of a SysML name.

    Strips the single quotes of an unrestricted name and undoes its escapes, and
    reduces a qualified name to its final segment so ``Parts::Housing`` resolves
    against a definition called ``Housing``.
    """
    text = (name or "").strip()
    if len(text) >= 2 and text.startswith("'") and text.endswith("'"):
        inner = text[1:-1]
        out = []
        index = 0
        while index < len(inner):
            if inner[index] == "\\" and index + 1 < len(inner):
                nxt = inner[index + 1]
                out.append({"n": "\n", "t": "\t", "r": "\r"}.get(nxt, nxt))
                index += 2
                continue
            out.append(inner[index])
            index += 1
        return "".join(out).strip()
    if "::" in text:
        text = text.split("::")[-1]
    return text.strip()


def _literal(value: str) -> str:
    """The text of a string literal, or the raw token when it is not one."""
    text = (value or "").strip().rstrip(";").strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1]
    return text


def multiplicity(text) -> int:
    """The instance count declared in a ``[...]`` multiplicity.

    The first integer wins, so ``[2]`` and ``[2..4]`` both read as two, and a
    range floor of zero is clamped to one: an optional component still gets a
    single link, because the editor has no way to draw "sometimes present".
    """
    if not text:
        return 1
    found = _INTEGER_RE.search(text)
    if not found:
        return 1
    return max(1, int(found.group(0)))


def _read_own_attributes(body: str) -> tuple:
    """``(classification, is_reference, has_bodies)`` from a definition's body.

    Only the immediate statements are read. A nested definition's attributes
    describe that definition, not this one.
    """
    classification = ""
    is_reference = False
    has_bodies = False
    for head, _block in _split_statements(body or ""):
        if not head:
            continue
        attribute = _ATTRIBUTE_RE.match(" ".join(head.split()))
        if not attribute:
            continue
        key = unquote(attribute.group(1))
        value = _literal(attribute.group(2))
        if key == "classification":
            classification = value.strip().casefold()
        elif key == "isExternalReference":
            is_reference = value.strip().casefold() == "true"
        elif key == "bodyCount":
            found = _INTEGER_RE.search(value)
            has_bodies = bool(found) and int(found.group(0)) > 0
    return classification, is_reference, has_bodies


def _infer_kind(classification: str, children, has_bodies: bool) -> str:
    """Decide a node type from the classification, falling back to the shape.

    An explicit ``classification`` attribute wins, since the exporter writes the
    distinction Fusion actually recorded. Without one -- a model from another
    tool -- the shape is the only evidence: children make it an assembly,
    nothing makes it a part. ``hybrid`` cannot be inferred from structure alone
    and is never guessed.

    One case overrides the classification: a definition labelled as a leaf that
    nonetheless contains usages. The structure has to win there, because a part
    node in the editor has no output port and its children would have nothing
    to attach to.
    """
    kind = CLASSIFICATION_KINDS.get(classification, "")
    if kind == KIND_PART and children:
        kind = KIND_HYBRID if has_bodies else KIND_ASSEMBLY
    if kind:
        return kind
    if children and has_bodies:
        return KIND_HYBRID
    if children:
        return KIND_ASSEMBLY
    return KIND_PART


def parse(text: str) -> ImportResult:
    """Parse SysML v2 textual notation into components and a root.

    Arguments:
    text -- The contents of a ``.sysml`` file.

    Returns:
    An :class:`ImportResult`. ``root`` is empty when no structure was found;
    ``warnings`` explains anything the caller should pass on to the user.
    """
    result = ImportResult()
    stripped = strip_comments(text or "")
    accums: dict = {}
    root_usages: list = []
    variant_types: set = set()

    def accumulator(name: str) -> _Accum:
        entry = accums.get(name)
        if entry is None:
            entry = _Accum(name=name)
            accums[name] = entry
        return entry

    def walk(body: str, depth: int, owner) -> None:
        """Scan one block body on behalf of *owner*.

        ``owner`` is the component whose composition the statements here
        describe: the name from an enclosing ``part def``, or the *type* of an
        enclosing ``part`` usage. ``None`` means package level, where a usage
        names the design as a whole rather than a child of something.
        """
        if depth > MAX_DEPTH:
            return
        for head, block in _split_statements(body):
            if not head:
                continue
            collapsed = " ".join(head.split())

            package = _PACKAGE_RE.match(collapsed)
            if package and block is not None:
                if not result.package_name:
                    result.package_name = unquote(package.group(1))
                walk(block, depth + 1, None)
                continue

            definition = _PART_DEF_RE.match(collapsed)
            if definition:
                name = unquote(definition.group(1))
                if not name:
                    result.warnings.append("Skipped a part definition with no name.")
                    continue
                entry = accumulator(name)
                if entry.declared:
                    result.warnings.append(
                        f"More than one definition is named {name!r}; "
                        "the first one was used."
                    )
                else:
                    entry.declared = True
                    (
                        entry.classification,
                        entry.is_reference,
                        entry.has_bodies,
                    ) = _read_own_attributes(block or "")
                if block:
                    walk(block, depth + 1, name)
                continue

            # A variation point offers alternatives rather than parts that are
            # all fitted, so neither it nor its variants becomes a child. The
            # types are recorded so the summary can say they were left out.
            if collapsed.startswith(_VARIANT_PREFIXES):
                remainder = collapsed.split(" ", 1)[1] if " " in collapsed else ""
                variant = _USAGE_RE.match(remainder)
                if variant:
                    variant_types.add(unquote(variant.group(2)))
                if block:
                    walk(block, depth + 1, None)
                continue

            usage = _USAGE_RE.match(collapsed)
            if usage:
                type_name = unquote(usage.group(2))
                if type_name:
                    if owner:
                        accumulator(owner).children.append(
                            Usage(
                                type_name=type_name,
                                count=multiplicity(usage.group(3)),
                                usage_name=unquote(usage.group(1)),
                            )
                        )
                    else:
                        root_usages.append(type_name)
                    # A usage's own body describes what its *type* contains.
                    if block:
                        walk(block, depth + 1, type_name)
                continue

            bare = _BARE_USAGE_RE.match(collapsed)
            if bare and block is None:
                result.warnings.append(
                    f"Ignored the untyped usage {unquote(bare.group(1))!r}, "
                    "which names no component."
                )
                continue

            # Ports, interfaces, connections, concerns, requirements, metadata
            # and the rest: not structure, but they can nest structure, so the
            # walk continues with the same owner.
            if block:
                walk(block, depth + 1, owner)

    walk(stripped, 0, None)

    # A type only ever used, never defined, still counts as a component when the
    # file told us what it contains -- dropping it would take its whole subtree
    # with it. A leaf we know nothing about stays unknown and is reported later.
    implicit = sorted(
        name for name, entry in accums.items() if not entry.declared and entry.children
    )
    for name, entry in accums.items():
        if not entry.declared and not entry.children:
            continue
        children = tuple(entry.children)
        result.definitions[name] = Definition(
            name=name,
            kind=_infer_kind(entry.classification, children, entry.has_bodies),
            children=children,
            classification=entry.classification,
            is_external_reference=entry.is_reference,
            is_declared=entry.declared,
        )

    if not result.definitions:
        result.warnings.append(
            "No component definitions or part usages were found, so there is "
            "no structure to import."
        )
        return result

    if implicit:
        result.warnings.append(
            f"{len(implicit)} component(s) have no 'part def' but are used and "
            "have contents, so they were read from their usages: " + ", ".join(implicit)
        )
    if variant_types:
        result.warnings.append(
            f"{len(variant_types)} variation point alternative(s) were left "
            "out, because a variant is a choice rather than a fitted "
            "component: " + ", ".join(sorted(variant_types))
        )

    result.root = _choose_root(result, root_usages)
    return result


def _subtree_size(result: ImportResult, name: str) -> int:
    """How many distinct components *name* reaches, itself included."""
    seen: set = set()

    def visit(key: str, depth: int) -> None:
        if key in seen or depth > MAX_DEPTH:
            return
        definition = result.definitions.get(key)
        if definition is None:
            return
        seen.add(key)
        for usage in definition.children:
            visit(usage.type_name, depth + 1)

    visit(name, 0)
    return len(seen)


def _choose_root(result: ImportResult, root_usages: list) -> str:
    """Pick the component the hierarchy hangs from.

    Package-level usages are the evidence, but not all of them are candidates. A
    stakeholder package that declares eight ``part someRole : Role;`` lines
    contributes eight usages that contain nothing, and picking one of those as
    the root would import a single empty node. So the choice prefers a top-level
    usage whose type actually has contents, and only then falls back to the
    largest structure it can find. Getting this wrong silently reparents the
    whole assembly, so every fallback carries a warning.
    """
    ordered: list = []
    for name in root_usages:
        if name in result.definitions and name not in ordered:
            ordered.append(name)

    structural = [name for name in ordered if result.definitions[name].children]
    if len(structural) == 1:
        return structural[0]
    if structural:
        best = max(structural, key=lambda n: _subtree_size(result, n))
        result.warnings.append(
            f"The file declares {len(structural)} top-level components with "
            f"contents ({', '.join(structural)}); {best!r} was used as the root "
            "because it is the largest."
        )
        return best

    if len(ordered) == 1:
        return ordered[0]
    if ordered:
        best = max(ordered, key=lambda n: _subtree_size(result, n))
        result.warnings.append(
            f"The file declares {len(ordered)} top-level components "
            f"({', '.join(ordered)}); {best!r} was used as the root."
        )
        return best

    referenced = {
        usage.type_name
        for definition in result.definitions.values()
        for usage in definition.children
    }
    candidates = [name for name in result.definitions if name not in referenced]
    if len(candidates) == 1:
        result.warnings.append(
            f"No top-level part usage was declared; {candidates[0]!r} was used "
            "as the root because nothing else contains it."
        )
        return candidates[0]
    if candidates:
        best = max(candidates, key=lambda n: _subtree_size(result, n))
        result.warnings.append(
            f"No top-level part usage was declared and {len(candidates)} "
            f"components are uncontained; {best!r} was used as the root "
            "because it is the largest."
        )
        return best

    first = next(iter(result.definitions))
    result.warnings.append(
        "Every component is contained by another, which means the model is "
        f"cyclic; {first!r} was used as the root."
    )
    return first


@dataclass
class Graph:
    """A node/edge list ready for the palette to build, plus what to report."""

    root_key: str = ""
    nodes: list = field(default_factory=list)
    edges: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    collapsed: list = field(default_factory=list)
    skipped: list = field(default_factory=list)


def to_graph(result: ImportResult) -> Graph:
    """Flatten *result* into the nodes and edges the editor should contain.

    Reachability from the root decides what is included: a component nothing
    contains would arrive as a node wired to nothing, and the creation pass only
    walks down from the root, so it would look imported while never being built.
    Those are reported as skipped instead.
    """
    graph = Graph(root_key=result.root, warnings=list(result.warnings))
    if not result.root or result.root not in result.definitions:
        return graph

    seen: set = set()
    edges: set = set()
    order: list = []

    def visit(key: str, depth: int, ancestors: frozenset) -> None:
        definition = result.definitions.get(key)
        if definition is None:
            return
        if key not in seen:
            seen.add(key)
            order.append(key)
        if depth >= MAX_DEPTH:
            graph.warnings.append(
                f"Stopped at {key!r}: the model nests deeper than {MAX_DEPTH} levels."
            )
            return

        # Several usages of one type under the same owner become one link with
        # a combined count, since the canvas holds only one link per pair.
        totals: dict = {}
        for usage in definition.children:
            totals[usage.type_name] = totals.get(usage.type_name, 0) + usage.count

        for child, count in totals.items():
            if child not in result.definitions:
                graph.skipped.append(f"{child} in {key} (no definition for it)")
                continue
            if child in ancestors or child == key:
                graph.warnings.append(
                    f"{child!r} contains itself through {key!r}; "
                    "that link was left out."
                )
                continue
            if count > 1:
                graph.collapsed.append(f"{count} x {child} in {key}")
            pair = (key, child)
            if pair not in edges:
                edges.add(pair)
                graph.edges.append({"parent": key, "child": child})
            visit(child, depth + 1, ancestors | {key})

    visit(result.root, 0, frozenset())

    graph.nodes = [
        {
            "key": key,
            "name": result.definitions[key].name,
            "kind": result.definitions[key].kind,
            "isRoot": key == result.root,
            "isExternalReference": result.definitions[key].is_external_reference,
        }
        for key in order
    ]

    unreachable = [name for name in result.definitions if name not in seen]
    if unreachable:
        graph.skipped.extend(
            f"{name} (not contained by the root assembly)"
            for name in sorted(unreachable)
        )
    return graph


# A message box is not a log: past a couple of dozen lines it stops being read
# and starts being dismissed. The full detail goes to the debug log instead.
SUMMARY_LIST_CAP = 20


def _capped(items: list) -> list:
    """*items*, trimmed to a length a dialog can actually show."""
    if len(items) <= SUMMARY_LIST_CAP:
        return list(items)
    remaining = len(items) - SUMMARY_LIST_CAP
    return list(items[:SUMMARY_LIST_CAP]) + [f"... and {remaining} more"]


def summarize(graph: Graph) -> str:
    """A report of what the import did, for a message box.

    Everything the graph could not represent is named. An import that quietly
    dropped a component would leave the user building an assembly they believe
    matches the model and does not.
    """
    if not graph.root_key:
        lines = ["No component structure could be read from that file."]
        lines.extend(graph.warnings)
        return "\n".join(lines)

    components = len(graph.nodes)
    shared = _shared_children(graph)
    lines = [
        f"Imported {components} component"
        f"{'' if components == 1 else 's'} from the SysML physical view.",
        "",
        f"Root: {graph.root_key}",
        f"Links: {len(graph.edges)}",
    ]
    if shared:
        lines.append(f"Shared components (more than one parent): {shared}")

    if graph.collapsed:
        lines.append("")
        lines.append(
            "Quantities above one were collapsed to a single link, because the "
            "node editor holds one node per component. Add the extra instances "
            "after the assembly is built:"
        )
        lines.extend(f"  - {item}" for item in _capped(graph.collapsed))

    externals = [n["name"] for n in graph.nodes if n["isExternalReference"]]
    if externals:
        lines.append("")
        lines.append(
            "These were linked from other documents in the source design and "
            "will be created as new external components:"
        )
        lines.extend(f"  - {name}" for name in _capped(externals))

    if graph.skipped:
        lines.append("")
        lines.append("Not imported:")
        lines.extend(f"  - {item}" for item in _capped(graph.skipped))

    if graph.warnings:
        lines.append("")
        lines.extend(graph.warnings)

    return "\n".join(lines)


def _shared_children(graph: Graph) -> int:
    """How many components have more than one parent in *graph*."""
    parents: dict = {}
    for edge in graph.edges:
        parents.setdefault(edge["child"], set()).add(edge["parent"])
    return sum(1 for owners in parents.values() if len(owners) > 1)
