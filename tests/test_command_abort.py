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


# ── early returns after an execute registration ─────────────────────────────
#
# The second half of the crash fix. A commandCreated handler that registers
# ``execute`` and then bails out (``if not design: messageBox(); return``)
# before building any input has told Fusion nothing: ``Command.isAutoExecute``
# fires ``command_execute`` anyway, against the failed precondition -- an
# AttributeError traceback box in Assembly Statistics, a second "No active
# design" box and then a traceback in Bottom-Up Update. Every such return must
# be preceded by ``abort_before_dialog`` so ``consume_abort`` can skip execute.
#
# "Early" is approximated statically: a ``return`` that follows the first
# ``add_handler(<x>.execute, ...)`` and precedes the first call that builds or
# reads a command input (``add*Input``, ``addCommandInput``,
# ``commandInputs.itemById``). A return *before* the execute registration is
# fine (relateddata registers its handlers after its inputs), and so is a
# return after the dialog exists.


def _own_children(node: ast.AST):
    """Direct children of *node*, not descending into nested function bodies."""
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        yield child


def _own_nodes(fu: ast.AST):
    """Every node in *fu*'s body, excluding nested functions and lambdas."""
    stack = list(fu.body)
    while stack:
        node = stack.pop()
        yield node
        stack.extend(_own_children(node))


def _registers_execute_at(fu: ast.AST):
    """Line of the first ``add_handler(<x>.execute, ...)`` in *fu*, or None."""
    lines = [
        node.lineno
        for node in _own_nodes(fu)
        if isinstance(node, ast.Call)
        and _is_add_handler(node)
        and node.args
        and isinstance(node.args[0], ast.Attribute)
        and node.args[0].attr == "execute"
    ]
    return min(lines) if lines else None


def _is_input_builder(call: ast.Call) -> bool:
    """``inputs.add*Input(...)``, ``addCommandInput`` or ``commandInputs.itemById``."""
    func = call.func
    if not isinstance(func, ast.Attribute):
        return False
    if func.attr.endswith("Input") or func.attr == "addCommandInput":
        return True
    if func.attr == "itemById":
        recv = func.value
        if isinstance(recv, ast.Attribute):
            return recv.attr == "commandInputs"
        return isinstance(recv, ast.Name) and "input" in recv.id.casefold()
    return False


def _first_input_build_line(fu: ast.AST) -> float:
    lines = [
        node.lineno
        for node in _own_nodes(fu)
        if isinstance(node, ast.Call) and _is_input_builder(node)
    ]
    return min(lines) if lines else float("inf")


def _is_abort_call(node: ast.AST) -> bool:
    """``abort_before_dialog(...)`` or a module-local wrapper such as
    changecyclecolor's ``_abort_before_dialog``."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name):
        return func.id.endswith("abort_before_dialog")
    return isinstance(func, ast.Attribute) and func.attr.endswith("abort_before_dialog")


_COMPOUND_BLOCKS = ("body", "orelse", "finalbody")


def _child_blocks(stmt: ast.stmt):
    """The statement lists nested directly inside a compound statement."""
    for field in _COMPOUND_BLOCKS:
        block = getattr(stmt, field, None)
        if isinstance(block, list) and block and isinstance(block[0], ast.stmt):
            yield block
    for group in ("handlers", "cases"):
        for item in getattr(stmt, group, ()) or ():
            body = getattr(item, "body", None)
            if isinstance(body, list):
                yield body


def _unguarded_early_returns(fu: ast.AST) -> list[int]:
    """Lines of ``return`` statements in *fu* that follow its execute
    registration, precede its first input build, and are not preceded by an
    ``abort_before_dialog`` call in their own or an enclosing block.

    Only a *simple* statement counts as the guard: an abort inside a sibling
    ``if`` body has not necessarily run by the time this return does.
    """
    exec_line = _registers_execute_at(fu)
    if exec_line is None:
        return []
    first_input = _first_input_build_line(fu)
    offenders: list[int] = []

    def visit(block, guarded: bool) -> None:
        for stmt in block:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            blocks = list(_child_blocks(stmt))
            if blocks:
                for inner in blocks:
                    visit(inner, guarded)
                continue
            if isinstance(stmt, ast.Return):
                if exec_line < stmt.lineno < first_input and not guarded:
                    offenders.append(stmt.lineno)
            elif any(_is_abort_call(n) for n in ast.walk(stmt)):
                guarded = True

    visit(fu.body, False)
    return offenders


# (relative path, handler name) pairs the tree is allowed to leave unguarded.
# Asserted *equal*, so fixing one means removing it here and a new gap fails
# loudly. Assembly Statistics, Bottom-Up Update and Document References were
# all fixed by the change that added this test (#14), so the set is empty and
# must stay that way.
KNOWN_UNGUARDED_EARLY_RETURNS: set[tuple[str, str]] = set()


def test_early_returns_after_execute_registration_abort_first() -> None:
    """Every commandCreated handler that registers ``execute`` and then returns
    before building an input must call ``abort_before_dialog`` first, or
    ``command_execute`` runs against the failed precondition."""
    found: dict[tuple[str, str], list[int]] = {}
    for path in _command_sources():
        rel = str(path.relative_to(REPO_ROOT))
        for fu in _command_created_handlers(path):
            lines = _unguarded_early_returns(fu)
            if lines:
                found.setdefault((rel, fu.name), []).extend(lines)
    assert set(found) == KNOWN_UNGUARDED_EARLY_RETURNS, (
        "return after add_handler(execute) with no abort_before_dialog: "
        + ", ".join(
            f"{p}:{n}:{sorted(set(ls))}" for (p, n), ls in sorted(found.items())
        )
    )


_EARLY_RETURN_FIXTURE = """
def unguarded(args):
    ptutil.add_handler(args.command.execute, command_execute)
    if not design:
        ui.messageBox("no design", CMD_NAME)
        return
    args.command.commandInputs.addBoolValueInput("x", "X", True)

def guarded(args):
    ptutil.add_handler(args.command.execute, command_execute)
    if not design:
        abort_before_dialog(CMD_ID, CMD_NAME, "no design")
        return
    if not saved:
        _abort_before_dialog("unsaved")
        return
    args.command.commandInputs.addBoolValueInput("x", "X", True)

def sibling_abort_does_not_count(args):
    ptutil.add_handler(args.command.execute, command_execute)
    if not design:
        abort_before_dialog(CMD_ID, CMD_NAME, "no design")
        return
    if not saved:
        return
    inputs.addStringValueInput("s", "S", "")

def enclosing_abort_guards(args):
    ptutil.add_handler(args.command.execute, command_execute)
    abort_before_dialog(CMD_ID, CMD_NAME, "always")
    if not design:
        return

def returns_before_registration(args):
    if not design:
        return
    inputs = args.command.commandInputs
    inputs.addStringValueInput("s", "S", "")
    ptutil.add_handler(args.command.execute, command_execute)

def returns_after_inputs(args):
    ptutil.add_handler(args.command.execute, command_execute)
    inputs = args.command.commandInputs
    inputs.addStringValueInput("s", "S", "")
    if not saved:
        return

def no_execute_handler(args):
    if not design:
        return
"""


def test_the_early_return_guard_can_tell_the_cases_apart() -> None:
    """Self-check for the walk above, on a fixture rather than the tree, so a
    broken analysis cannot pass by finding nothing."""
    tree = ast.parse(_EARLY_RETURN_FIXTURE)
    by_name = {fu.name: fu for fu in tree.body if isinstance(fu, ast.FunctionDef)}
    assert _unguarded_early_returns(by_name["unguarded"]) == [6]
    assert _unguarded_early_returns(by_name["guarded"]) == []
    assert _unguarded_early_returns(by_name["sibling_abort_does_not_count"]) == [25]
    assert _unguarded_early_returns(by_name["enclosing_abort_guards"]) == []
    assert _unguarded_early_returns(by_name["returns_before_registration"]) == []
    assert _unguarded_early_returns(by_name["returns_after_inputs"]) == []
    assert _unguarded_early_returns(by_name["no_execute_handler"]) == []


def test_the_early_return_guard_sees_the_tree() -> None:
    """The analysis must find real execute registrations and real input
    builds in the tree, or the guard above is passing on nothing."""
    with_execute = 0
    with_inputs = 0
    for path in _command_sources():
        for fu in _command_created_handlers(path):
            if _registers_execute_at(fu) is not None:
                with_execute += 1
            if _first_input_build_line(fu) != float("inf"):
                with_inputs += 1
    # 40 and 17 at time of writing; most input-less commands never build one.
    assert with_execute >= 30, with_execute
    assert with_inputs >= 15, with_inputs
    # relateddata registers execute only after its inputs: the walk must place
    # the registration after the first input build, so its precondition
    # returns are never in the "early" window.
    (fu,) = [
        fu
        for fu in _command_created_handlers(REPO_ROOT / "commands/relateddata/entry.py")
        if fu.name == "command_created"
    ]
    assert _registers_execute_at(fu) > _first_input_build_line(fu)


if __name__ == "__main__":
    for _name in sorted(n for n in dir() if n.startswith("test_")):
        globals()[_name]()
        print(f"PASS {_name}")
    print("ALL TEST FUNCS PASSED")
