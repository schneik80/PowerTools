"""Unit tests for ``commands/_command_abort.py`` and a repo-wide crash guard.

Calling ``args.command.doExecute()`` from a ``command_created`` handler
hard-crashes Fusion: that callback runs inside
``CommandDefinition::createCommand``, so doExecute re-enters the command manager
on a half-constructed command. Observed 2026-09-02 by running Change Cycle Color
with nothing selected, faulting inside
``Xl::APICommandDefinitionImpl::doOnCreateCommand``.

Seven commands did this. The fix is to build no inputs and let
``Command.isAutoExecute`` (default true) end the command — which means
``command_execute`` still fires, on stale module state, hence the one-shot
abort flag these tests cover.

``test_no_command_created_calls_do_execute`` is the important one: it is a
static guard over the whole tree, so reintroducing the crash anywhere fails CI
rather than waiting for a user to find it.
"""

import ast
import importlib
import pathlib

import pytest

abort = importlib.import_module("PowerTools.commands._command_abort")

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

CMD_A = "PTAT_commandA"
CMD_B = "PTAT_commandB"


@pytest.fixture(autouse=True)
def clear_flags():
    """The flag set is module-level state shared by every command."""
    abort._aborted.clear()
    yield
    abort._aborted.clear()


# ── flag lifecycle ───────────────────────────────────────────────────────────
def test_consume_returns_false_when_nothing_aborted() -> None:
    """A normal invocation must not be mistaken for an aborted one, or the
    command would silently refuse to do its work."""
    assert abort.consume_abort(CMD_A, "Command A") is False


def test_abort_then_consume_reports_the_abort() -> None:
    """The signal command_execute relies on to skip its work."""
    abort.abort_before_dialog(CMD_A, "Command A", "no selection")
    assert abort.consume_abort(CMD_A, "Command A") is True


def test_consume_is_one_shot() -> None:
    """Leaving the flag set would break the *next*, legitimate invocation --
    the command would come up and then quietly do nothing."""
    abort.abort_before_dialog(CMD_A, "Command A", "no selection")
    assert abort.consume_abort(CMD_A, "Command A") is True
    assert abort.consume_abort(CMD_A, "Command A") is False


def test_flags_are_keyed_per_command() -> None:
    """Commands share the module, so one command's abort must not cancel
    another command's real invocation."""
    abort.abort_before_dialog(CMD_A, "Command A", "no selection")
    assert abort.consume_abort(CMD_B, "Command B") is False
    assert abort.consume_abort(CMD_A, "Command A") is True


def test_was_aborted_does_not_consume() -> None:
    """The non-consuming check is for handlers other than command_execute,
    which must not steal the flag from it."""
    abort.abort_before_dialog(CMD_A, "Command A", "no selection")
    assert abort.was_aborted(CMD_A) is True
    assert abort.was_aborted(CMD_A) is True
    assert abort.consume_abort(CMD_A, "Command A") is True


def test_repeated_aborts_still_consume_once() -> None:
    """Two failing preconditions in one pass must not need two consumes."""
    abort.abort_before_dialog(CMD_A, "Command A", "first reason")
    abort.abort_before_dialog(CMD_A, "Command A", "second reason")
    assert abort.consume_abort(CMD_A, "Command A") is True
    assert abort.consume_abort(CMD_A, "Command A") is False


# ── repo-wide static guard ───────────────────────────────────────────────────
def _do_execute_calls_in(path: pathlib.Path):
    """Yield (line, enclosing function name) for each doExecute call."""
    tree = ast.parse(path.read_text())
    funcs = [
        n
        for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "doExecute"
        ):
            continue
        owner = None
        for fu in funcs:
            if fu.lineno <= node.lineno <= (fu.end_lineno or fu.lineno):
                if owner is None or fu.lineno > owner.lineno:
                    owner = fu
        yield node.lineno, (owner.name if owner else "<module>")


def _command_sources():
    return [
        p
        for p in sorted((REPO_ROOT / "commands").rglob("*.py"))
        if "__pycache__" not in str(p)
    ]


def test_no_command_created_calls_do_execute() -> None:
    """No command may dismiss itself from command_created with doExecute.

    Use ``_command_abort.abort_before_dialog`` and return without adding
    inputs instead; see that module for why doExecute segfaults Fusion here.
    """
    offenders = [
        f"{path.relative_to(REPO_ROOT)}:{line}"
        for path in _command_sources()
        for line, owner in _do_execute_calls_in(path)
        if owner == "command_created"
    ]
    assert not offenders, "doExecute inside command_created: " + ", ".join(offenders)


def test_the_guard_can_actually_see_do_execute_calls() -> None:
    """Guard against the guard silently passing because the AST walk broke:
    the legitimate call sites outside command_created must still be found."""
    found = {
        (str(path.relative_to(REPO_ROOT)), owner)
        for path in _command_sources()
        for _, owner in _do_execute_calls_in(path)
    }
    assert (
        "commands/changecyclecolor/entry.py",
        "_enter_custom_color_flow",
    ) in found


if __name__ == "__main__":
    for _name in sorted(n for n in dir() if n.startswith("test_")):
        globals()[_name]()
        print(f"PASS {_name}")
    print("ALL TEST FUNCS PASSED")
