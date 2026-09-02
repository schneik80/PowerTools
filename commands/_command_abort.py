# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.
#
# Shared "bail out of command_created" helper.
#
# NEVER call ``args.command.doExecute()`` from a ``command_created`` handler.
# That callback runs inside Fusion's ``CommandDefinition::createCommand``, so
# doExecute re-enters the command manager on a half-constructed command and
# hard-crashes Fusion — a segfault with a CER dump, not a Python exception.
# Observed 2026-09-02 running Change Cycle Color with nothing selected, the
# crash stack faulting inside ``Xl::APICommandDefinitionImpl::doOnCreateCommand``
# beneath ``createCommand`` ← ``Nu::CommandMgr::executeCommand``. Both
# ``doExecute(True)`` and ``doExecute(False)`` re-enter the same way.
#
# To abandon a command from ``command_created``, simply build no command inputs
# and return. ``Command.isAutoExecute`` defaults to true, so Fusion executes and
# terminates the command by itself — no re-entrancy, no crash.
#
# The catch that makes this more than a one-line deletion: because Fusion
# auto-executes an input-less command, ``command_execute`` still fires. Command
# state usually lives in module-level globals that outlive one invocation, so an
# unguarded execute can act on the *previous* run's state. In Change Cycle Color
# that silently re-applied the previous run's color to the previous run's
# components. Hence the one-shot flag below: mark the abort on the way out of
# ``command_created``, and consume it at the top of ``command_execute``.
#
# Usage:
#
#     from .._command_abort import abort_before_dialog, consume_abort
#
#     def command_created(args):
#         if not precondition_ok:
#             ui.messageBox("...", CMD_NAME, 0, 2)
#             abort_before_dialog(CMD_ID, CMD_NAME, "precondition failed")
#             return                      # no inputs built -> Fusion ends it
#
#     def command_execute(args):
#         if consume_abort(CMD_ID, CMD_NAME):
#             return
#
# Keyed by command ID so concurrently-registered commands cannot clear each
# other's flag.

from ..lib import ptAddInUtils as ptutil

# Command IDs whose current invocation was abandoned before a dialog was built.
_aborted: set = set()


def abort_before_dialog(cmd_id: str, cmd_name: str, reason: str) -> None:
    """Record that *cmd_id* is giving up in ``command_created``.

    Call this instead of ``args.command.doExecute(...)`` and then return without
    adding any command inputs. See the module comment for why doExecute crashes
    Fusion here.
    """
    _aborted.add(cmd_id)
    ptutil.log(f"{cmd_name}: aborted before building the dialog — {reason}")


def consume_abort(cmd_id: str, cmd_name: str) -> bool:
    """True if *cmd_id* aborted in ``command_created``; clears the flag.

    One-shot on purpose: leaving it set would make the *next*, legitimate
    invocation of the command refuse to do its work.
    """
    if cmd_id not in _aborted:
        return False
    _aborted.discard(cmd_id)
    ptutil.log(f"{cmd_name} execute: skipped (aborted before dialog)")
    return True


def was_aborted(cmd_id: str) -> bool:
    """Non-consuming check, for handlers other than ``command_execute``."""
    return cmd_id in _aborted
