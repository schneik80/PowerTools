# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.

import adsk.core
import adsk.fusion
import os
import traceback
from datetime import datetime

from ...lib import ptAddInUtils as ptutil
from ... import config
from .. import _ui_bootstrap
from .design_properties import extract_design_properties
from .param_fingerprint import extract_feature_params, attach_params_to_features
from .timeline_diff import walk_timeline, get_version_info, compute_diff, save_diff_json
from .timeline_model import DiffResult
from .html_report import generate_html_report

app = adsk.core.Application.get()
ui = app.userInterface

CMD_NAME = "Version Diff"
CMD_ID = "PTND-versiondiff"
CMD_Description = "Compare timeline differences between two versions of the active document"
IS_PROMOTED = True

# Global variables by referencing values from /config.py
WORKSPACE_ID = config.design_workspace
TAB_ID = config.tools_tab_id
TAB_NAME = config.my_tab_name

PANEL_ID = config.my_panel_id
PANEL_NAME = config.my_panel_name
PANEL_AFTER = config.my_panel_after

# Resource location for command icons
ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "")

# Local list of event handlers used to maintain a reference so
# they are not released and garbage collected.
local_handlers = []

# Maps dropdown item labels to DataFile objects for version selection
_version_map = {}


def start():
    """Initialize and register the Version Diff command."""
    cmd_def = ui.commandDefinitions.addButtonDefinition(
        CMD_ID, CMD_NAME, CMD_Description, ICON_FOLDER
    )

    ptutil.add_handler(cmd_def.commandCreated, command_created)

    panel = _ui_bootstrap.get_power_tools_panel()
    if panel:
        control = panel.controls.addCommand(cmd_def)
        control.isPromoted = IS_PROMOTED

    ptutil.log(f"{CMD_NAME} command started successfully")


def stop():
    """Clean up and unregister the Version Diff command."""
    try:
        panel = _ui_bootstrap.get_power_tools_panel()
        command_control = panel.controls.itemById(CMD_ID) if panel else None
        command_definition = ui.commandDefinitions.itemById(CMD_ID)

        if command_control:
            command_control.deleteMe()

        if command_definition:
            command_definition.deleteMe()

        ptutil.log(f"{CMD_NAME} command stopped successfully")

    except Exception as e:
        ptutil.log(f"Error stopping {CMD_NAME}: {e}")


def command_created(args: adsk.core.CommandCreatedEventArgs):
    """Handle command creation: validate document and build the dialog."""
    global _version_map
    _version_map = {}

    ptutil.log(f"{CMD_NAME} Command Created Event")

    try:
        # --- Phase 1: Validation ---

        # Check document is saved
        if not app.activeDocument.isSaved:
            ui.messageBox(
                "The active document must be saved before you can compare versions.",
                "Document Not Saved",
                0, 2,
            )
            args.command.doExecute(True)  # cancel
            return

        # Check active product is a Fusion 3D design
        product = app.activeProduct
        design = adsk.fusion.Design.cast(product)
        if not design:
            ui.messageBox(
                "Version Diff requires an active Fusion 3D design.",
                "No Design Found",
                0, 2,
            )
            args.command.doExecute(True)
            return

        # Check design is parametric (has timeline), not direct modeling
        if design.designType == adsk.fusion.DesignTypes.DirectDesignType:
            ui.messageBox(
                "Version Diff requires a parametric (timeline) design.\n"
                "Direct modeling designs do not have a timeline to compare.",
                "Direct Design Not Supported",
                0, 2,
            )
            args.command.doExecute(True)
            return

        # Check document has more than one version
        data_file = app.activeDocument.dataFile
        versions = data_file.versions
        if versions.count < 2:
            ui.messageBox(
                "This document has only one version.\n"
                "Save at least one more version before comparing.",
                "Insufficient Versions",
                0, 2,
            )
            args.command.doExecute(True)
            return

        # --- Phase 2: Build Dialog ---

        # Show busy indicator in the Fusion status bar while loading version data
        progress = ui.progressBar
        progress.showBusy("Version Diff — Loading version history...")
        adsk.doEvents()

        try:
            cmd = args.command
            inputs = cmd.commandInputs

            # Current version info group
            info_group = inputs.addGroupCommandInput("current_version_info", "Current Version")
            info_group.isEnabledCheckBoxDisplayed = False
            info_group.isExpanded = True

            group_inputs = info_group.children

            # Gather current version metadata
            version_num = data_file.versionNumber
            date_str = ""
            if data_file.dateModified:
                date_str = datetime.fromtimestamp(data_file.dateModified).strftime("%Y-%m-%d %H:%M:%S")
            updated_by = ""
            if data_file.lastUpdatedBy:
                updated_by = data_file.lastUpdatedBy.displayName
            description = data_file.description or "(no description)"

            progress.message = "Version Diff — Reading current version info..."
            adsk.doEvents()

            group_inputs.addTextBoxCommandInput(
                "info_version", "Version",
                f"<b>Version {version_num}</b> of {data_file.latestVersionNumber}",
                1, True,
            )
            group_inputs.addTextBoxCommandInput(
                "info_date", "Date Saved",
                date_str,
                1, True,
            )
            group_inputs.addTextBoxCommandInput(
                "info_user", "Saved By",
                updated_by,
                1, True,
            )
            group_inputs.addTextBoxCommandInput(
                "info_desc", "Description",
                description,
                1, True,
            )

            # --- Version Summary group (collapsed by default) ---
            progress.message = "Version Diff — Gathering version summary..."
            adsk.doEvents()

            summary_group = inputs.addGroupCommandInput("version_summary", "Version Summary")
            summary_group.isEnabledCheckBoxDisplayed = False
            summary_group.isExpanded = False

            sg = summary_group.children

            # Walk all versions to gather stats
            total_versions = versions.count
            unique_users = set()
            earliest_date = None
            latest_date = None
            latest_user = ""
            milestone_count = 0
            latest_is_milestone = False

            for i in range(total_versions):
                ver = versions.item(i)
                if ver.lastUpdatedBy:
                    unique_users.add(ver.lastUpdatedBy.displayName)
                if ver.dateModified:
                    d = ver.dateModified
                    if earliest_date is None or d < earliest_date:
                        earliest_date = d
                    if latest_date is None or d > latest_date:
                        latest_date = d
                        latest_user = ver.lastUpdatedBy.displayName if ver.lastUpdatedBy else ""
                try:
                    if ver.isMilestone:
                        milestone_count += 1
                        if ver.versionNumber == data_file.latestVersionNumber:
                            latest_is_milestone = True
                except Exception:
                    pass

            # Revisions come from the milestones collection.
            # Each Milestone has a name and a linked version.
            # Auto-generated names like "Milestone V7" or "Item Update"
            # are not revisions — real revisions have short labels like "A", "B", "C".
            _auto_milestone_prefixes = ("Milestone ", "Item Update")
            revision_count = 0
            latest_revision_label = ""
            latest_is_revision = False
            try:
                mss = data_file.milestones
                for i in range(mss.count):
                    ms = mss.item(i)
                    ms_name = ms.name or ""
                    is_auto = any(ms_name.startswith(p) for p in _auto_milestone_prefixes)
                    if not is_auto and ms_name:
                        revision_count += 1
                        # Check if this revision is on the latest version
                        try:
                            if ms.version and ms.version.versionNumber == data_file.latestVersionNumber:
                                latest_is_revision = True
                                latest_revision_label = ms_name
                        except Exception:
                            pass
            except Exception:
                pass

            # Public share link
            has_public_link = False
            try:
                shared = getattr(data_file, "sharedLink", None)
                if shared and shared.isShared:
                    has_public_link = True
            except Exception:
                pass

            # Populate summary fields
            sg.addTextBoxCommandInput(
                "sum_versions", "Versions",
                str(total_versions),
                1, True,
            )
            if earliest_date:
                sg.addTextBoxCommandInput(
                    "sum_created", "Created",
                    datetime.fromtimestamp(earliest_date).strftime("%Y-%m-%d %H:%M:%S"),
                    1, True,
                )
            if latest_date:
                sg.addTextBoxCommandInput(
                    "sum_last_saved", "Last Saved",
                    datetime.fromtimestamp(latest_date).strftime("%Y-%m-%d %H:%M:%S"),
                    1, True,
                )
            if latest_user:
                sg.addTextBoxCommandInput(
                    "sum_last_user", "Last Saved By",
                    latest_user,
                    1, True,
                )
            sg.addTextBoxCommandInput(
                "sum_users", "Contributors",
                f"{len(unique_users)} user{'s' if len(unique_users) != 1 else ''}",
                1, True,
            )
            sg.addTextBoxCommandInput(
                "sum_milestones", "Milestones",
                str(milestone_count),
                1, True,
            )
            sg.addTextBoxCommandInput(
                "sum_latest_ms", "Latest Is Milestone",
                "Yes" if latest_is_milestone else "No",
                1, True,
            )
            sg.addTextBoxCommandInput(
                "sum_revisions", "Revisions",
                str(revision_count),
                1, True,
            )
            rev_text = f"Yes — <b>{latest_revision_label}</b>" if latest_is_revision else "No"
            sg.addTextBoxCommandInput(
                "sum_latest_rev", "Latest Is Revision",
                rev_text,
                1, True,
            )
            sg.addTextBoxCommandInput(
                "sum_public", "Public Share Link",
                "Yes" if has_public_link else "No",
                1, True,
            )

            # Comparison version dropdown
            dropdown = inputs.addDropDownCommandInput(
                "compare_version",
                "Compare With Version",
                adsk.core.DropDownStyles.TextListDropDownStyle,
            )

            current_version_num = data_file.versionNumber
            total_versions = versions.count

            progress.message = f"Version Diff — Loading {total_versions} versions..."
            adsk.doEvents()

            # Collect and sort versions by version number descending (newest first)
            version_list = []
            for i in range(total_versions):
                ver = versions.item(i)
                if ver.versionNumber == current_version_num:
                    continue
                version_list.append(ver)

            version_list.sort(key=lambda v: v.versionNumber, reverse=True)

            progress.message = "Version Diff — Building version list..."
            adsk.doEvents()

            is_first = True
            for ver in version_list:
                ver_date = ""
                if ver.dateModified:
                    ver_date = datetime.fromtimestamp(ver.dateModified).strftime("%Y-%m-%d %H:%M")
                ver_user = ""
                if ver.lastUpdatedBy:
                    ver_user = ver.lastUpdatedBy.displayName

                label = f"V{ver.versionNumber} - {ver_date} - {ver_user}"
                dropdown.listItems.add(label, is_first)
                _version_map[label] = ver
                is_first = False

        finally:
            progress.hide()

        # Connect event handlers
        ptutil.add_handler(
            cmd.execute, command_execute, local_handlers=local_handlers
        )
        ptutil.add_handler(
            cmd.inputChanged, on_input_changed, local_handlers=local_handlers
        )
        ptutil.add_handler(
            cmd.destroy, command_destroy, local_handlers=local_handlers
        )

    except Exception as e:
        ptutil.log(f"Error in command_created: {e}\n{traceback.format_exc()}")
        ui.messageBox(f"Failed to initialize Version Diff:\n{str(e)}")


def on_input_changed(args: adsk.core.InputChangedEventArgs):
    """Handle input changes (stub for future use)."""
    pass


def command_execute(args: adsk.core.CommandEventArgs):
    """Execute the version diff: walk timelines, compute diff, generate report."""
    compare_doc = None

    try:
        # Resolve selected comparison version
        cmd_inputs = args.command.commandInputs
        dropdown = cmd_inputs.itemById("compare_version")
        selected_label = dropdown.selectedItem.name
        compare_data_file = _version_map.get(selected_label)

        if not compare_data_file:
            ui.messageBox("Could not resolve the selected version.", CMD_NAME, 0, 3)
            return

        # Walk baseline (current) timeline and extract design properties
        product = app.activeProduct
        design = adsk.fusion.Design.cast(product)
        baseline_features = walk_timeline(design.timeline)
        attach_params_to_features(baseline_features, extract_feature_params(design))
        baseline_info = get_version_info(app.activeDocument.dataFile)
        baseline_properties = extract_design_properties(design)

        ptutil.log(
            f"Baseline: V{baseline_info.version_number}, "
            f"{len(baseline_features)} timeline features"
        )

        # Open comparison version
        ptutil.log(f"Opening comparison version V{compare_data_file.versionNumber}...")
        compare_doc = app.documents.open(compare_data_file, True)

        if not compare_doc:
            ui.messageBox(
                "Failed to open the comparison version.",
                CMD_NAME, 0, 3,
            )
            return

        # Walk comparison timeline
        compare_product = compare_doc.products.itemByProductType("DesignProductType")
        compare_design = adsk.fusion.Design.cast(compare_product)

        if not compare_design:
            ui.messageBox(
                "The comparison version does not contain a valid design.",
                CMD_NAME, 0, 3,
            )
            return

        compare_features = walk_timeline(compare_design.timeline)
        attach_params_to_features(compare_features, extract_feature_params(compare_design))
        compare_info = get_version_info(compare_data_file)
        compare_properties = extract_design_properties(compare_design)

        ptutil.log(
            f"Comparison: V{compare_info.version_number}, "
            f"{len(compare_features)} timeline features"
        )

        # Close comparison document before generating report
        compare_doc.close(False)
        compare_doc = None

        # Compute diff
        diff_entries, aligned_rows, summary = compute_diff(baseline_features, compare_features)

        # Determine chronological order: is comparison older or newer?
        older_is_comparison = compare_info.version_number < baseline_info.version_number

        diff_result = DiffResult(
            baseline=baseline_info,
            comparison=compare_info,
            features=diff_entries,
            aligned_rows=aligned_rows,
            summary=summary,
            older_is_comparison=older_is_comparison,
            baseline_properties=baseline_properties,
            comparison_properties=compare_properties,
        )

        # Save JSON
        json_path = save_diff_json(diff_result)
        ptutil.log(f"Diff JSON saved to: {json_path}")

        # Generate and display HTML report
        html_path = generate_html_report(diff_result)
        ptutil.log(f"HTML report saved to: {html_path}")

        app.executeTextCommand(f"QTWebBrowser.Display file:///{html_path}")

        ptutil.log(
            f"Version Diff complete: "
            f"{summary['newer']} newer, "
            f"{summary['deleted']} deleted, "
            f"{summary['unchanged']} unchanged"
        )

    except Exception as e:
        error_msg = f"Version Diff failed: {str(e)}\n{traceback.format_exc()}"
        ptutil.log(error_msg)
        ui.messageBox(f"Version Diff failed:\n{str(e)}", CMD_NAME, 0, 3)

    finally:
        # Ensure comparison document is closed if still open
        if compare_doc:
            try:
                compare_doc.close(False)
            except:
                pass


def command_destroy(args: adsk.core.CommandEventArgs):
    """Clean up on command destruction."""
    global local_handlers, _version_map
    local_handlers = []
    _version_map = {}
    ptutil.log(f"{CMD_NAME} Command Destroy Event")
