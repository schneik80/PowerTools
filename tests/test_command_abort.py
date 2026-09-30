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


def test_clear_abort_is_unconditional() -> None:
    """destroy always runs, so clearing there bounds the flag to one invocation."""
    abort.abort_before_dialog(CMD_A, "Command A", "no selection")
    abort.clear_abort(CMD_A)
    assert abort.consume_abort(CMD_A, "Command A") is False


def test_clear_abort_is_safe_when_nothing_was_aborted() -> None:
    """destroy calls it on every teardown, including normal invocations."""
    abort.clear_abort(CMD_A)  # must not raise
    assert abort.was_aborted(CMD_A) is False


def test_clear_abort_only_touches_its_own_command() -> None:
    """One command's teardown must not unblock another's pending abort."""
    abort.abort_before_dialog(CMD_A, "Command A", "no selection")
    abort.clear_abort(CMD_B)
    assert abort.was_aborted(CMD_A) is True


def test_stale_flag_cannot_suppress_the_next_invocation() -> None:
    """The regression clear_abort exists for: an abort whose execute never
    fired would otherwise leave the flag set, and the next legitimate run of
    the command would come up and then silently do nothing."""
    abort.abort_before_dialog(CMD_A, "Command A", "no selection")
    # execute never ran -- only destroy did.
    abort.clear_abort(CMD_A)
    # Next invocation: a real one, which must not be skipped.
    assert abort.consume_abort(CMD_A, "Command A") is False


# ── repo-wide static guard ───────────────────────────────────────────────────
#
# The guarded set is derived from *registration*, not from a function name.
# The first version filtered on ``owner == "command_created"`` and so never saw
# the five commandCreated handlers with other names (``_launch_command_created``
# in assemblypalette, ``_add_favorite_created`` / ``_edit_favorites_created`` in
# favorites, and the ``_created`` closures returned by ``_make_open_handler`` /
# ``_make_navigate_handler`` in openrecent and favorites).


def _parse(path: pathlib.Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _do_execute_calls_in(path: pathlib.Path):
    """Yield (line, enclosing function name) for each doExecute call."""
    tree = _parse(path)
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


def _is_add_handler(call: ast.Call) -> bool:
    """``add_handler(...)`` under any prefix: ``ptutil.add_handler``, bare, etc."""
    func = call.func
    if isinstance(func, ast.Attribute):
        return func.attr == "add_handler"
    return isinstance(func, ast.Name) and func.id == "add_handler"


def _is_command_created_event(expr: ast.AST) -> bool:
    """The first ``add_handler`` argument is ``<anything>.commandCreated``."""
    return isinstance(expr, ast.Attribute) and expr.attr == "commandCreated"


def _command_created_handlers(path: pathlib.Path):
    """Yield every FunctionDef registered as a commandCreated handler in *path*.

    A handler passed by name resolves to the FunctionDef(s) of that name. A
    handler produced by a factory call (``_make_open_handler(...)``) resolves
    to every FunctionDef nested inside that factory, because the closure it
    returns runs inside ``createCommand`` just the same.
    """
    tree = _parse(path)
    funcs = [
        n
        for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    by_name: dict[str, list] = {}
    for fu in funcs:
        by_name.setdefault(fu.name, []).append(fu)

    for call in ast.walk(tree):
        if not (isinstance(call, ast.Call) and _is_add_handler(call)):
            continue
        if len(call.args) < 2 or not _is_command_created_event(call.args[0]):
            continue
        handler = call.args[1]
        if isinstance(handler, ast.Name):
            yield from by_name.get(handler.id, [])
        elif isinstance(handler, ast.Call) and isinstance(handler.func, ast.Name):
            for factory in by_name.get(handler.func.id, []):
                for nested in ast.walk(factory):
                    if nested is not factory and isinstance(
                        nested, (ast.FunctionDef, ast.AsyncFunctionDef)
                    ):
                        yield nested


def _command_sources():
    return [
        p
        for p in sorted((REPO_ROOT / "commands").rglob("*.py"))
        if "__pycache__" not in str(p)
    ]


def _guarded_handlers():
    """(relative path, handler name, first line, last line) for every handler."""
    return {
        (str(path.relative_to(REPO_ROOT)), fu.name, fu.lineno, fu.end_lineno)
        for path in _command_sources()
        for fu in _command_created_handlers(path)
    }


# Every registered command has a commandCreated handler, and favorites has
# three; a walk that finds fewer than this has broken, not found a clean tree.
MIN_GUARDED_HANDLERS = 55


def test_no_command_created_calls_do_execute() -> None:
    """No commandCreated handler may dismiss its command with doExecute.

    Use ``_command_abort.abort_before_dialog`` and return without adding
    inputs instead; see that module for why doExecute segfaults Fusion here.
    The handler set comes from ``add_handler(<x>.commandCreated, <handler>)``
    registrations, so a handler by any name is covered.
    """
    offenders = []
    for path in _command_sources():
        handlers = list(_command_created_handlers(path))
        if not handlers:
            continue
        for line, _owner in _do_execute_calls_in(path):
            if any(
                fu.lineno <= line <= (fu.end_lineno or fu.lineno) for fu in handlers
            ):
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{line}")
    assert not offenders, "doExecute inside a commandCreated handler: " + ", ".join(
        offenders
    )


def test_the_guard_can_actually_see_do_execute_calls() -> None:
    """Guard against the guard silently passing because the AST walk broke:
    the legitimate call sites outside commandCreated must still be found."""
    found = {
        (str(path.relative_to(REPO_ROOT)), owner)
        for path in _command_sources()
        for _, owner in _do_execute_calls_in(path)
    }
    assert (
        "commands/changecyclecolor/entry.py",
        "_enter_custom_color_flow",
    ) in found


def test_the_guard_can_actually_see_command_created_handlers() -> None:
    """Mirror self-check for the registration walk.

    If ``add_handler`` or ``commandCreated`` were renamed, or the factory
    resolution broke, the handler set would collapse and the guard above would
    pass on an empty set. Pin the floor and the five oddly named handlers.
    """
    handlers = _guarded_handlers()
    named = {(path, name) for path, name, _, _ in handlers}

    assert len(handlers) >= MIN_GUARDED_HANDLERS, sorted(named)
    assert ("commands/closealldocuments/entry.py", "command_created") in named
    assert ("commands/assemblypalette/entry.py", "_launch_command_created") in named
    assert ("commands/openrecent/entry.py", "_created") in named
    assert ("commands/favorites/entry.py", "_created") in named
    assert ("commands/favorites/entry.py", "_add_favorite_created") in named
    assert ("commands/favorites/entry.py", "_edit_favorites_created") in named


if __name__ == "__main__":
    for _name in sorted(n for n in dir() if n.startswith("test_")):
        globals()[_name]()
        print(f"PASS {_name}")
    print("ALL TEST FUNCS PASSED")
