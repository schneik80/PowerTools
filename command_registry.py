# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.
#
# Declarative command registry — the single source of truth for command grouping,
# documentation filenames, the beta tier, and which commands expose a settings
# section in the Preferences palette. Kept at the add-in root (not under
# commands/) and free of any `adsk` import so the settings store can import it
# without triggering commands/__init__ or a Fusion runtime.
#
# `commands/__init__.py` derives its imports, start/stop order, and start-up
# gating from this registry; the Preferences command renders its tree from it.
# `module` is the on-disk command folder name (also the stable settings key).
# `doc` is the exact filename under docs/ (note these are NOT always CMD_NAME,
# e.g. module `sketchfix` -> `SketchFix.md`).


def _cmd(module, doc, beta=False, settings=False):
    return {"module": module, "doc": doc, "beta": beta, "has_settings": settings}


GROUPS = [
    {
        "key": "assembly",
        "label": "Assembly",
        "commands": [
            _cmd("assemblybuilder", "Assembly Builder.md"),
            _cmd("insertSTEP", "Insert Step.md"),
            _cmd("assemblyintent", "New Assembly.md"),
            _cmd("assemblystats", "Assembly Statistics.md"),
            _cmd("getandupdate", "Get and Update.md"),
            _cmd("bottomupupdate", "Bottom-Up Update.md"),
            _cmd("componentwarn", "Component Warning.md", settings=True),
            _cmd("changecyclecolor", "Change Cycle Color.md", settings=True),
            _cmd("externalize", "Externalize.md"),
            _cmd("globalParameters", "Global Parameters.md"),
            _cmd("inferconstraints", "Infer Constraints.md", beta=True),
            _cmd("linkGlobalParameters", "Link Global Parameters.md"),
            _cmd("refmanager", "Reference Manager.md"),
            _cmd("refreshGlobalParametersCache", "Refresh Global Parameters Cache.md"),
            _cmd("refrences", "Document References.md"),
            _cmd("refresh", "Document Refresh.md"),
        ],
    },
    {
        "key": "document",
        "label": "Document Tools",
        "commands": [
            _cmd("assigndrawingnumber", "Assign Drawing Number.md"),
            _cmd("assignpartnumbers", "Assign Part Numbers.md"),
            _cmd("autosave", "Recovery Save.md"),
            _cmd("datatoggle", "Toggle Data Pane.md"),
            _cmd("defaultfolders", "Default Folders.md", settings=True),
            _cmd("dochistory", "Document History.md"),
            _cmd("docinfo", "Document Information.md"),
            _cmd("docopen", "Show In Location.md", settings=True),
            _cmd("favorites", "Favorites.md"),
            _cmd("openrecent", "Open Recent.md"),
            _cmd("versiondiff", "Version Diff.md"),
        ],
    },
    {
        "key": "exports",
        "label": "Exports",
        "commands": [
            _cmd("exportbomcsv", "Export BOM.md"),
            _cmd("exportmermaid", "Export Mermaid.md"),
        ],
    },
    {
        "key": "partmodeling",
        "label": "Part Modeling",
        "commands": [
            _cmd("sketchfix", "SketchFix.md"),
            _cmd("roundsketchdimensions", "Round Sketch Dimensions.md"),
            _cmd("sketchunderconstrained", "SketchUnder.md"),
            _cmd("sketchcirclecenterpoint", "RadialHoleCircle.md", beta=True),
            _cmd("timelinecompute", "Timeline Compute Times.md"),
            _cmd("mirrorderive", "MirrorDerive.md"),
            _cmd("hideobjects", "HideObjects.md"),
        ],
    },
    {
        "key": "related",
        "label": "Related Data",
        # The Related Data group owns the "Hub Settings" preferences section
        # (see commands/preferences); that section is shown when this group is
        # enabled.
        "commands": [
            _cmd("confighub", "Select Related Data Folder.md"),
            _cmd("relateddata", "Related Data.md"),
        ],
    },
    {
        "key": "tools",
        "label": "Tools",
        # Launcher commands that open built-in Fusion tools. "Scripts and
        # Add-ins" sits directly before PowerTools Preferences in the QAT File
        # dropdown (see commands/scriptsmanager).
        "commands": [
            _cmd("scriptsmanager", "Scripts and Add-ins.md"),
        ],
    },
    {
        "key": "share",
        "label": "Share Document",
        "commands": [
            _cmd("shareDocument", "Get a Share Link.md"),
            _cmd("shareSettings", "Change Share Settings.md"),
            _cmd("OpenDesktop", "Get Open on Desktop Link.md"),
            _cmd("OpenInTeam", "Get Open in Team Link.md"),
            _cmd("projectInvite", "Invite to Project.md"),
            _cmd("projectMembers", "Document Project Members.md"),
        ],
    },
]


def iter_commands():
    """Yield (group, command) for every registered command, in start order."""
    for group in GROUPS:
        for cmd in group["commands"]:
            yield group, cmd


def group_keys():
    return [g["key"] for g in GROUPS]


def command_keys():
    return [c["module"] for _, c in iter_commands()]
