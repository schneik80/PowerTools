"""Cheap source-level checks for user-visible hygiene across ``commands/``.

Each check here is an AST walk over the tree that was earned by a concrete
slip found in review; none of them proves behaviour inside Fusion. They live
apart from ``tests/test_command_contract.py`` (registry-driven contract rules)
because they are about what the user *sees*, not about how a command is wired.

- **Dialog titles are the command name, not its ID.** Sketch Under-constrained
  showed ``PTPM_sketchunderconstrain`` as the ``messageBox`` title (D13). A
  ``CMD_ID`` is a Fusion-internal handle (rule 9) and never user text.
- **No placeholder ``example.com`` URLs ship.** Assign Drawing Number linked
  its setup guide to ``https://example.com/drawing-number-setup`` (D14).
- **A module-level ``CMD_AFTER`` must be passed somewhere.** Timeline Compute
  Report declared ``CMD_AFTER = "InterferenceCheckCommand"`` and then placed
  its control with ``addCommand(cmd_def, "", True)`` (D12b); a dead position
  ID fails silently in Fusion (6789216).
- **Design-intent labels read as intents.** Assign Part Numbers labelled
  ``INTENT_ASSEMBLY`` as "Assembly Palette", the name of a different command
  (D15). The labels now live in the ``adsk``-free ``schemes.py``.

The helpers are deliberately copied from ``test_command_contract.py`` rather
than imported so the two files can change independently.
"""

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
COMMANDS_DIR = REPO_ROOT / "commands"

# Guards against a silently empty scan (a moved directory, a bad glob).
MIN_ENTRY_FILES = 50


# --- Helpers ----------------------------------------------------------------


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _command_sources():
    return [
        p for p in sorted(COMMANDS_DIR.rglob("*.py")) if "__pycache__" not in p.parts
    ]


def _entry_paths():
    return sorted(COMMANDS_DIR.glob("*/entry.py"))


def _rel(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def _string_constants(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            yield node


def _module_level_assignment(tree: ast.Module, name: str):
    """Return the value node of the first module-level ``name = ...``, or None."""
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return node.value
    return None


# --- Tests ------------------------------------------------------------------


def test_scan_floor():
    """The glob must still find the tree; a silent zero would pass everything."""
    assert len(_entry_paths()) >= MIN_ENTRY_FILES


def test_no_message_box_titled_with_cmd_id():
    """``ui.messageBox(text, CMD_ID, ...)`` shows the Fusion ID as the dialog
    title. The second positional argument is the title; it must be user text
    (``CMD_NAME``), never the ``CMD_ID`` name (D13)."""
    offenders = set()
    for path in _command_sources():
        for node in ast.walk(_parse(path)):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (isinstance(func, ast.Attribute) and func.attr == "messageBox"):
                continue
            if len(node.args) < 2:
                continue
            title = node.args[1]
            if isinstance(title, ast.Name) and title.id == "CMD_ID":
                offenders.add(f"{_rel(path)}:{node.lineno}")
    assert offenders == set()


def test_no_example_com_urls():
    """No shipped string constant may point at ``example.com`` (D14)."""
    offenders = set()
    for path in _command_sources():
        for node in _string_constants(_parse(path)):
            if "example.com" in node.value.casefold():
                offenders.add(f"{_rel(path)}:{node.lineno}")
    assert offenders == set()


def test_cmd_after_is_referenced():
    """A module-level ``CMD_AFTER = ...`` that is never read is a position ID
    the control was meant to anchor on and does not (D12b, 6789216)."""
    unused = set()
    for path in _entry_paths():
        tree = _parse(path)
        if _module_level_assignment(tree, "CMD_AFTER") is None:
            continue
        loads = [
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.Name)
            and n.id == "CMD_AFTER"
            and isinstance(n.ctx, ast.Load)
        ]
        if not loads:
            unused.add(_rel(path))
    assert unused == set()


def test_intent_labels_read_as_intents():
    """Every ``INTENT_LABELS`` value names a design intent, not another
    command (D15)."""
    from PowerTools.commands.partnumber_shared import schemes

    assert set(schemes.INTENT_LABELS) == {
        schemes.INTENT_PART,
        schemes.INTENT_ASSEMBLY,
        schemes.INTENT_HYBRID,
    }
    for value in schemes.INTENT_LABELS.values():
        assert value.endswith(" Intent"), value
