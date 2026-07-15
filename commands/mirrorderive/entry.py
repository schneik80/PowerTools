# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.

import os
from typing import cast

import adsk.core
import adsk.fusion

from ... import config
from ...lib import ptAddInUtils as ptutil

app = adsk.core.Application.get()
ui = app.userInterface

CMD_NAME = "Create Mirrored Design"
CMD_ID = "PTPM_createmirrordesign"
CMD_DESCRIPTION = "Save the active documents bodies as an associative mirror using derive. Names the component after the source plus -Mirror"
IS_PROMOTED = False

WORKSPACE_ID = config.design_workspace
TAB_ID = "SolidTab"
PANEL_ID = "SolidCreatePanel"
DERIVE_CMD_ID = "FusionInsertDeriveCommand"

ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "")

local_handlers = []


def start() -> None:
    try:
        cmd_def = ui.commandDefinitions.addButtonDefinition(
            CMD_ID, CMD_NAME, CMD_DESCRIPTION, ICON_FOLDER
        )
        ptutil.add_handler(cmd_def.commandCreated, command_created)

        solid_tab = ui.allToolbarTabs.itemById(TAB_ID)
        if not solid_tab:
            ptutil.log(f"Warning: Toolbar tab {TAB_ID} not found")
            return

        panel = solid_tab.toolbarPanels.itemById(PANEL_ID)
        if not panel:
            ptutil.log(f"Warning: Panel {PANEL_ID} not found in {TAB_ID}")
            return

        control = panel.controls.addCommand(cmd_def, DERIVE_CMD_ID, False)
        control.isPromoted = IS_PROMOTED

    except Exception as e:
        ptutil.log(f"Error starting {CMD_NAME}: {e}")


def stop() -> None:
    try:
        solid_tab = ui.allToolbarTabs.itemById(TAB_ID)
        if not solid_tab:
            return

        panel = solid_tab.toolbarPanels.itemById(PANEL_ID)
        command_control = panel.controls.itemById(CMD_ID) if panel else None
        command_definition = ui.commandDefinitions.itemById(CMD_ID)

        if command_control:
            command_control.deleteMe()

        if command_definition:
            command_definition.deleteMe()

    except Exception as e:
        ptutil.log(f"Error stopping {CMD_NAME}: {e}")


def command_created(args: adsk.core.CommandCreatedEventArgs) -> None:
    ptutil.log(f"{CMD_NAME} Command Created Event")

    ptutil.add_handler(
        args.command.execute, command_execute, local_handlers=local_handlers
    )
    ptutil.add_handler(
        args.command.destroy, command_destroy, local_handlers=local_handlers
    )


def _validate_source_design() -> tuple[adsk.fusion.Design, adsk.core.DataFile]:
    product = app.activeProduct
    design = adsk.fusion.Design.cast(product)
    if not design:
        raise RuntimeError("No active Fusion design.")

    active_workspace = ui.activeWorkspace
    if not active_workspace or active_workspace.id != WORKSPACE_ID:
        raise RuntimeError("Switch to the Design workspace and try again.")

    active_document = app.activeDocument
    if not active_document:
        raise RuntimeError("No active document.")

    source_data_file = active_document.dataFile
    if not source_data_file:
        raise RuntimeError(
            "Save the current 3D design to Fusion before running this command."
        )

    return design, source_data_file


def _derive_into_new_document(
    source_design: adsk.fusion.Design,
) -> tuple[adsk.core.Document, adsk.fusion.Design]:
    new_document = app.documents.add(
        cast(
            adsk.core.DocumentTypes,
            adsk.core.DocumentTypes.FusionDesignDocumentType,
        )
    )
    target_design = adsk.fusion.Design.cast(app.activeProduct)
    if not target_design:
        raise RuntimeError("Failed to create target design document.")

    root_comp = target_design.rootComponent
    derive_features = root_comp.features.deriveFeatures

    derive_input = derive_features.createInput(source_design)
    source_bodies = _collect_source_bodies(source_design)
    if len(source_bodies) == 0:
        raise RuntimeError("No source bodies found to derive.")

    derive_input.sourceEntities = source_bodies

    derive_features.add(derive_input)

    if _count_bodies_in_root(root_comp) == 0:
        raise RuntimeError("No bodies were derived into the new document.")

    return new_document, target_design


def _collect_source_bodies(source_design: adsk.fusion.Design) -> list[adsk.core.Base]:
    source_entities: list[adsk.core.Base] = []

    all_components = source_design.allComponents
    for component in all_components:
        for body in component.bRepBodies:
            source_entities.append(body)

    return source_entities


def _count_bodies_in_root(root_comp: adsk.fusion.Component) -> int:
    body_count = root_comp.bRepBodies.count
    for occ in root_comp.allOccurrences:
        body_count += occ.bRepBodies.count
    return body_count


def _add_scale_feature(
    scale_features: adsk.fusion.ScaleFeatures,
    entities: adsk.core.ObjectCollection,
    base_point: adsk.fusion.ConstructionPoint,
    scale_value: adsk.core.ValueInput,
) -> adsk.fusion.ScaleFeature:
    scale_input = scale_features.createInput(entities, base_point, scale_value)
    scale_feature = scale_features.add(scale_input)
    if not scale_feature:
        raise RuntimeError("Failed to create scale feature.")

    return scale_feature


def _set_scale_parameter_to_negative_one(
    scale_feature: adsk.fusion.ScaleFeature,
) -> None:
    scale_param = scale_feature.scaleFactor
    if not scale_param:
        raise RuntimeError("Unable to access the scale factor parameter for edit.")

    # Explicit post-create parameter edit using the ModelParameter API.
    if not scale_param.expression == "-1":
        scale_param.expression = "-1"


def _collect_component_bodies(
    component: adsk.fusion.Component,
) -> adsk.core.ObjectCollection:
    entities = adsk.core.ObjectCollection.create()
    for body in component.bRepBodies:
        entities.add(body)
    return entities


def _apply_post_derive_scale(target_design: adsk.fusion.Design) -> None:
    root_comp = target_design.rootComponent
    scale_value = adsk.core.ValueInput.createByReal(1.0)

    did_scale = False
    scaled_component_tokens: set[str] = set()

    components_to_scale: list[adsk.fusion.Component] = [root_comp]
    for occ in root_comp.allOccurrences:
        comp = occ.component
        token = comp.entityToken
        if token in scaled_component_tokens:
            continue
        scaled_component_tokens.add(token)
        components_to_scale.append(comp)

    for component in components_to_scale:
        body_entities = _collect_component_bodies(component)
        if body_entities.count == 0:
            continue

        scale_feature = _add_scale_feature(
            component.features.scaleFeatures,
            body_entities,
            component.originConstructionPoint,
            scale_value,
        )
        _set_scale_parameter_to_negative_one(scale_feature)
        did_scale = True

    if not did_scale:
        raise RuntimeError("No valid derived bodies found to scale.")


def _save_mirror_document(
    new_document: adsk.core.Document,
    source_data_file: adsk.core.DataFile,
    mirror_name: str,
) -> None:
    folder = source_data_file.parentFolder
    if not folder:
        raise RuntimeError("Unable to determine destination folder for mirror design.")

    save_ok = new_document.saveAs(mirror_name, folder, "Mirrored derived design", "")
    if not save_ok:
        raise RuntimeError(f"Save As failed for {mirror_name}.")


def command_execute(args: adsk.core.CommandEventArgs) -> None:
    try:
        source_design, source_data_file = _validate_source_design()

        source_name = app.activeDocument.name
        mirror_name = f"{source_name}-mirror"

        new_document, target_design = _derive_into_new_document(source_design)

        # Create the mirror design file first using the requested naming pattern.
        _save_mirror_document(new_document, source_data_file, mirror_name)

        _apply_post_derive_scale(target_design)

        # Save the post-derive scale operation as the next version of the same file.
        new_document.save(
            "Created scale features at 1 and edited scale parameters to -1"
        )

        ui.messageBox(
            f"Created mirrored design: {mirror_name}",
            CMD_NAME,
            cast(
                adsk.core.MessageBoxButtonTypes,
                adsk.core.MessageBoxButtonTypes.OKButtonType,
            ),
            cast(
                adsk.core.MessageBoxIconTypes,
                adsk.core.MessageBoxIconTypes.InformationIconType,
            ),
        )

    except Exception as e:
        ptutil.handle_error(CMD_NAME)
        ui.messageBox(str(e), CMD_NAME)


def command_destroy(args: adsk.core.CommandEventArgs) -> None:
    global local_handlers
    local_handlers = []
    ptutil.log(f"{CMD_NAME} Command Destroy Event")
