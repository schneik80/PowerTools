# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.

import json
import os

import adsk.core
import adsk.fusion

from ... import config
from ...lib import ptAddInUtils as ptutil

app = adsk.core.Application.get()
ui = app.userInterface

# Active hub ID captured in command_created and reused by all handlers.
_active_hub_id = ""

# Doc name values shared across command handlers.
docSeed = ""
docTitle = ""
docURN = ""

# Template dict for the current hub — populated fresh in command_created.
my_DocsDictSorted = {}

# command identity information.
CMD_ID = f"{config.COMPANY_NAME}_{config.ADDIN_NAME}_cmdDialog"
CMD_NAME = "Create Related Data"
CMD_Description = (
    "Create a new related document of the active document using a template"
)

# Specify that the command will be promoted to the panel.
IS_PROMOTED = True

# Define the tabs and panels where the command button will be created.
WORKSPACE_ID = "FusionSolidEnvironment"

TABS = [
    {
        "TAB_ID": "SolidTab",
        "TAB_NAME": "SOLID",
        "PANEL_ID": "SolidCreatePanel",
        "PANEL_NAME": "Create",
    },
]

# Resource location for command icons, here we assume a sub folder in this directory named "resources".
ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "")

# Local list of event handlers used to maintain a reference so
# they are not released and garbage collected.
local_handlers = []


def _cache_path_for_hub(hub_id: str) -> str:
    """Return the absolute path to the cache file for *hub_id*."""
    return os.path.join(config.CACHE_PATH, f"{hub_id}.json")


def _load_templates_for_hub(hub_id: str) -> dict:
    """Return the template dict for *hub_id*.

    Checks cache/<hub_id>.json first. On a cache miss, fetches live from the
    API, writes the cache file, then returns the result.
    Returns an empty dict and shows a message box on any configuration error.
    """
    # --- cache hit ---
    cache_file = _cache_path_for_hub(hub_id)
    if os.path.isfile(cache_file):
        with open(cache_file) as f:
            cached = json.load(f)
        ptutil.log(f"{CMD_NAME} Templates loaded from cache for hub {hub_id}")
        return cached

    # --- cache miss: fetch from API ---
    hub_cfg = config.COMPANY_HUB_CONFIGS.get(hub_id)
    if not hub_cfg:
        ui.messageBox(
            "No configuration found for this hub.\n"
            "Please run 'Select Related Data Folder' and try again.",
            "Hub Not Configured",
            0,
            3,
        )
        return {}

    project_id = hub_cfg.get("project_id", "")
    folder_id = hub_cfg.get("folder_id", "")

    if not project_id or not folder_id:
        ui.messageBox(
            "The hub configuration is incomplete (missing project or folder ID).\n"
            "Please run 'Select Related Data Folder' again from a document in your templates folder.",
            "Incomplete Hub Config",
            0,
            3,
        )
        return {}

    my_hub = app.data.activeHub
    my_project = my_hub.dataProjects.itemById(project_id)
    if my_project is None:
        ui.messageBox(
            f"Templates project (id: {project_id}) not found.\n"
            "Please reconfigure the hub.",
            "Project Not Found",
            0,
            3,
        )
        return {}

    my_folder = my_project.rootFolder.dataFolders.itemById(folder_id)
    if my_folder is None:
        ui.messageBox(
            f"Templates folder (id: {folder_id}) not found.\n"
            "Please reconfigure the hub.",
            "Folder Not Found",
            0,
            3,
        )
        return {}

    unsorted = {}
    for data_file in my_folder.dataFiles:
        if data_file.fileExtension == "f3d":
            key = data_file.name + "dict"
            unsorted[key] = {"name": data_file.name, "urn": data_file.id}

    sorted_dict = dict(sorted(unsorted.items()))

    # Write cache so subsequent opens skip the API call.
    os.makedirs(config.CACHE_PATH, exist_ok=True)
    with open(cache_file, "w") as f:
        json.dump(sorted_dict, f, indent=2)

    ptutil.log(f"{CMD_NAME} Templates fetched and cached for hub {hub_id}")
    return sorted_dict


# Executed when add-in is run.
def start():
    # Create a command Definition. Reuse an existing one (e.g. after a dev
    # reload where stop() did not run cleanly) instead of failing on a duplicate
    # ID; addButtonDefinition returns None when CMD_ID is already registered.
    cmd_def = ui.commandDefinitions.itemById(CMD_ID)
    if cmd_def is None:
        cmd_def = ui.commandDefinitions.addButtonDefinition(
            CMD_ID, CMD_NAME, CMD_Description, ICON_FOLDER
        )

    # Define an event handler for the command created event. It will be called when the button is clicked.
    ptutil.add_handler(cmd_def.commandCreated, command_created)

    # ******** Add a button into the UI so the user can run the command. ********
    workspace = ui.workspaces.itemById(WORKSPACE_ID)

    # Add the command to each tab/panel.
    for tab_info in TABS:
        toolbar_tab = workspace.toolbarTabs.itemById(tab_info["TAB_ID"])
        if toolbar_tab is None:
            toolbar_tab = workspace.toolbarTabs.add(
                tab_info["TAB_ID"], tab_info["TAB_NAME"]
            )

        panel = toolbar_tab.toolbarPanels.itemById(tab_info["PANEL_ID"])
        if panel is None:
            panel = toolbar_tab.toolbarPanels.add(
                tab_info["PANEL_ID"], tab_info["PANEL_NAME"]
            )

        # Clear any stale controls for this command (persisted ribbon state from
        # a prior version or an unclean reload) so the button never accumulates.
        existing = panel.controls.itemById(CMD_ID)
        while existing is not None:
            existing.deleteMe()
            existing = panel.controls.itemById(CMD_ID)

        control = panel.controls.addCommand(cmd_def)
        control.isPromoted = IS_PROMOTED


# Executed when add-in is stopped.
def stop():
    workspace = ui.workspaces.itemById(WORKSPACE_ID)

    for tab_info in TABS:
        toolbar_tab = workspace.toolbarTabs.itemById(tab_info["TAB_ID"])
        if toolbar_tab:
            panel = toolbar_tab.toolbarPanels.itemById(tab_info["PANEL_ID"])
            if panel:
                # Remove every control for this command, not just the first, in
                # case a duplicate was left behind by a prior session.
                command_control = panel.controls.itemById(CMD_ID)
                while command_control:
                    command_control.deleteMe()
                    command_control = panel.controls.itemById(CMD_ID)

    command_definition = ui.commandDefinitions.itemById(CMD_ID)
    if command_definition:
        command_definition.deleteMe()


# Function that is called when a user clicks the corresponding button in the UI.
# This defines the contents of the command dialog and connects to the command related events.
def command_created(args: adsk.core.CommandCreatedEventArgs):
    # General logging for debug.
    ptutil.log(f"{CMD_NAME} Command Created Event")
    ptutil.log(f"Hub Configured: {config.COMPANY_HUB}")

    # https://help.autodesk.com/view/fusion360/ENU/?contextId=CommandInputs
    inputs = args.command.commandInputs
    global _active_hub_id, docSeed, docURN, my_DocsDictSorted

    # Reload config so any recently-configured hub is visible, then capture hub ID.
    config.reload_hub_config()
    _active_hub_id = app.data.activeHub.id

    if _active_hub_id not in config.COMPANY_HUB:
        ptutil.log(
            f"active hub is {_active_hub_id}.\n{config.COMPANY_HUB} was expected"
        )
        ui.messageBox(
            "The active hub is not configured for this command.\nPlease switch to the correct hub and try again.",
            "Incorrect Hub",
            0,
            3,
        )
        return

    # Load templates for the current hub (cache/<hub_id>.json when available).
    my_DocsDictSorted = _load_templates_for_hub(_active_hub_id)
    if not my_DocsDictSorted:
        # _load_templates_for_hub already showed an error message.
        return

    if not ptutil.isSaved():
        return

    # Define the dialog for command
    dropDownCommandInput = inputs.addDropDownCommandInput(
        "dropDownCommandInput",
        "Type",
        adsk.core.DropDownStyles.LabeledIconDropDownStyle,
    )

    dropDownItems_ = dropDownCommandInput.listItems
    for _key, val in my_DocsDictSorted.items():
        if isinstance(val, dict):
            (dropDownItems_.add(val.get("name"), True),)
            docActive = app.activeDocument
            docWithVersion = docActive.name
            docSeed = docWithVersion.rsplit(" ", 1)[0]  # trim version
            docTitle = docSeed + " ‹+› " + (val.get("name"))
            docURN = val.get("urn")

    boolCommandInput = inputs.addBoolValueInput("boolvalueInput_", "Auto-Name", True)
    boolCommandInput.value = True

    stringDocName = inputs.addStringValueInput("stringValueInput_", "Name", docTitle)
    stringDocName.isEnabled = False

    # Connect to the events
    ptutil.add_handler(
        args.command.execute, command_execute, local_handlers=local_handlers
    )
    ptutil.add_handler(
        args.command.inputChanged, command_input_changed, local_handlers=local_handlers
    )
    ptutil.add_handler(
        args.command.destroy, command_destroy, local_handlers=local_handlers
    )


# This event handler is called when the user clicks the OK button in the command dialog or
# is immediately called after the created event not command inputs were created for the dialog.
def command_execute(args: adsk.core.CommandEventArgs):
    # General logging for debug.
    ptutil.log(f"{CMD_NAME} Command Execute Event")

    # Get a reference to your command's inputs.
    inputs = args.command.commandInputs
    global docURN, docSeed, docTitle

    docActiveUrn = app.data.findFileById(docURN)

    docActive = app.activeDocument
    docWithVersion = docActive.name
    docSeed = docWithVersion.rsplit(" ", 1)[0]  # trim version
    docTitleinput: adsk.core.StringValueCommandInput = inputs.itemById(
        "stringValueInput_"
    )
    docTitle = docTitleinput.value
    docNew = app.documents.open(docActiveUrn)
    docNew.saveAs(
        docTitle,
        docActive.dataFile.parentFolder,
        "Auto created by related data add-in",
        "",
    )
    transform = adsk.core.Matrix3D.create()
    seedDoc = adsk.fusion.Design.cast(
        docNew.products.itemByProductType("DesignProductType")
    )
    seedDoc.rootComponent.occurrences.addByInsert(docActive.dataFile, transform, True)

    docNew.save(
        "Auto saved by related data add-in"
    )  # Save new doc and add boiler plate comment


# This event handler is called when the user changes anything in the command dialog
# allowing you to modify values of other inputs based on that change.
def command_input_changed(args: adsk.core.InputChangedEventArgs):
    changed_input = args.input

    global docURN, docTitle, docSeed
    stringDocname = args.inputs.itemById("stringValueInput_")

    # handle the combobox change event
    if changed_input.id == "dropDownCommandInput":
        searchDict = changed_input.selectedItem.name

        # find the right dictionary based on the combo box value
        listOfKeys = ""
        for i in my_DocsDictSorted.keys():
            for j in my_DocsDictSorted[i].values():
                if searchDict in j:
                    if i not in listOfKeys:
                        listOfKeys = i

        docURN = (my_DocsDictSorted).get(listOfKeys).get("urn")  # set the urn
        doctempname = (my_DocsDictSorted).get(listOfKeys).get("name")
        docTitle = docSeed + " ‹+› " + doctempname
        stringDocname.value = docTitle

    # Auto name or user name input
    if changed_input.id == "boolvalueInput_":
        if changed_input.value:
            stringDocname.isEnabled = False
        else:
            stringDocname.isEnabled = True

    # General logging for debug.
    ptutil.log(
        f"{CMD_NAME} Input Changed Event fired from a change to {changed_input.id}"
    )


# This event handler is called when the command terminates.
def command_destroy(args: adsk.core.CommandEventArgs):
    # General logging for debug.
    ptutil.log(f"{CMD_NAME} Command Destroy Event")

    global local_handlers
    local_handlers = []
