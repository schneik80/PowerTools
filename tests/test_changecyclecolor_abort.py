"""Unit tests for Change Cycle Color's pre-dialog abort path.

Running the command with nothing selected crashed Fusion (2026-09-02): the
early return in ``command_created`` called ``args.command.doExecute(True)``,
and because ``command_created`` runs inside Fusion's
``CommandDefinition::createCommand``, that re-entered the command manager on a
half-constructed command. The crash stack faulted inside
``Xl::APICommandDefinitionImpl::doOnCreateCommand``.

The fix is ``_abort_before_dialog``: build no inputs and let
``Command.isAutoExecute`` (default true) end the command. Fusion then fires
``command_execute`` on a command that never captured any targets, so the abort
also has to neutralize the module-level state that outlives one invocation --
otherwise the auto-execute re-applies the previous run's color to the previous
run's components.

``entry`` is imported via the ``PowerTools.*`` scaffolding in ``conftest.py``,
which fabricates ``adsk`` as mocks.
"""

import importlib

import pytest

entry = importlib.import_module("PowerTools.commands.changecyclecolor.entry")


class FakeComponent:
    """Stand-in for a component that records any color written to it."""

    def __init__(self, name):
        self.name = name
        self.componentColor = None


@pytest.fixture(autouse=True)
def reset_module_state(monkeypatch):
    """Isolate the module globals the abort path manipulates."""
    monkeypatch.setattr(entry, "_pending_targets", [], raising=False)
    monkeypatch.setattr(entry, "_skip_normal_execute", False, raising=False)
    monkeypatch.setattr(entry, "_pending_error_message", None, raising=False)
    monkeypatch.setattr(entry, "_selected_hex", None, raising=False)


# ── _abort_before_dialog ─────────────────────────────────────────────────────
def test_abort_defers_the_message_instead_of_showing_it() -> None:
    """The message is queued for command_destroy, not shown from inside the
    create callback -- that keeps modal UI out of createCommand."""
    entry._abort_before_dialog("nothing selected")
    assert entry._pending_error_message == "nothing selected"


def test_abort_clears_targets_from_the_previous_invocation() -> None:
    """The crux of the stale-state half of the bug: _pending_targets is a
    module global, so an abort must empty it before Fusion auto-executes."""
    entry._pending_targets = [FakeComponent("M3x8 BHCS")]
    entry._abort_before_dialog("nothing selected")
    assert entry._pending_targets == []


def test_abort_tells_execute_to_do_nothing() -> None:
    """Fusion auto-executes a command that built no inputs, so execute has to
    be told there is nothing to apply."""
    entry._abort_before_dialog("nothing selected")
    assert entry._skip_normal_execute is True


# ── the auto-execute that follows an abort ───────────────────────────────────
def test_execute_after_abort_writes_no_color(monkeypatch) -> None:
    """End-to-end on the regression: abort, then let Fusion's auto-execute run.

    With a color and a target left over from a previous invocation, the old
    code would have re-colored that component. Nothing may be written.
    """
    stale = FakeComponent("M3x8 BHCS")
    entry._pending_targets = [stale]
    entry._selected_hex = "C4F570"

    applied = []
    monkeypatch.setattr(
        entry,
        "_set_component_color",
        lambda comp, rgb: applied.append((comp.name, rgb)) or True,
    )

    entry._abort_before_dialog("nothing selected")
    entry.command_execute(object())

    assert applied == []
    assert stale.componentColor is None
    # The specific reason survives for command_destroy to show; it is not
    # overwritten by execute's generic "No color was selected" complaint.
    assert entry._pending_error_message == "nothing selected"


def test_skip_flag_is_consumed_so_the_next_run_still_applies(monkeypatch) -> None:
    """The flag is one-shot. If an abort left it set, the next real invocation
    would silently refuse to apply a color."""
    entry._abort_before_dialog("nothing selected")
    entry.command_execute(object())
    assert entry._skip_normal_execute is False


# ── the shape of the fix ─────────────────────────────────────────────────────
def test_command_created_never_calls_do_execute() -> None:
    """Guard the crash directly: doExecute must not appear in the source of
    command_created or the helper it delegates the abort to."""
    import inspect

    for func in (entry.command_created, entry._abort_before_dialog):
        body = inspect.getsource(func)
        # Strip the docstring, which discusses doExecute deliberately.
        doc = inspect.getdoc(func) or ""
        for line in doc.splitlines():
            body = body.replace(line, "")
        assert "doExecute" not in body, f"{func.__name__} calls doExecute"


if __name__ == "__main__":
    for _name in sorted(n for n in dir() if n.startswith("test_")):
        globals()[_name]()
        print(f"PASS {_name}")
    print("ALL TEST FUNCS PASSED")
