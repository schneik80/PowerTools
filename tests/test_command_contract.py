"""Registry-driven enforcement of the per-command contract in ``AGENTS.md``.

``command_registry.py`` is the single source of truth for which commands
exist. Until now the contract each command must keep -- rule 9 (Fusion IDs use
``_``, never ``-``), rule 15 (registry entry, ``CMD_Description``, docs pair,
arch index row, README row) and the ``time.sleep`` half of rule 2 -- was
asserted for exactly one command (``tests/test_exportsysml_entry.py``). These
tests iterate the registry so every command is held to it, and a new command
is held to it the moment it is registered. Rule 6 (no document close inside an
``execute`` handler) and the ``SystemExit`` guard (issue #9) are AST walks over
the same files.

Every known gap is an explicit allowlist that the matching test asserts is
*exactly equal* to what the tree contains. Fixing a gap therefore fails the
test until the allowlist shrinks, and a new gap fails it loudly. The
allowlists are the to-do list; do not grow them to make a test pass.

Entry modules are imported as ``PowerTools.commands.<module>.entry`` so their
relative imports resolve and ``adsk`` comes from the stub in ``conftest.py``.
Nothing here proves behaviour inside Fusion.
"""

import ast
import importlib
import re
from pathlib import Path
from urllib.parse import quote

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PT_PKG = REPO_ROOT.name
COMMANDS_DIR = REPO_ROOT / "commands"
DOCS_DIR = REPO_ROOT / "docs"
ARCH_DIR = DOCS_DIR / "arch"

registry = importlib.import_module(f"{PT_PKG}.command_registry")

COMMANDS = [cmd for _group, cmd in registry.iter_commands()]
MODULES = [cmd["module"] for cmd in COMMANDS]

# ``preferences`` is infrastructure, started before the registry, and owns a
# CMD_ID other commands anchor on (``PT_preferences``). It is not registered
# but its entry.py is held to the same ID rules.
UNREGISTERED_ENTRY_MODULES = ("preferences",)

# --- Allowlists (the gaps) --------------------------------------------------

# Rule 15: docs/arch/<Doc>.md missing. Empty: every registered command has an
# architecture note. Add to this set only for a brand-new command whose note
# is genuinely pending, and remove it in the commit that adds the note.
KNOWN_ARCH_GAPS: frozenset[str] = frozenset()

# Rule 15: registered command with no row in docs/arch/index.md. Empty: the
# index lists every note.
KNOWN_ARCH_INDEX_GAPS: frozenset[str] = frozenset()

# Rule 9: CMD_ID built as an f-string from ``config.COMPANY_NAME`` ("IMA LLC")
# and ``config.ADDIN_NAME``, so the resolved ID contains a space. Renaming a
# CMD_ID orphans users' QAT pins (6789216), so the fix is a deliberate change,
# not a cleanup; until then these three are the only non-literal CMD_IDs.
KNOWN_NONLITERAL_CMD_IDS = frozenset({"confighub", "relateddata", "configteamaddins"})

# Registered modules whose entry.py defines no ``CMD_ID`` at all:
#   assemblypalette -- a palette; its launch button is ``LAUNCH_CMD_ID``.
#   docopen         -- event-only (documentOpened / documentActivated), no command.
#   openrecent      -- a QAT dropdown; its control is ``DROPDOWN_ID``.
KNOWN_NO_CMD_ID = frozenset({"assemblypalette", "docopen", "openrecent"})

# Every ``PT*_`` string literal in commands/ that is not a CMD_ID, with why it
# is legitimate. Each was read in context; none is a stale ``positionID``.
KNOWN_NON_COMMAND_PT_LITERALS = {
    # Custom event ids (``app.registerCustomEvent``), derived from a CMD_ID.
    "PT_teamaddins_startup_check": "custom event: teamaddins startup check",
    "PTND_matchunits_check": "custom event: matchunits document check",
    "PTND_matchunits_mfg_check": "custom event: matchunits Manufacture check",
    "PTND_history_loadHistory": "custom event: dochistory deferred load",
    "PTND_history_docSwitch": "custom event: dochistory document switch",
    "PTND_history_thumbTick": "custom event: dochistory thumbnail poll",
    "PTAT_assemblyPalette_finishInsert": "custom event: assemblypalette insert",
    "PTAT_assemblyPalette_thumbTick": "custom event: assemblypalette thumbnails",
    "PTAT_externalize_runner": "custom event: externalize batch runner",
    # Secondary command / control definitions owned by the file that uses them.
    "PTAT_assemblyPalette": "assemblypalette LAUNCH_CMD_ID (launch button)",
    "PTAT_favorites_add": "favorites CMD_ADD_ID (Favorite This Location)",
    "PTAT_favorites_edit": "favorites CMD_EDIT_ID (Edit Favorites)",
    "PT_openrecent_dropdown": "openrecent DROPDOWN_ID (File-menu flyout)",
    "PT_openrecent_item_": "openrecent ITEM_ID_PREFIX (one button per recent)",
    "PT_openrecent_empty": "openrecent EMPTY_ITEM_ID (placeholder item)",
    "PTAT_fav_": "favorites per-entry button id prefix (f-string PTAT_fav_{i})",
    # Command input ids inside a dialog.
    "PTAN_autoName": "animationnamedview AUTO_NAME_INPUT_ID",
    "PTAN_name": "animationnamedview NAME_INPUT_ID",
    "PTAT_favorites_edit_table": "favorites EDIT_TABLE_ID",
    "PTAT_favorites_edit_delete": "favorites EDIT_DELETE_BTN_ID",
    "PTAT_favorites_edit_count": "favorites EDIT_COUNT_ID",
    # Not an id at all.
    "PTAT_thumbs": "refrences THUMB_DIR temp folder name",
}

# Rule 2 (f0ff1af): ``time.sleep`` parks the UI thread; use
# ``ptutil.pump_events_for()``. The upload poll, commit backoff and thumbnail
# poll were converted under #18. The one site left is deliberate: it sleeps
# only after ``shutil.rmtree`` raises, waiting on another process's file lock,
# which pumping cannot release, and pumping mid folder-swap would invite
# re-entrancy. {relative path: number of sleep calls}.
KNOWN_TIME_SLEEP_SITES = {
    "commands/teamaddins/installer.py": 1,  # rmtree retry backoff, off the happy path
}

# ``exit()`` / ``quit()`` / ``sys.exit()`` raise SystemExit, which is not an
# Exception: it escapes the handler's ``except Exception:`` and ptutil's
# wrapper alike and lands in Fusion's Python host (issue #9). Handlers bail
# out with ``return``. The one known site is a child process, where exiting
# is the point: {relative path: number of exit calls}.
KNOWN_PROCESS_EXIT_SITES = {
    "commands/changecyclecolor/_color_picker_subprocess.py": 1,
}

# Rule 6 (11cfc51): never close a document inside a command event. That crash
# was the *visible* close. The invisible ``documents.open(df, False)`` +
# ``close(False)`` inside ``command_execute`` was probed with
# ``tools/fusion_probes/close_in_execute_probe.py`` on 2706.0.97, macOS
# ADSKMVG91G2F5W and Windows g16win.local, production and pre-production,
# 2026-09-30: no fault in any placement, though the open fires documentOpened
# into every other command (issue #11). Issue #10 asked for exactly the two
# probed sites; the walk below (execute handlers plus the same-module helpers
# they call, one level deep) also finds three unprobed ones, and a plausible
# wrong number is worse than an error, so all five are recorded here.
# Recorded, not blessed; shrinks as sites are restructured (deferred
# Timer -> custom event, the probe's mode C/D). {relative path: close calls}.
KNOWN_CLOSE_IN_EXECUTE_SITES = {
    # Probed. Invisible open, close in ``finally`` of a helper called from
    # command_execute. Ships enabled.
    "commands/assigndrawingnumber/entry.py": 1,
    # Probed (modes E and F, 2026-09-30): the open passes ``True`` (visible)
    # with no pump before the close; no fault on either platform or channel.
    # Ships disabled for unrelated reasons (lessons.md).
    "commands/versiondiff/entry.py": 2,
    # Not probed. Closures defined and called inside command_execute close the
    # processed document and sweep strays, pumping 0.25 s after each close.
    "commands/bottomupupdate/entry.py": 2,
    # Not probed. ``_apply_parameters`` creates/saves a parameters document
    # and closes it (mid-path and in ``finally``).
    "commands/globalParameters/entry.py": 2,
    # Not probed. ``_derive_into_active`` opens invisibly, closes in
    # ``finally`` and re-activates the caller's document.
    "commands/linkGlobalParameters/entry.py": 1,
}

# Every registered dialog command registers ``.execute``; the input-less,
# palette and event-only entry files do not (rule 1). 28 files register one as
# of 2026-09-30 (38 before issue #16 moved eight QAT launchers into
# commandCreated, one fewer after #22 removed a Sketch-panel command); a walk
# that sees fewer than this has broken, not found a clean tree.
MIN_EXECUTE_HANDLER_FILES = 25

# Rule 1 (f18b911, 11cfc51, 8a676af): ``execute`` never fires with no document
# open, and nothing raises. A commandCreated handler that registers
# ``.execute`` but builds no CommandInput therefore does nothing in exactly the
# no-document case. Issue #16 moved the ones reachable from the QAT / QATRight
# (favorites' navigate and Add items, the six share-flyout commands,
# getandupdate, and a since-removed QAT launcher) into commandCreated. The
# handlers below still do it. Seven sit on Design-workspace toolbar panels, which Fusion only shows
# with a document open, so the case cannot arise there. Three sit in the QAT
# File dropdown, live on the start screen, and have the same bug as issue #16:
# recorded here, not fixed here. {module: (handler, ...)}. Shrinks as sites
# move; never grows for a new QAT / QATRight item.
KNOWN_EXECUTE_ONLY_INPUTLESS = {
    # Design workspace > Tools tab > Power Tools panel (config.my_panel_id).
    "assemblybuilder": ("command_created",),
    # Same panel; aborts before the dialog on no design / unsaved document.
    "assemblystats": ("command_created",),
    # Same panel.
    "docinfo": ("command_created",),
    # Design workspace > Manage tab > Power Tools panel (config.manage_panel_id).
    "syncitempartnumber": ("command_created",),
    # Design workspace > Sketch tab > Modify panel (SketchModifyPanel).
    "sketchunderconstrained": ("command_created",),
    # Design workspace > Solid tab > Inspect panel (InspectPanel).
    "timelinecompute": ("command_created",),
    # Design workspace > Solid tab > Create panel (SolidCreatePanel).
    "mirrorderive": ("command_created",),
    # QAT File dropdown, before ExportCommand: same shape, same gap.
    "exportbomcsv": ("command_created",),
    # QAT File dropdown, before ExportCommand: same shape, same gap.
    "exportmermaid": ("command_created",),
}

# Prefixes in use: PT_, PTAT_, PTND_, PTE_, PTPM_, PTAN_, PTSHD_. The rule
# that matters is no ``-`` and no whitespace; the shape pins what exists.
CMD_ID_SHAPE = re.compile(r"^PT[A-Z]*_[A-Za-z0-9_]+$")
PT_LITERAL_SHAPE = re.compile(r"^PT[A-Za-z]*_\w+$")


# --- Helpers ----------------------------------------------------------------


def _entry_path(module: str) -> Path:
    return COMMANDS_DIR / module / "entry.py"


def _entry_paths():
    """Every ``commands/*/entry.py`` that belongs to a registered or
    infrastructure command, in registry order."""
    return [_entry_path(m) for m in (*MODULES, *UNREGISTERED_ENTRY_MODULES)]


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _module_level_assignment(tree: ast.Module, name: str):
    """Return the value node of the first module-level ``name = ...``, or None."""
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return node.value
    return None


def _cmd_id_nodes():
    """{module: value node} for each entry.py that assigns ``CMD_ID``."""
    found = {}
    for path in _entry_paths():
        value = _module_level_assignment(_parse(path), "CMD_ID")
        if value is not None:
            found[path.parent.name] = value
    return found


def _literal_cmd_ids() -> set[str]:
    return {
        node.value
        for node in _cmd_id_nodes().values()
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }


def _command_sources():
    return [
        p for p in sorted(COMMANDS_DIR.rglob("*.py")) if "__pycache__" not in p.parts
    ]


def _string_constants(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            yield node.value


def _is_sleep_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr == "sleep" and isinstance(func.value, ast.Name)
    return isinstance(func, ast.Name) and func.id == "sleep"


def _is_process_exit_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name):
        return func.id in {"exit", "quit"}
    return (
        isinstance(func, ast.Attribute)
        and func.attr in {"exit", "_exit"}
        and isinstance(func.value, ast.Name)
        and func.value.id in {"sys", "os"}
    )


def _is_add_handler(call: ast.Call) -> bool:
    """``add_handler(...)`` under any prefix: ``ptutil.add_handler``, bare, etc."""
    func = call.func
    if isinstance(func, ast.Attribute):
        return func.attr == "add_handler"
    return isinstance(func, ast.Name) and func.id == "add_handler"


def _function_defs(tree: ast.AST):
    return [
        n
        for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]


def _event_handlers(tree: ast.Module, event: str):
    """Every FunctionDef registered via ``add_handler(<x>.<event>, <handler>)``.

    Same resolution as ``tests/test_command_abort.py``: a handler passed by
    name resolves to the FunctionDef(s) of that name; a handler produced by a
    factory call (``_make_open_handler(...)``) resolves to every FunctionDef
    nested inside that factory.
    """
    by_name: dict[str, list] = {}
    for fu in _function_defs(tree):
        by_name.setdefault(fu.name, []).append(fu)
    for call in ast.walk(tree):
        if not (isinstance(call, ast.Call) and _is_add_handler(call)):
            continue
        if len(call.args) < 2:
            continue
        target = call.args[0]
        if not (isinstance(target, ast.Attribute) and target.attr == event):
            continue
        handler = call.args[1]
        if isinstance(handler, ast.Name):
            yield from by_name.get(handler.id, [])
        elif isinstance(handler, ast.Call) and isinstance(handler.func, ast.Name):
            for factory in by_name.get(handler.func.id, []):
                for nested in _function_defs(factory):
                    if nested is not factory:
                        yield nested


def _file_handle_names(fn: ast.AST) -> set[str]:
    """Names bound from the builtin ``open(...)`` inside *fn* (``fh = open(p)``,
    ``with open(p) as fh``). Their ``.close()`` closes a file, not a document;
    ``app.documents.open`` is an Attribute call and is not matched."""
    names: set[str] = set()

    def _is_builtin_open(node):
        return (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "open"
        )

    for node in ast.walk(fn):
        if isinstance(node, ast.Assign) and _is_builtin_open(node.value):
            names.update(t.id for t in node.targets if isinstance(t, ast.Name))
        elif isinstance(node, ast.With):
            for item in node.items:
                if _is_builtin_open(item.context_expr) and isinstance(
                    item.optional_vars, ast.Name
                ):
                    names.add(item.optional_vars.id)
    return names


def _close_calls_in(fn: ast.AST):
    """``<receiver>.close(...)`` calls in *fn*, minus file handles."""
    files = _file_handle_names(fn)
    for node in ast.walk(fn):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "close"
        ):
            continue
        receiver = node.func.value
        if isinstance(receiver, ast.Name) and receiver.id in files:
            continue
        yield node


def _close_in_execute_sites(tree: ast.Module):
    """Line numbers of document ``.close()`` calls reachable from an
    ``.execute`` handler: in the handler itself (nested closures included,
    since ``ast.walk`` descends into them) or in a same-module function it
    calls, one level deep -- assigndrawingnumber's close lives in a helper.
    Lines are a set so a closure counted from the handler and again as a
    callee is one site."""
    by_name = {fu.name: fu for fu in _function_defs(tree)}
    lines: set[int] = set()
    for handler in _event_handlers(tree, "execute"):
        scopes = [handler]
        for node in ast.walk(handler):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in by_name
                and by_name[node.func.id] is not handler
            ):
                scopes.append(by_name[node.func.id])
        for scope in scopes:
            lines.update(call.lineno for call in _close_calls_in(scope))
    return lines


def _import_entry(module: str):
    return importlib.import_module(f"{PT_PKG}.commands.{module}.entry")


# --- Registry shape ---------------------------------------------------------


def test_registry_module_keys_are_unique():
    """The module key is the folder name and the user's settings key; a
    duplicate would silently merge two commands' enable state."""
    assert len(MODULES) == len(set(MODULES)), sorted(
        m for m in set(MODULES) if MODULES.count(m) > 1
    )


def test_registry_doc_names_are_unique():
    docs = [cmd["doc"] for cmd in COMMANDS]
    assert len(docs) == len(set(docs))


def test_registry_is_not_empty():
    """A broken registry import must not make every parametrised test vanish."""
    assert len(COMMANDS) >= 50


# --- Rule 15: per-command contract ------------------------------------------


@pytest.mark.parametrize("module", MODULES)
def test_entry_module_exists(module):
    assert _entry_path(module).is_file(), f"commands/{module}/entry.py missing"


@pytest.mark.parametrize("module", MODULES)
def test_entry_imports_under_the_stub(module):
    """Import errors at Fusion load time take the whole add-in down (14abc78)."""
    _import_entry(module)


@pytest.mark.parametrize("module", MODULES)
def test_cmd_description_is_present_ascii_and_correctly_cased(module):
    """``CMD_Description`` is read by that exact name for the Preferences
    palette and the button tooltip; an all-caps ``CMD_DESCRIPTION`` shipped
    once as an empty summary (aa6802e). ASCII because it doubles as a Fusion
    tooltip."""
    entry = _import_entry(module)
    description = getattr(entry, "CMD_Description", None)
    assert isinstance(description, str) and description.strip(), (
        f"{module}: CMD_Description missing or empty"
    )
    assert description.isascii(), f"{module}: CMD_Description is not ASCII"
    assert not hasattr(entry, "CMD_DESCRIPTION"), (
        f"{module}: CMD_DESCRIPTION is ignored by the palette; use CMD_Description"
    )


@pytest.mark.parametrize("cmd", COMMANDS, ids=lambda c: c["module"])
def test_user_doc_exists_under_the_registered_filename(cmd):
    """The Preferences palette appends the registered filename to a GitHub
    URL, so a typo is a 404 for the user."""
    assert (DOCS_DIR / cmd["doc"]).is_file(), f"docs/{cmd['doc']} missing"


@pytest.mark.parametrize("cmd", COMMANDS, ids=lambda c: c["module"])
def test_arch_doc_exists_or_is_a_known_gap(cmd):
    exists = (ARCH_DIR / cmd["doc"]).is_file()
    if cmd["doc"] in KNOWN_ARCH_GAPS:
        assert not exists, (
            f"{cmd['doc']} now has an arch note; drop it from KNOWN_ARCH_GAPS"
        )
    else:
        assert exists, f"docs/arch/{cmd['doc']} missing"


def test_known_arch_gaps_are_all_registered_docs():
    docs = {cmd["doc"] for cmd in COMMANDS}
    assert KNOWN_ARCH_GAPS <= docs
    assert KNOWN_ARCH_INDEX_GAPS <= docs


@pytest.mark.parametrize("cmd", COMMANDS, ids=lambda c: c["module"])
def test_arch_index_lists_the_doc_or_it_is_a_known_gap(cmd):
    """A command no index mentions is undiscoverable to a developer."""
    index = (ARCH_DIR / "index.md").read_text(encoding="utf-8")
    listed = quote(cmd["doc"]) in index or cmd["doc"] in index
    if cmd["doc"] in KNOWN_ARCH_INDEX_GAPS:
        assert not listed, (
            f"{cmd['doc']} is now in docs/arch/index.md; drop it from "
            "KNOWN_ARCH_INDEX_GAPS"
        )
    else:
        assert listed, f"docs/arch/index.md has no row for {cmd['doc']}"


@pytest.mark.parametrize("cmd", COMMANDS, ids=lambda c: c["module"])
def test_readme_links_the_user_doc(cmd):
    """Match the link *target*, not the label: the Animation Named View row is
    labelled "Save Named View"."""
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    target = f"./docs/{quote(cmd['doc'])}"
    assert target in readme, f"README.md has no link to {target}"


# --- Rule 9: CMD_ID shape ---------------------------------------------------


def test_every_entry_defines_cmd_id_or_is_a_known_exception():
    with_id = set(_cmd_id_nodes())
    expected = set(MODULES) | set(UNREGISTERED_ENTRY_MODULES)
    assert expected - with_id == KNOWN_NO_CMD_ID, (
        "modules without CMD_ID changed; update KNOWN_NO_CMD_ID: "
        f"{sorted(expected - with_id)}"
    )


def test_nonliteral_cmd_ids_are_exactly_the_known_three():
    """Rule 9. The allowlist must shrink when one is fixed and grow loudly."""
    nonliteral = {
        module
        for module, node in _cmd_id_nodes().items()
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str))
    }
    assert nonliteral == KNOWN_NONLITERAL_CMD_IDS


def test_the_known_nonliteral_cmd_ids_really_do_violate_rule_9():
    """Keep the allowlist honest: if the resolved value becomes clean, the
    module must move to a literal and leave the list."""
    for module in KNOWN_NONLITERAL_CMD_IDS:
        cmd_id = _import_entry(module).CMD_ID
        assert not CMD_ID_SHAPE.match(cmd_id), (
            f"{module}: CMD_ID {cmd_id!r} is now well-formed; make it a literal"
        )


def test_literal_cmd_ids_have_the_fusion_id_shape():
    """A hyphen or a space in a Fusion id logs "invalid characters" on every
    launch (6789216); the prefix set pins what exists."""
    bad = {
        module: node.value
        for module, node in _cmd_id_nodes().items()
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and not CMD_ID_SHAPE.match(node.value)
    }
    assert not bad, bad


def test_literal_cmd_ids_are_unique():
    ids = [
        node.value
        for node in _cmd_id_nodes().values()
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]
    assert len(ids) == len(set(ids)), sorted(i for i in set(ids) if ids.count(i) > 1)


# --- Foreign PT*_ literals resolve -----------------------------------------


def _pt_literals_by_file():
    """{literal: {relative path, ...}} for every PT*_ string constant."""
    found: dict[str, set[str]] = {}
    for path in _command_sources():
        for value in _string_constants(_parse(path)):
            if PT_LITERAL_SHAPE.match(value):
                found.setdefault(value, set()).add(
                    str(path.relative_to(REPO_ROOT)).replace("\\", "/")
                )
    return found


def test_every_pt_literal_is_a_cmd_id_or_a_known_non_command_id():
    """A ``positionID`` or anchor that names a CMD_ID that no longer exists
    places the control nowhere, silently. Every PT*_ literal that is not some
    entry.py's CMD_ID must be in the allowlist, and vice versa."""
    literals = _pt_literals_by_file()
    unresolved = {lit for lit in literals if lit not in _literal_cmd_ids()}

    extra = unresolved - set(KNOWN_NON_COMMAND_PT_LITERALS)
    stale = set(KNOWN_NON_COMMAND_PT_LITERALS) - unresolved
    assert not extra, {lit: sorted(literals[lit]) for lit in sorted(extra)}
    assert not stale, f"no longer in the tree; drop from allowlist: {sorted(stale)}"


def test_the_literal_walk_can_see_cross_module_anchors():
    """Self-check: the walk must find a known foreign anchor, or an empty
    result would pass the test above vacuously."""
    literals = _pt_literals_by_file()
    assert "commands/linkGlobalParameters/entry.py" in literals.get(
        "PTAT_globalParameters", set()
    )
    assert "commands/scriptsmanager/entry.py" in literals.get("PT_preferences", set())


def test_pt_literals_use_underscores_only():
    """Rule 9 for every PT*_ id, not just CMD_ID: input ids and custom event
    ids are Fusion ids too."""
    offenders = sorted(
        lit for lit in _pt_literals_by_file() if "-" in lit or " " in lit
    )
    assert not offenders, offenders


# --- Rule 2: no time.sleep on the UI thread ---------------------------------


def test_time_sleep_sites_are_exactly_the_known_ones():
    """``time.sleep`` parks the UI thread; use ``ptutil.pump_events_for()``
    (f0ff1af). The known sites are recorded, not blessed."""
    found: dict[str, int] = {}
    for path in _command_sources():
        count = sum(1 for node in ast.walk(_parse(path)) if _is_sleep_call(node))
        if count:
            found[str(path.relative_to(REPO_ROOT)).replace("\\", "/")] = count
    assert found == KNOWN_TIME_SLEEP_SITES


def test_process_exit_sites_are_exactly_the_known_ones():
    """``exit()`` in a handler raises SystemExit past every ``except
    Exception:`` into Fusion's Python host (issue #9). Handlers ``return``."""
    found: dict[str, int] = {}
    for path in _command_sources():
        count = sum(1 for node in ast.walk(_parse(path)) if _is_process_exit_call(node))
        if count:
            found[str(path.relative_to(REPO_ROOT)).replace("\\", "/")] = count
    assert found == KNOWN_PROCESS_EXIT_SITES


# --- Rule 6: no document close inside an execute handler --------------------


def test_close_in_execute_sites_are_exactly_the_known_ones():
    """Rule 6 (11cfc51): a document closed inside a command event. The known
    sites are recorded, not blessed; see KNOWN_CLOSE_IN_EXECUTE_SITES for
    which were probed and how (issue #10)."""
    found: dict[str, int] = {}
    for path in _entry_paths():
        count = len(_close_in_execute_sites(_parse(path)))
        if count:
            found[str(path.relative_to(REPO_ROOT)).replace("\\", "/")] = count
    assert found == KNOWN_CLOSE_IN_EXECUTE_SITES


def test_the_execute_walk_can_actually_see_handlers():
    """Self-check: if ``add_handler`` or ``.execute`` were renamed, or the
    helper-following broke, the guard above would pass on an empty set. Pin a
    floor, the two probed handlers, and the helper hop that finds
    assigndrawingnumber's close."""
    with_execute = {
        path.parent.name
        for path in _entry_paths()
        if any(True for _ in _event_handlers(_parse(path), "execute"))
    }
    assert len(with_execute) >= MIN_EXECUTE_HANDLER_FILES, sorted(with_execute)
    assert {"assigndrawingnumber", "versiondiff", "bottomupupdate"} <= with_execute

    adn = _parse(_entry_path("assigndrawingnumber"))
    direct = {
        call.lineno
        for handler in _event_handlers(adn, "execute")
        for call in _close_calls_in(handler)
    }
    assert not direct, "assigndrawingnumber's close moved into command_execute"
    assert _close_in_execute_sites(adn), "the one-level helper hop is broken"


# --- Rule 1: execute-only handlers that build no input ----------------------


def _same_module_closure(tree: ast.Module, fn: ast.AST):
    """*fn* plus every same-module function it calls, transitively, so a
    handler that builds its dialog in ``_build_inputs(inputs)`` or registers
    its events in a helper is judged on the whole of what it runs."""
    by_name = {fu.name: fu for fu in _function_defs(tree)}
    seen, todo = [], [fn]
    while todo:
        scope = todo.pop()
        if any(scope is s for s in seen):
            continue
        seen.append(scope)
        for node in ast.walk(scope):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in by_name
            ):
                todo.append(by_name[node.func.id])
    return seen


def _registers_execute(scopes) -> bool:
    return any(
        isinstance(call, ast.Call)
        and _is_add_handler(call)
        and call.args
        and isinstance(call.args[0], ast.Attribute)
        and call.args[0].attr == "execute"
        for scope in scopes
        for call in ast.walk(scope)
    )


_ADD_INPUT = re.compile(r"^add\w*Input$")


def _builds_input(scopes) -> bool:
    """Any ``add*Input`` / ``addCommandInput`` call: the dialog exists, so
    Fusion waits for OK instead of auto-executing, and a document is implied."""
    return any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and _ADD_INPUT.match(node.func.attr)
        for scope in scopes
        for node in ast.walk(scope)
    )


def _execute_only_inputless_handlers():
    """{module: (handler name, ...)} for every commandCreated handler that
    registers ``.execute`` and builds no input. Judged per handler, not per
    module: favorites builds a dialog for Edit Favorites while its navigate
    and Add handlers built none, and a module-level check would have hidden
    them (issue #16)."""
    found: dict[str, tuple[str, ...]] = {}
    for path in _entry_paths():
        tree = _parse(path)
        names = []
        for handler in _event_handlers(tree, "commandCreated"):
            scopes = _same_module_closure(tree, handler)
            if _registers_execute(scopes) and not _builds_input(scopes):
                names.append(handler.name)
        if names:
            found[path.parent.name] = tuple(sorted(set(names)))
    return found


def test_execute_only_inputless_handlers_are_exactly_the_known_ones():
    """A commandCreated handler that registers ``.execute`` and builds no
    input does nothing when no document is open (rule 1). The known ones are
    behind design-panel buttons that need a document to be clicked; anything
    on the QAT belongs in commandCreated (issue #16)."""
    assert _execute_only_inputless_handlers() == KNOWN_EXECUTE_ONLY_INPUTLESS


def test_the_inputless_walk_can_actually_see_handlers():
    """Self-check: the walk must see the handler that registers execute, the
    one that builds inputs (so a dialog command is *not* flagged) and the
    favorites handlers it must judge separately."""
    fav = _parse(_entry_path("favorites"))
    handlers = {h.name: h for h in _event_handlers(fav, "commandCreated")}
    assert {"_created", "_add_favorite_created", "_edit_favorites_created"} <= set(
        handlers
    )
    edit = _same_module_closure(fav, handlers["_edit_favorites_created"])
    assert _registers_execute(edit) and _builds_input(edit)
    add = _same_module_closure(fav, handlers["_add_favorite_created"])
    assert not _registers_execute(add)


# --- positionID anchors name a command that has already started -------------


def _pt_anchor_sites():
    """(module, anchor literal, line) for every ``addCommand(<def>, "PT...",
    ...)``; Fusion's own control ids (``"save"``, ``"ExportCommand"``) are not
    PT literals and are skipped."""
    for path in _entry_paths():
        for node in ast.walk(_parse(path)):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "addCommand"
                and len(node.args) >= 2
            ):
                continue
            anchor = node.args[1]
            if (
                isinstance(anchor, ast.Constant)
                and isinstance(anchor.value, str)
                and PT_LITERAL_SHAPE.match(anchor.value)
            ):
                yield path.parent.name, anchor.value, node.lineno


def test_pt_anchors_name_a_command_that_started_earlier():
    """``addCommand(cmd_def, positionID, ...)`` places the control relative to
    an existing control. A PT anchor whose command starts *later* in
    ``command_registry.iter_commands()`` order does not exist yet when this
    ``start()`` runs, so the placement is whatever Fusion does with an
    unresolved positionID (issue #21: shareSettings anchored on projectInvite,
    four modules later). ``preferences`` starts before the registry."""
    start_order = [*UNREGISTERED_ENTRY_MODULES, *MODULES]
    owner = {
        node.value: module
        for module, node in _cmd_id_nodes().items()
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    offenders = []
    for module, anchor, line in _pt_anchor_sites():
        anchor_module = owner.get(anchor)
        if anchor_module is None:
            offenders.append(f"{module}:{line} anchors on {anchor!r}: not a CMD_ID")
        elif start_order.index(anchor_module) >= start_order.index(module):
            offenders.append(
                f"{module}:{line} anchors on {anchor!r} ({anchor_module}), "
                "which starts later"
            )
    assert not offenders, offenders


def test_the_anchor_walk_can_actually_see_anchors():
    """Self-check: linkGlobalParameters anchors on globalParameters; an empty
    walk would pass the test above vacuously.
    (scriptsmanager anchors on preferences through a Name, ``PREFERENCES_CMD_ID``,
    which the literal walk deliberately does not see.)"""
    sites = {(module, anchor) for module, anchor, _ in _pt_anchor_sites()}
    assert ("linkGlobalParameters", "PTAT_globalParameters") in sites
