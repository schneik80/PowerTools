# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2022-2026 IMA LLC
#
# Consolidated command registry. Imports every command module from the six
# merged PowerTools add-ins and starts/stops them around the shared UI
# access-point bootstrap.

from . import _ui_bootstrap
from ..lib import ptAddInUtils as ptutil

# ── Assembly ──────────────────────────────────────────────────────────────────
from .assemblybuilder import entry as assemblybuilder
from .assemblyintent import entry as assemblyintent
from .assemblystats import entry as assemblystats
from .getandupdate import entry as getandupdate
from .bottomupupdate import entry as bottomupupdate
from .componentwarn import entry as componentwarn
from .externalize import entry as externalize
from .globalParameters import entry as globalParameters
from .inferconstraints import entry as inferconstraints
from .insertSTEP import entry as insertSTEP
from .linkGlobalParameters import entry as linkGlobalParameters
from .refmanager import entry as refmanager
from .refreshGlobalParametersCache import entry as refreshGlobalParametersCache
from .refrences import entry as refrences
from .refresh import entry as refresh

# ── Document Tools ────────────────────────────────────────────────────────────
from .assigndrawingnumber import entry as assigndrawingnumber
from .assignpartnumbers import entry as assignpartnumbers
from .autosave import entry as autosave
from .datatoggle import entry as datatoggle
from .defaultfolders import entry as defaultfolders
from .dochistory import entry as dochistory
from .docinfo import entry as docinfo
from .docopen import entry as docopen
from .favorites import entry as favorites
from .versiondiff import entry as versiondiff

# ── Exports ───────────────────────────────────────────────────────────────────
from .exportbomcsv import entry as exportbomcsv
from .exportmermaid import entry as exportmermaid

# ── Part Modeling ─────────────────────────────────────────────────────────────
from .sketchfix import entry as sketchfix
from .sketchunderconstrained import entry as sketchunderconstrained
from .sketchcirclecenterpoint import entry as sketchcirclecenterpoint
from .timelinecompute import entry as timelinecompute
from .mirrorderive import entry as mirrorderive
from .hideobjects import entry as hideobjects

# ── Related Data ──────────────────────────────────────────────────────────────
from .confighub import entry as confighub
from .relateddata import entry as relateddata

# ── Share Document ────────────────────────────────────────────────────────────
from .shareDocument import entry as shareDocument
from .shareSettings import entry as shareSettings
from .OpenDesktop import entry as OpenDesktop
from .OpenInTeam import entry as openInTeam
from .projectInvite import entry as projectInvite
from .projectMembers import entry as projectMembers

# Order matters in a few places:
#   * insertSTEP must start before assemblyintent — the New Assembly launch
#     button positions itself relative to the Insert STEP control.
#   * Share-Document commands keep their original relative order for QATRight
#     flyout positioning.
commands = [
    # Assembly
    assemblybuilder,
    insertSTEP,
    assemblyintent,
    assemblystats,
    getandupdate,
    bottomupupdate,
    componentwarn,
    externalize,
    globalParameters,
    inferconstraints,
    linkGlobalParameters,
    refmanager,
    refreshGlobalParametersCache,
    refrences,
    refresh,
    # Document Tools
    assigndrawingnumber,
    assignpartnumbers,
    autosave,
    datatoggle,
    defaultfolders,
    dochistory,
    docinfo,
    docopen,
    favorites,
    versiondiff,
    # Exports
    exportbomcsv,
    exportmermaid,
    # Part Modeling
    sketchfix,
    sketchunderconstrained,
    sketchcirclecenterpoint,
    timelinecompute,
    mirrorderive,
    hideobjects,
    # Related Data
    confighub,
    relateddata,
    # Share Document
    shareDocument,
    shareSettings,
    OpenDesktop,
    openInTeam,
    projectInvite,
    projectMembers,
]


def start():
    # Create the shared "Power Tools" panel and PTSettings flyout once, before
    # any command registers its controls.
    try:
        _ui_bootstrap.create_shared_access_points()
    except Exception:
        ptutil.handle_error("_ui_bootstrap.create_shared_access_points")

    for command in commands:
        try:
            command.start()
        except Exception:
            ptutil.handle_error(command.__name__)


def stop():
    for command in commands:
        try:
            command.stop()
        except Exception:
            ptutil.handle_error(command.__name__)

    # Remove the shared access points once every command has cleaned up its own
    # controls.
    try:
        _ui_bootstrap.remove_shared_access_points()
    except Exception:
        ptutil.handle_error("_ui_bootstrap.remove_shared_access_points")
