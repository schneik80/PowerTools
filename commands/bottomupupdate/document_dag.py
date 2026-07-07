# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.

"""Prototype: document-level dependency DAG for Bottom-Up Update.

This is **not wired into the command**. It builds the bottom-up save order over
*documents* (keyed by ``dataFile.id``) instead of over *components* (keyed by
``name``, as ``entry.py`` does today), so the two orderings can be diffed before
any switch is committed. The resume/log machinery is deliberately untouched.

Design notes
------------
* The only Autodesk Fusion API contact is isolated in :func:`resolve_document`,
  and it uses the *exact* resolution path the current processing loop already
  relies on (``component.parentDesign.parentDocument.designDataFile``). This
  module therefore introduces **no new API assumptions**. Unit tests inject a
  fake ``resolver`` and never touch Fusion.
* The graph is keyed by ``dataFile.id``, so it is inherently collision-safe:
  two distinct documents whose representative components happen to share a
  *name* still get two nodes. This is the structural fix for the name-collision
  silent-skip in the component-name graph.

Drop-in comparison
------------------
To A/B this against the live ordering without touching the loop, resume, or log,
one line in ``entry.command_execute`` would change from::

    bottom_up_order = sort_dag_bottom_up(assembly_dict)

to::

    bottom_up_order = document_bottom_up_names(root_component)

**Caveat that this prototype is meant to expose:** the loop still maps each
emitted *name* back to a component via ``components_by_name``. Projecting the
id-keyed order back to names (:func:`document_bottom_up_names`) re-exposes the
name collision at that boundary. The graph itself is collision-safe; realising
that safety end to end requires the loop to consume ``doc_id`` values
(:func:`document_bottom_up_order`), which is the deferred follow-up that does
touch the loop/resume/log.
"""

from typing import Callable, Optional

# A resolver maps a component to (doc_id, display_name), or None when the
# component has no own saved document (internal / unsaved geometry).
Resolver = Callable[[object], Optional[tuple[str, str]]]


def resolve_document(component: object) -> Optional[tuple[str, str]]:
    """Resolve a component's owning document id and display name.

    Mirrors the ownership resolution the current processing loop performs: walk
    to the owning document's ``designDataFile`` and read its id. A component
    with no reachable design data file (internal or never-externalized
    geometry) returns ``None`` so the caller folds it into its parent document
    rather than treating it as a separate save unit.

    Args:
        component: An ``adsk.fusion.Component`` (or any object exposing the same
            ``parentDesign.parentDocument.designDataFile`` chain and ``name``).

    Returns:
        A ``(doc_id, display_name)`` tuple, or ``None`` if no owning document
        data file can be resolved.
    """
    try:
        parent_document = component.parentDesign.parentDocument
    except AttributeError:
        return None
    design_data_file = getattr(parent_document, "designDataFile", None)
    if design_data_file is None:
        return None
    doc_id = getattr(design_data_file, "id", None)
    if not doc_id:
        return None
    return doc_id, component.name


def build_document_dag(
    root_component: object,
    resolver: Resolver = resolve_document,
) -> tuple[dict, Optional[str]]:
    """Build a document-level DAG from an assembly's occurrence tree.

    Walks ``component.occurrences`` depth-first while carrying the id of the
    document that currently owns the walk. Crossing into a component owned by a
    *different* document creates one graph node (deduped by ``doc_id``) and one
    edge; staying within the same document folds internal sub-components into
    their owner. Components that resolve to ``None`` are treated as internal to
    the current document.

    Args:
        root_component: The assembly root component to traverse.
        resolver: Callable mapping a component to ``(doc_id, name)`` or ``None``.
            Defaults to :func:`resolve_document`; injected in tests.

    Returns:
        A ``(nodes, root_doc_id)`` pair where ``nodes`` maps ``doc_id`` to a
        node dict ``{"doc_id", "name", "children": {doc_id: node}}`` and
        ``root_doc_id`` is the active document's id (``None`` if unresolved).
    """
    nodes: dict = {}

    def get_node(doc_id: str, name: Optional[str]) -> dict:
        node = nodes.get(doc_id)
        if node is None:
            node = {"doc_id": doc_id, "name": name, "children": {}}
            nodes[doc_id] = node
        return node

    root = resolver(root_component)
    root_doc_id = root[0] if root else None
    if root_doc_id is not None:
        get_node(root_doc_id, root[1])

    # Documents whose internals have already been walked; components already
    # walked within a document (keyed by (doc_id, name), which is unique because
    # component names are unique within a design and stable across marshalling).
    expanded_docs: set = set()
    walked_components: set = set()

    def walk(component: object, current_doc_id: Optional[str]) -> None:
        for occurrence in component.occurrences:
            child = occurrence.component
            resolved = resolver(child)
            child_doc_id = resolved[0] if resolved else current_doc_id

            if child_doc_id is not None and child_doc_id != current_doc_id:
                # A reference to another document: record the edge once.
                child_node = get_node(child_doc_id, child.name)
                if current_doc_id is not None:
                    nodes[current_doc_id]["children"][child_doc_id] = child_node
                if child_doc_id in expanded_docs:
                    continue  # That document's internals are already known.
                expanded_docs.add(child_doc_id)
                walk(child, child_doc_id)
            else:
                # Internal to the current document: keep the same owner and keep
                # discovering outgoing edges, but never re-walk a shared node.
                key = (current_doc_id, child.name)
                if key in walked_components:
                    continue
                walked_components.add(key)
                walk(child, current_doc_id)

    if root_doc_id is not None:
        expanded_docs.add(root_doc_id)
    walk(root_component, root_doc_id)
    return nodes, root_doc_id


def sort_document_dag_bottom_up(
    nodes: dict,
    root_doc_id: Optional[str],
) -> list[dict]:
    """Topologically sort the document DAG into bottom-up (leaves-first) order.

    Depth-first, post-order traversal with the same tri-color guards as the
    component sort: an ``emitted`` set makes each document appear once (diamond
    dependencies collapse) and keeps the walk O(V + E); an ``in_progress`` set
    breaks any unexpected cycle instead of overflowing the stack. The root
    document is excluded from the result because the command saves it separately
    at the end.

    Args:
        nodes: The ``doc_id`` -> node map from :func:`build_document_dag`.
        root_doc_id: The active document's id, excluded from the output.

    Returns:
        A list of node dicts in bottom-up order (root document omitted).
    """
    order: list[dict] = []
    emitted: set = set()
    in_progress: set = set()

    def visit(node: dict) -> None:
        doc_id = node["doc_id"]
        if doc_id in emitted:
            return
        if doc_id in in_progress:
            return  # Cycle guard; a real reference graph never reaches here.
        in_progress.add(doc_id)
        for child in node["children"].values():
            visit(child)
        in_progress.discard(doc_id)
        emitted.add(doc_id)
        if doc_id != root_doc_id:
            order.append(node)

    root_node = nodes.get(root_doc_id)
    if root_node is not None:
        visit(root_node)
    else:
        for node in nodes.values():
            visit(node)
    return order


def document_bottom_up_order(
    root_component: object,
    resolver: Resolver = resolve_document,
) -> list[dict]:
    """Return the bottom-up save order as document records.

    This is the target shape for when the processing loop moves to consuming
    document ids directly.

    Args:
        root_component: The assembly root component to traverse.
        resolver: Component -> ``(doc_id, name)`` resolver; injected in tests.

    Returns:
        A list of ``{"doc_id", "name"}`` records, leaves first, root omitted.
    """
    nodes, root_doc_id = build_document_dag(root_component, resolver)
    ordered = sort_document_dag_bottom_up(nodes, root_doc_id)
    return [{"doc_id": node["doc_id"], "name": node["name"]} for node in ordered]


def document_bottom_up_names(
    root_component: object,
    resolver: Resolver = resolve_document,
) -> list[str]:
    """Return the bottom-up order as names, drop-in for the current loop.

    Provided only for A/B comparison against ``sort_dag_bottom_up``; see the
    module docstring for the name-collision caveat this projection re-exposes at
    the loop boundary.

    Args:
        root_component: The assembly root component to traverse.
        resolver: Component -> ``(doc_id, name)`` resolver; injected in tests.

    Returns:
        A list of representative component names, leaves first, root omitted.
    """
    return [record["name"] for record in document_bottom_up_order(root_component, resolver)]
