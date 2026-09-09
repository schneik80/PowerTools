# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.
"""Export SysML Architecture Document.

Writes the active design as an Architecture Design Document organised on the
4+1 View Model, with the Physical View generated in SysML v2 textual notation.
Two files land in a folder the user picks: the document and the model.

All Fusion contact is in this module. The assembly is flattened into the plain
records in ``model.py`` and both output formats are produced by ``render.py``,
neither of which imports ``adsk`` -- so quantities, classification, escaping and
unit conversion are all unit tested outside Fusion.

The whole command runs in ``command_created`` and builds no command inputs.
``execute`` never fires when no document is open, so a QAT File-menu command
that did its work there would silently do nothing -- which is the latent bug in
``exportbomcsv`` and ``exportmermaid``, whose "A Design Must be Active." message
is unreachable in exactly the case it exists for (f18b911, 11cfc51).

Because there are no inputs, Fusion auto-executes and terminates the command by
itself; registering no execute handler makes that a no-op, which is why the
``_command_abort`` flag machinery is not needed here. **Adding an execute
handler later would reintroduce that bug**, and the AST guard in
``tests/test_command_abort.py`` would not catch it because it only inspects
``command_created``; ``tests/test_exportsysml_entry.py`` guards it instead.

Joints are read per component from ``Component.joints`` / ``asBuiltJoints``
rather than from ``rootComponent.allJoints``. ``allJoints`` returns proxies "in
the context of" the root, whose ends are proxy occurrences that do not
correspond to the native children recorded while walking, and a connection is
emitted inside the owning component's definition -- so the native, per-component
collections are the ones whose ends can actually be named.
"""

from __future__ import annotations

import datetime
import os
from dataclasses import replace

import adsk.core
import adsk.fusion

from ...lib import ptAddInUtils as ptutil
from . import model, render

app = adsk.core.Application.get()
ui = app.userInterface

CMD_NAME = "Export SysML Architecture Document..."
CMD_ID = "PTE_exportsysml"
CMD_Description = (
    "Export the active assembly as a 4+1 architecture design document "
    "with a SysML physical view"
)
# Only show a progress dialog once the assembly is big enough for the physical
# property reads to be noticeable. Below this a dialog that flashes up and
# vanishes is worse than none.
PROGRESS_THRESHOLD = 25

# Suffixes appended to the sanitised document name.
ADD_SUFFIX = "-ADD.md"
SYSML_SUFFIX = "-physical.sysml"

_JOINT_TYPE_NAMES = {
    adsk.fusion.JointTypes.RigidJointType: "Rigid",
    adsk.fusion.JointTypes.RevoluteJointType: "Revolute",
    adsk.fusion.JointTypes.SliderJointType: "Slider",
    adsk.fusion.JointTypes.CylindricalJointType: "Cylindrical",
    adsk.fusion.JointTypes.PinSlotJointType: "PinSlot",
    adsk.fusion.JointTypes.PlanarJointType: "Planar",
    adsk.fusion.JointTypes.BallJointType: "Ball",
    adsk.fusion.JointTypes.InferredJointType: "Inferred",
}

_DESIGN_TYPE_NAMES = {
    adsk.fusion.DesignTypes.DirectDesignType: "Direct",
    adsk.fusion.DesignTypes.ParametricDesignType: "Parametric",
}


# Executed when add-in is run.
def start():
    cmd_def = ui.commandDefinitions.itemById(CMD_ID)
    if cmd_def is None:
        cmd_def = ui.commandDefinitions.addButtonDefinition(
            CMD_ID, CMD_NAME, CMD_Description
        )
    ptutil.add_handler(cmd_def.commandCreated, command_created)

    # Sits with the other two exports, immediately before Fusion's own Export.
    # The third argument is isBefore, not a separator flag: the siblings pass
    # True and therefore land *before* ExportCommand, despite their comment.
    file_dd = ptutil.get_qat_file_dropdown()
    if file_dd and file_dd.controls.itemById(CMD_ID) is None:
        file_dd.controls.addCommand(cmd_def, "ExportCommand", True)


# Executed when add-in is stopped.
def stop():
    ptutil.remove_from_qat_file_dropdown(CMD_ID)
    command_definition = ui.commandDefinitions.itemById(CMD_ID)
    if command_definition:
        command_definition.deleteMe()


# Function that is called when a user clicks the corresponding button in the UI.
# The whole command runs here; see the module docstring for why there is no
# execute handler to defer the work to.
def command_created(args: adsk.core.CommandCreatedEventArgs):
    ptutil.log(f"{CMD_NAME} Command Event")
    try:
        _export()
    except Exception:
        ptutil.handle_error(CMD_NAME, show_message_box=True)


def _read(getter, default=None):
    """Call *getter*, returning *default* if Fusion refuses.

    Every property on a component, occurrence or joint is read through here. A
    handle can be stale, a property can be unsupported on the current design
    type, and a physical-property evaluation can simply fail -- and a partial
    document that says which values are missing beats an aborted export.
    """
    try:
        return getter()
    except Exception:
        return default


def _export():
    """Validate, ask for a destination, scan the assembly, write both files."""
    design = adsk.fusion.Design.cast(app.activeProduct)
    if not design:
        ui.messageBox(
            "A Fusion design must be active to export an architecture document.",
            CMD_NAME,
            0,
            2,
        )
        return

    root = design.rootComponent
    if _read(lambda: root.occurrences.count, 0) < 1:
        ui.messageBox(
            "This design has no child components.\n\n"
            "The Physical View documents how an assembly is composed, so open an "
            "assembly or a hybrid design and try again.",
            CMD_NAME,
            0,
            2,
        )
        ptutil.log(f"{CMD_NAME}: refused -- root component has no occurrences")
        return

    document_name = _read(lambda: design.parentDocument.name) or "Untitled"

    # The folder is chosen before the scan: a cancelled dialog should cost the
    # user nothing, and the physical-property reads are the slow part.
    folder_dlg = ui.createFolderDialog()
    folder_dlg.title = "Choose a folder for the architecture document"
    if folder_dlg.showDialog() != adsk.core.DialogResults.DialogOK:
        return
    folder = folder_dlg.folder

    assembly = _scan(design, root, document_name)
    if assembly is None:
        return

    stem = render.safe_filename(os.path.basename(document_name))
    sysml_name = stem + SYSML_SUFFIX
    add_path = os.path.join(folder, stem + ADD_SUFFIX)
    sysml_path = os.path.join(folder, sysml_name)

    # newline="\n" and an explicit encoding: the siblings omit both, which makes
    # a non-ASCII component name raise on Windows and turns every line ending in
    # a .sysml file into CRLF there.
    for path, text in (
        (sysml_path, render.sysml_document(assembly)),
        (add_path, render.add_document(assembly, sysml_name)),
    ):
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        ptutil.log(f"{CMD_NAME}: wrote {path}")

    ui.messageBox(
        "Architecture document exported.\n\n"
        f"Document: {os.path.basename(add_path)}\n"
        f"SysML model: {sysml_name}\n\n"
        f"Folder: {folder}",
        document_name,
        0,
        2,
    )


class _Scan:
    """One pass over the assembly, turning Fusion objects into plain records.

    The walk is over the unique-component graph rather than the occurrence tree,
    so a component used two hundred times is expanded once and its physical
    properties are evaluated once. Repeat visits are skipped, which is also what
    makes a component that somehow contains itself terminate.
    """

    def __init__(self, progress):
        self.progress = progress
        self.nodes: dict = {}
        self.notes: list = []
        self.joints: list = []
        self.references: dict = {}
        self.cancelled = False
        self._fallback_keys = 0
        # Referenced occurrences whose document could not be named.
        self._unidentified_refs: set = set()
        # Component ids seen, to the names carrying them. Fusion's persistent id
        # is not always unique (see key_for), and the collision is worth telling
        # the reader about rather than absorbing.
        self._id_names: dict = {}
        self._noted_ids: set = set()

    def note(self, text: str) -> None:
        """Record something that could not be read, for the document appendix."""
        self.notes.append(text)
        ptutil.log(f"{CMD_NAME}: {text}")

    def key_for(self, component, occurrence) -> str:
        """A stable identity for *component*, for use as a dictionary key.

        ``Component.id`` is the persistent id: it is created with the component
        and does not change. ``entityToken`` is deliberately not used -- its own
        API documentation warns that the token for one entity can differ between
        reads and must never be compared, which as a dict key would emit the same
        component twice and re-evaluate its properties per instance.

        ``id`` is documented as unique within a single design but possibly not
        across externally referenced designs that are different revisions or
        copies of one another, so a referenced component's key also carries its
        source document and version.

        That suffix is not sufficient on its own, and the name completes the key.
        A component created by copying another inside a referenced document
        carries the original's ``id``: a real hub assembly has "CVD Pivot Pin"
        and "CVD Drive Pin" sharing one ``id`` and differing only in
        ``revisionId``. The suffix cannot separate them, because both come from
        the same document at the same version -- and for an occurrence nested
        inside a referenced subassembly ``documentReference`` raises "Cannot get
        allDocumentReferences of a non-top-level document", so the suffix is
        empty anyway. Keying on the id alone dropped the second component from
        the model entirely and attached its joint to the first.

        ``revisionId`` would also separate them, but it changes every time the
        component is modified, so as a key it would make the export differ
        between runs over an unchanged structure. The name is stable, and the
        two together are unique.
        """
        component_id = _read(lambda: component.id) or ""
        if not component_id:
            self._fallback_keys += 1
            name = _read(lambda: component.name) or f"component {self._fallback_keys}"
            self.note(
                f"component {name!r} reported no persistent id; identified by name, "
                "so two same-named components may be merged"
            )
            return f"name:{name}"
        name = _read(lambda: component.name) or ""
        base = component_id + self._reference_suffix(occurrence)
        names = self._id_names.setdefault(base, set())
        names.add(name)
        if len(names) > 1 and base not in self._noted_ids:
            self._noted_ids.add(base)
            listed = ", ".join(repr(each) for each in sorted(names))
            self.note(
                f"components {listed} share one persistent id; they are kept "
                "apart by name, so a rename in the source design would merge them"
            )
        return f"{base}|{name}"

    def _reference_suffix(self, occurrence) -> str:
        """Source document and version for a referenced component, else ``""``."""
        if occurrence is None:
            return ""
        if not _read(lambda: occurrence.isReferencedComponent, False):
            return ""
        reference = _read(lambda: occurrence.documentReference)
        if reference is None:
            return ""
        data_file = _read(lambda: reference.dataFile)
        file_id = _read(lambda: data_file.id) if data_file is not None else ""
        version = _read(lambda: reference.version)
        return f"@{file_id or ''}:{'' if version is None else version}"

    def _tick(self, label: str) -> bool:
        """Advance the progress dialog. False when the user cancelled."""
        if self.progress is None:
            return True
        if _read(lambda: self.progress.wasCancelled, False):
            self.cancelled = True
            return False
        self.progress.progressValue = self.progress.progressValue + 1
        return True

    def _occurrences(self, component, label) -> list:
        """Direct child occurrences of *component*, skipping unreadable ones."""
        collection = _read(lambda: component.occurrences)
        if collection is None:
            self.note(f"{label}: child components could not be read")
            return []
        items = []
        for index in range(_read(lambda: collection.count, 0) or 0):
            occurrence = _read(lambda i=index: collection.item(i))
            if occurrence is None:
                self.note(f"{label}: child {index + 1} could not be read")
                continue
            items.append(occurrence)
        return items

    def _physical(self, component, label):
        """Mass, volume, area and centre of mass, as a tuple of optionals.

        ``LowCalculationAccuracy`` is Fusion's own default and is documented as
        within +/- 1%, which is the right trade for a structural document: the
        higher settings cost real time on a large assembly and change nothing a
        reader of this document would decide differently.
        """
        properties = _read(
            lambda: component.getPhysicalProperties(
                adsk.fusion.CalculationAccuracy.LowCalculationAccuracy
            )
        )
        if properties is None:
            self.note(f"{label}: physical properties could not be evaluated")
            return None, None, None, None
        mass = _read(lambda: properties.mass)
        volume = _read(lambda: properties.volume)
        area = _read(lambda: properties.area)
        centre = _read(lambda: properties.centerOfMass)
        centre_tuple = None
        if centre is not None:
            coords = [_read(lambda a=axis: getattr(centre, a)) for axis in "xyz"]
            if all(value is not None for value in coords):
                centre_tuple = tuple(coords)
        return mass, volume, area, centre_tuple

    def _bounds(self, component, label):
        """Bounding-box corners in centimetres, or ``(None, None)``."""
        box = _read(lambda: component.boundingBox)
        if box is None:
            self.note(f"{label}: bounding box is unavailable or empty")
            return None, None
        corners = []
        for name in ("minPoint", "maxPoint"):
            point = _read(lambda n=name: getattr(box, n))
            if point is None:
                return None, None
            coords = [_read(lambda a=axis, pt=point: getattr(pt, a)) for axis in "xyz"]
            if any(value is None for value in coords):
                return None, None
            corners.append(tuple(coords))
        return corners[0], corners[1]

    def _joint_end(self, occurrence):
        """``(component key, label)`` for one end of a joint."""
        if occurrence is None:
            return None, ""
        label = _read(lambda: occurrence.name) or ""
        component = _read(lambda: occurrence.component)
        if component is None:
            return None, label
        return self.key_for(component, occurrence), label

    def _joints(self, component, owner_key, label) -> None:
        """Collect this component's own joints and as-built joints."""
        for attribute, as_built in (("joints", False), ("asBuiltJoints", True)):
            collection = _read(lambda a=attribute: getattr(component, a))
            if collection is None:
                self.note(f"{label}: {attribute} could not be read")
                continue
            for index in range(_read(lambda c=collection: c.count, 0) or 0):
                joint = _read(lambda i=index, c=collection: c.item(i))
                if joint is None:
                    continue
                self.joints.append(self._joint_edge(joint, owner_key, as_built, label))

    def _joint_edge(self, joint, owner_key, as_built, label):
        """One :class:`model.JointEdge` from a live joint."""
        name = _read(lambda: joint.name) or "Joint"
        motion = _read(lambda: joint.jointMotion)
        joint_type = "Rigid" if as_built else "Unknown"
        if motion is not None:
            joint_type = _JOINT_TYPE_NAMES.get(
                _read(lambda: motion.jointType), joint_type
            )
        one_key, one_label = self._joint_end(_read(lambda: joint.occurrenceOne))
        two_key, two_label = self._joint_end(_read(lambda: joint.occurrenceTwo))
        if one_key is None or two_key is None:
            self.note(
                f"{label}: joint {name!r} has an end that belongs to no occurrence, "
                "so it is reported but not modelled as a connection"
            )
        return model.JointEdge(
            name=name,
            joint_type=joint_type,
            owner_key=owner_key,
            one_key=one_key,
            two_key=two_key,
            one_label=one_label,
            two_label=two_label,
            is_as_built=as_built,
            is_suppressed=self._is_suppressed(joint, name, label),
            origin_cm=self._joint_origin(joint, as_built),
            axis=self._joint_axis(motion, joint_type),
            axis_role=self._axis_role(joint_type),
        )

    def _is_suppressed(self, joint, name, label) -> bool:
        """True when *joint* is not part of the built configuration.

        Two independent signals, because Fusion has two. ``Joint.isSuppressed``
        is the joint's own flag, and ``TimelineObject.isSuppressed`` is the
        feature's -- suppressing a joint from the browser sets the second and
        leaves the first alone. Reading only the first published a suppressed
        joint as a live connection: a Rear Hub export emitted
        ``connection 'Rigid 10' ... connect iso7380M3X12 to c6MmBallNut`` for a
        joint the design had switched off, and the only visible sign was that
        the joint's origin had moved to where the screw sits unjointed.

        Either signal is enough. Asserting an interface the design denies is
        the worse error, and a joint suppressed by either route is equally not
        built.
        """
        if bool(_read(lambda: joint.isSuppressed, False)):
            return True
        timeline_object = _read(lambda: joint.timelineObject)
        if timeline_object is None:
            return False
        if bool(_read(lambda t=timeline_object: t.isSuppressed, False)):
            self.note(
                f"{label}: joint {name!r} is suppressed in the timeline though "
                "the joint itself does not report it; treated as suppressed"
            )
            return True
        return False

    def _joint_origin(self, joint, as_built):
        """Where the joint sits, in centimetres, or ``None``.

        A ``Joint`` exposes ``geometryOrOriginOne``/``Two``, which is either a
        ``JointGeometry`` (with an ``origin``) or a ``JointOrigin`` (which wraps
        one). An ``AsBuiltJoint`` has a single ``geometry`` instead. The first
        end that yields a point wins; the second is the fallback, because a
        joint made to root-level geometry can have nothing on one side.
        """
        candidates = []
        if as_built:
            candidates.append(_read(lambda: joint.geometry))
        else:
            candidates.append(_read(lambda: joint.geometryOrOriginOne))
            candidates.append(_read(lambda: joint.geometryOrOriginTwo))
        for candidate in candidates:
            if candidate is None:
                continue
            geometry = adsk.fusion.JointGeometry.cast(candidate)
            if geometry is None:
                origin_object = adsk.fusion.JointOrigin.cast(candidate)
                if origin_object is None:
                    continue
                geometry = _read(lambda o=origin_object: o.geometry)
            if geometry is None:
                continue
            point = _read(lambda g=geometry: g.origin)
            if point is None:
                continue
            coords = [_read(lambda a=axis, p=point: getattr(p, a)) for axis in "xyz"]
            if all(value is not None for value in coords):
                return tuple(coords)
        return None

    def _joint_axis(self, motion, joint_type):
        """The joint's primary axis as a unit vector, or ``None``.

        Which vector to read depends on the kind, and that mapping lives in
        ``model.JOINT_AXIS`` so it is testable; here it is one ``getattr``.
        """
        if motion is None:
            return None
        mapping = model.joint_axis_property(joint_type)
        if mapping is None:
            return None
        vector = _read(lambda: getattr(motion, mapping[0]))
        if vector is None:
            return None
        coords = [_read(lambda a=axis, v=vector: getattr(v, a)) for axis in "xyz"]
        if any(value is None for value in coords):
            return None
        return model.unit_vector(coords)

    def _axis_role(self, joint_type):
        """What this kind's axis governs, or ``""`` when it has none."""
        mapping = model.joint_axis_property(joint_type)
        return mapping[1] if mapping else ""

    def _record_reference(self, occurrence, key) -> None:
        """Note that *key* comes from a linked document, aggregating by document.

        Only occurrences whose document actually resolves are recorded. Fusion
        marks the *contents* of a referenced subassembly as referenced too, but
        ``documentReference`` raises for them -- "Cannot get
        allDocumentReferences of a non-top-level document" -- so all that is
        left is the occurrence name. Listing those would present the eight parts
        inside a linked assembly as eight more linked documents, when they are
        the one document already in the table: a Rear Hub export showed 14 rows
        for 8 real documents. The Development View is meant to be the module
        structure, and a module nobody can name is not one.
        """
        if not _read(lambda: occurrence.isReferencedComponent, False):
            return
        reference = _read(lambda: occurrence.documentReference)
        label = ""
        file_id = ""
        version = None
        out_of_date = None
        if reference is not None:
            data_file = _read(lambda: reference.dataFile)
            if data_file is not None:
                label = _read(lambda: data_file.name) or ""
                file_id = _read(lambda: data_file.id) or ""
            version = _read(lambda: reference.version)
            out_of_date = _read(lambda: reference.isOutOfDate)
        if not (label or file_id):
            self._unidentified_refs.add(
                _read(lambda: occurrence.name) or "(unnamed occurrence)"
            )
            return
        entry = self.references.setdefault(
            file_id or label,
            {
                "label": label,
                "version": version,
                "out_of_date": out_of_date,
                "keys": set(),
            },
        )
        entry["keys"].add(key)

    def visit(self, component, occurrence, depth: int) -> str:
        """Record *component* and everything below it. Returns its key."""
        key = self.key_for(component, occurrence)
        if key in self.nodes or self.cancelled:
            return key

        label = _read(lambda: component.name) or "(unnamed component)"
        if not self._tick(label):
            return key

        bodies = _read(lambda: component.bRepBodies.count, 0) or 0
        mass, volume, area, centre = self._physical(component, label)
        bbox_min, bbox_max = self._bounds(component, label)

        # Inserted before recursing so a component reachable from itself, or one
        # reached twice, is not walked again.
        self.nodes[key] = model.CompNode(
            key=key,
            name=label,
            part_number=_read(lambda: component.partNumber) or "",
            description=_read(lambda: component.description) or "",
            material=_read(lambda: component.material.name) or "",
            is_referenced=bool(
                occurrence is not None
                and _read(lambda: occurrence.isReferencedComponent, False)
            ),
            body_count=bodies,
            children=(),
            mass_kg=mass,
            volume_cm3=volume,
            area_cm2=area,
            center_of_mass_cm=centre,
            bbox_min_cm=bbox_min,
            bbox_max_cm=bbox_max,
        )
        self._joints(component, key, label)

        if depth >= model.MAX_DEPTH:
            self.note(
                f"{label}: nesting reached the export's depth limit of "
                f"{model.MAX_DEPTH}, so its children are not documented"
            )
            return key

        # Multiplicity is counted into a dict as the occurrences are walked, in
        # first-appearance order, so the output follows the Fusion browser and is
        # stable between exports.
        counts: dict = {}
        order: list = []
        for child_occurrence in self._occurrences(component, label):
            child_component = _read(lambda occ=child_occurrence: occ.component)
            if child_component is None:
                self.note(f"{label}: a child occurrence has no component")
                continue
            child_key = self.visit(child_component, child_occurrence, depth + 1)
            if self.cancelled:
                return key
            self._record_reference(child_occurrence, child_key)
            if child_key not in counts:
                counts[child_key] = 0
                order.append(child_key)
            counts[child_key] += 1

        children = tuple(
            model.ChildRef(key=child_key, count=counts[child_key])
            for child_key in order
        )
        # The node was recorded before its children were walked so that cycles
        # terminate, so the children are attached now. The records are frozen,
        # which makes this a replacement rather than a mutation.
        self.nodes[key] = replace(self.nodes[key], children=children)
        return key


def _scan(design, root, document_name):
    """Build the :class:`model.AssemblyModel`, or ``None`` if cancelled."""
    total = _read(lambda: design.allComponents.count, 0) or 0
    progress = None
    if total >= PROGRESS_THRESHOLD:
        progress = ui.createProgressDialog()
        progress.isCancelButtonShown = True
        progress.cancelButtonText = "Cancel"
        progress.isBackgroundTranslucent = False
        # show() reseats the range, so progressValue is set afterwards -- passing
        # a non-zero minimum here is what made Bottom-Up Update unlaunchable.
        progress.show(CMD_NAME, "Reading component %v of %m...", 0, total, 0)
        progress.progressValue = 0

    scan = _Scan(progress)
    try:
        root_key = scan.visit(root, None, 0)
    finally:
        if progress is not None:
            progress.hide()

    if scan.cancelled:
        ptutil.log(f"{CMD_NAME}: cancelled during the scan; nothing was written")
        return None

    # One note for the lot rather than one per occurrence: inside a linked
    # subassembly every part hits this, and a note each would bury the appendix.
    if scan._unidentified_refs:
        names = sorted(scan._unidentified_refs)
        shown = ", ".join(names[:6]) + (", ..." if len(names) > 6 else "")
        scan.note(
            f"{len(names)} occurrence(s) are linked from another document that "
            "could not be named, so they are left out of the Development View; "
            "Fusion refuses documentReference for anything nested inside a "
            f"referenced subassembly. They are: {shown}"
        )

    counts = model.total_counts(
        model.AssemblyModel(
            meta=model.DocMeta(document_name=document_name),
            root_key=root_key,
            nodes=scan.nodes,
        )
    )
    external_refs = tuple(
        model.ExternalRef(
            label=entry["label"],
            version=entry["version"],
            is_out_of_date=entry["out_of_date"],
            instance_count=sum(counts.get(key, 0) for key in entry["keys"]),
        )
        for entry in scan.references.values()
    )

    data_file = _read(lambda: design.parentDocument.dataFile)
    meta = model.DocMeta(
        document_name=document_name,
        design_type=_DESIGN_TYPE_NAMES.get(_read(lambda: design.designType), ""),
        length_units=_read(lambda: design.fusionUnitsManager.defaultLengthUnits) or "",
        exported_at=datetime.datetime.now().replace(microsecond=0).isoformat(),
        version=_read(lambda: data_file.versionNumber) if data_file else None,
    )
    ptutil.log(
        f"{CMD_NAME}: {len(scan.nodes)} unique component(s), "
        f"{len(scan.joints)} joint(s), {len(external_refs)} linked document(s), "
        f"{len(scan.notes)} note(s)"
    )
    return model.AssemblyModel(
        meta=meta,
        root_key=root_key,
        nodes=scan.nodes,
        joints=tuple(scan.joints),
        external_refs=external_refs,
        notes=tuple(scan.notes),
    )
