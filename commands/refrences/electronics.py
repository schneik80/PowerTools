# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.
"""The electronics design a document belongs to -- pure logic, no ``adsk``.

An electronics design is four cloud files linked by references, which are the
link to rely on: ``Document.documentReferences`` was empty on all four
when each was opened alone, and populated only after a drawing loaded them.

    project (.fprj) --child--> schematic (.fsch)
    project (.fprj) --child--> 2D PCB    (.fbrd) --child--> 3D PCB (.f3d)
    drawing (.f2d)  --child--> project   (.fprj)

A drawing of an electronics design references the *project*, not the 3D PCB
it shows (observed with a Fusion drawing of the 3D PCB). A drawing that
references the 3D PCB directly is handled too, in case Fusion records that.

Starting from any of them, :func:`electronics_set` walks up to the project and
back down, so Document References can list the whole set. Observed with the
Fusion MCP on ADSKMVG91G2F5W, pre-production 2706.0.116, 2026-10-02.

Duck-typed: a file needs ``id``, ``fileExtension``, ``parentReferences`` and
``childReferences``. Each reference read is a cloud call that can raise, so
every one is guarded and a failure reads as "no references".
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .logic import unique_by_id

PROJECT = "fprj"
SCHEMATIC = "fsch"
BOARD = "fbrd"
DESIGN = "f3d"
DRAWING = "f2d"

ELECTRONICS_EXTENSIONS = (PROJECT, SCHEMATIC, BOARD)


@dataclass
class ElectronicsSet:
    projects: list = field(default_factory=list)
    schematics: list = field(default_factory=list)
    boards: list = field(default_factory=list)
    pcb3ds: list = field(default_factory=list)
    drawings: list = field(default_factory=list)

    def ids(self) -> set:
        """Every file id in the set."""
        out = set()
        for group in (
            self.projects,
            self.schematics,
            self.boards,
            self.pcb3ds,
            self.drawings,
        ):
            for item in group:
                out.add(_read(item, "id"))
        out.discard("")
        return out


def _read(obj, attr) -> str:
    try:
        return str(getattr(obj, attr) or "")
    except Exception:
        return ""


def extension(data_file) -> str:
    """``fileExtension``, lower-cased; "" when unreadable."""
    return _read(data_file, "fileExtension").casefold()


def _refs(data_file, attr: str) -> list:
    try:
        return list(getattr(data_file, attr) or [])
    except Exception:
        return []


def _of_type(files, ext: str) -> list:
    return [f for f in files if extension(f) == ext]


def is_electronics_file(data_file) -> bool:
    """A project, schematic or 2D board file."""
    return extension(data_file) in ELECTRONICS_EXTENSIONS


def boards_of_design(data_file) -> list:
    """The 2D boards a design is the 3D PCB of; empty for an ordinary design."""
    if extension(data_file) != DESIGN:
        return []
    return _of_type(_refs(data_file, "parentReferences"), BOARD)


def electronics_set(active) -> ElectronicsSet | None:
    """The electronics design *active* belongs to, or None if it is not part of one.

    A design counts only when a 2D board references it (it is a 3D PCB); a
    drawing only when it references a project or a 3D PCB. Files that cannot
    be reached through a project -- a board whose project
    link is missing -- still list what their own references reach.
    """
    ext = extension(active)
    if ext == PROJECT:
        projects = [active]
    elif ext in (SCHEMATIC, BOARD):
        projects = _of_type(_refs(active, "parentReferences"), PROJECT)
    elif ext == DESIGN:
        start_boards = boards_of_design(active)
        if not start_boards:
            return None
        projects = []
        for board in start_boards:
            projects += _of_type(_refs(board, "parentReferences"), PROJECT)
    elif ext == DRAWING:
        children = _refs(active, "childReferences")
        projects = _of_type(children, PROJECT)
        start_boards = [
            b for d in _of_type(children, DESIGN) for b in boards_of_design(d)
        ]
        if not projects and not start_boards:
            return None
        for board in start_boards:
            projects += _of_type(_refs(board, "parentReferences"), PROJECT)
    else:
        return None

    projects = unique_by_id(projects)
    children = [c for p in projects for c in _refs(p, "childReferences")]
    schematics = _of_type(children, SCHEMATIC)
    boards = _of_type(children, BOARD)

    # Whatever the walk could not reach from a project, the active file and
    # its own references still supply.
    if ext == SCHEMATIC:
        schematics = [active] + schematics
    elif ext == BOARD:
        boards = [active] + boards
    elif ext in (DESIGN, DRAWING):
        boards = boards + start_boards
    boards = unique_by_id(boards)

    pcb3ds = [d for b in boards for d in _of_type(_refs(b, "childReferences"), DESIGN)]
    if ext == DESIGN:
        pcb3ds = [active] + pcb3ds
    pcb3ds = unique_by_id(pcb3ds)

    # Drawings hang off the project (as observed) or the 3D PCB.
    drawings = [
        d
        for f in projects + pcb3ds
        for d in _of_type(_refs(f, "parentReferences"), DRAWING)
    ]
    if ext == DRAWING:
        drawings = [active] + drawings

    return ElectronicsSet(
        projects=projects,
        schematics=unique_by_id(schematics),
        boards=boards,
        pcb3ds=pcb3ds,
        drawings=unique_by_id(drawings),
    )
