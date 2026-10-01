# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.

import os
import re

import adsk.core
import adsk.fusion

from ...lib import ptAddInUtils as ptutil

app = adsk.core.Application.get()
ui = app.userInterface

showversion = True  # show versions in xref component names, default is on
showsubs = False  # show the subassemblies in list, for flat BOM default is off. Children are still displayed this only affects the sub itself

CMD_NAME = "Export BOM as CSV"
CMD_ID = "PTE_exportbom"
CMD_Description = (
    "Write the flat bill of materials of the active assembly to a CSV file."
)
IS_PROMOTED = False

# Local list of event handlers used to maintain a reference so
# they are not released and garbage collected.
local_handlers = []


# Executed when add-in is run.
def start():
    # Create a command Definition.
    cmd_def = ui.commandDefinitions.addButtonDefinition(
        CMD_ID, CMD_NAME, CMD_Description
    )

    # Define an event handler for the command created event. It will be called when the button is clicked.
    ptutil.add_handler(cmd_def.commandCreated, command_created)

    # ******** Add a button into the UI so the user can run the command. ********
    # Get the target workspace the button will be created in.

    qat = ui.toolbars.itemById("QAT")

    # Get the drop-down that contains the file related commands.
    fileDropDown = qat.controls.itemById("FileSubMenuCommand")

    # Add a new button after the Export control.
    fileDropDown.controls.addCommand(cmd_def, "ExportCommand", True)


# Executed when add-in is stopped.
def stop():
    # Get the various UI elements for this command
    qat = ui.toolbars.itemById("QAT")
    fileDropDown = qat.controls.itemById("FileSubMenuCommand")
    command_control = fileDropDown.controls.itemById(CMD_ID)
    command_definition = ui.commandDefinitions.itemById(CMD_ID)

    # Delete the button command control
    if command_control:
        command_control.deleteMe()

    # Delete the command definition
    if command_definition:
        command_definition.deleteMe()


# Function that is called when a user clicks the corresponding button in the UI.
# This defines the contents of the command dialog and connects to the command related events.
def command_created(args: adsk.core.CommandCreatedEventArgs):
    ptutil.add_handler(
        args.command.destroy, command_destroy, local_handlers=local_handlers
    )

    # No inputs, so the work runs here: the control sits in the File dropdown,
    # which exists with no document open, and execute never fires in that
    # state (rule 1, #25). The guard tells the user instead of doing nothing.
    design = ptutil.require_document(CMD_NAME, "design")
    if design is None:
        return
    try:
        _export_bom(design)
    except Exception:
        ptutil.handle_error(CMD_NAME, show_message_box=True)


def _export_bom(design):
    """Write the flat BOM of *design* to a CSV file the user picks.

    The command builds no inputs, so ``showversion`` / ``showsubs`` keep their
    module defaults; the old execute handler read inputs that never existed.
    """
    # Get all occurrences in the rootComp component of the active design
    rootComp = design.rootComponent
    occs = rootComp.allOccurrences

    # Gather information about each unique component, in first-seen order.
    # Rows are keyed on Component.id (the persistent identity exportsysml
    # also uses) so each occurrence costs one dict lookup instead of a
    # rescan of every row, each comparison of which was a native call.
    # childOccurrences.count is likewise read only when a component is
    # first seen; it is a property of the component, not the occurrence.
    bom = []
    rows_by_id = {}
    for occ in occs:
        comp = occ.component
        refocc = occ.isReferencedComponent
        row = rows_by_id.get(comp.id)
        if row is not None:
            # Increment the instance count of the existing row.
            row["instances"] += 1
        else:
            occtype = occ.childOccurrences.count
            # Modify the name if versions are OFF and an occurrence is an xref
            if not showversion and refocc:
                longname = comp.name
                shortname = " v".join(longname.split(" v")[:-1])
            else:
                shortname = comp.name

            mat = ""
            bodies = comp.bRepBodies
            for bodyK in bodies:
                if bodyK.isSolid:
                    mat += bodyK.material.name

            # Add this component to the BOM
            row = {
                "component": comp,
                "name": shortname,
                "pn": comp.partNumber,
                "material": mat,
                "instances": 1,
                "sub": occtype,
            }
            bom.append(row)
            rows_by_id[comp.id] = row

    # collect BOM data
    parentOcc = design.parentDocument.name
    resultString = parentOcc + " BOM\n"
    resultString += "Display Name," + "Part Number," + "Material," + "Count\n"
    resultString += traverseAssembly(bom)

    # Display the BOM in the console
    ptutil.log(resultString)

    # Set styles of file dialog.
    folderDlg = ui.createFolderDialog()
    folderDlg.title = "Choose Folder to save BOM CSV"

    # Show file save dialog
    dlgResult = folderDlg.showDialog()
    if dlgResult == adsk.core.DialogResults.DialogOK:
        safe_name = re.sub(r'[<>:"/\\|?*]', "_", os.path.basename(parentOcc))
        filepath = os.path.join(folderDlg.folder, safe_name + ".csv")
        # Write the results to the file. Fusion's Python on Windows defaults
        # to the ANSI code page, so a name with a character outside it (a
        # diameter sign, say) raised UnicodeEncodeError here; the BOM makes
        # Excel read the file as UTF-8.
        with open(filepath, "w", encoding="utf-8-sig") as f:
            f.write(resultString)
        ui.messageBox("BOM saved at: " + filepath, parentOcc, 0, 2)
        ptutil.log(f"BOM Saved at {filepath}")
    else:
        return


# This function will be called when the user completes the command.
def command_destroy(args: adsk.core.CommandEventArgs):
    global local_handlers
    local_handlers = []
    ptutil.log(f"{CMD_NAME} Command Destroy Event")


def _csv_cell(value) -> str:
    """Neutralize CSV/formula injection for a single cell value.

    Cells whose first character is one a spreadsheet may treat as a formula
    (= + - @) or a control character (tab/CR) are prefixed with a single
    quote so they are imported as literal text. Names, part numbers, and
    materials can flow from shared documents authored by others, so they are
    treated as untrusted.
    """
    text = str(value)
    if text and text[0] in ("=", "+", "-", "@", "\t", "\r"):
        text = "'" + text
    return text


# walk thru the assembly
def traverseAssembly(bom):
    mStr = ""
    if not showsubs:
        for item in bom:
            if item["sub"] < 1:
                mStr += (
                    '"'
                    + _csv_cell(item["name"])
                    + '","'
                    + _csv_cell(item["pn"])
                    + '","'
                    + _csv_cell(item["material"])
                    + '",'
                    + str(item["instances"])
                    + ",EA"
                    + "\n"
                )
        return mStr
    if showsubs:
        for item in bom:
            mStr += (
                '"'
                + _csv_cell(item["name"])
                + '","'
                + _csv_cell(item["pn"])
                + '","'
                + _csv_cell(item["material"])
                + '",'
                + str(item["instances"])
                + ",EA"
                + "\n"
            )
        return mStr
