"""Registry-driven enforcement of the per-command contract in ``AGENTS.md``.

``command_registry.py`` is the single source of truth for which commands
exist. Until now the contract each command must keep -- rule 9 (Fusion IDs use
``_``, never ``-``), rule 15 (registry entry, ``CMD_Description``, docs pair,
arch index row, README row) and the ``time.sleep`` half of rule 2 -- was
asserted for exactly one command (``tests/test_exportsysml_entry.py``). These
tests iterate the registry so every command is held to it, and a new command
is held to it the moment it is registered.

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

# Rule 15: docs/arch/<Doc>.md missing. Both commands have a user guide and a
# README row but no architecture note.
KNOWN_ARCH_GAPS = frozenset(
    {
        "Animation Named View.md",
        "Set Up Shared Add-ins Folder.md",
    }
)

# Rule 15: registered command with no row in docs/arch/index.md. The first two
# also lack the arch note itself (above); the other three have a note that the
# index never picked up.
KNOWN_ARCH_INDEX_GAPS = frozenset(
    {
        "Animation Named View.md",
        "Set Up Shared Add-ins Folder.md",
        "Close All Documents.md",
        "Sync Item to Part Number.md",
        "Team Add-ins.md",
    }
)

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
# ``ptutil.pump_events_for()``. These call sites predate the rule and are
# recorded here, not fixed here: {relative path: number of sleep calls}.
KNOWN_TIME_SLEEP_SITES = {
    "commands/partnumber_shared/pn_cache.py": 2,  # upload poll, commit backoff
    "commands/refrences/entry.py": 1,  # thumbnail future poll
    "commands/teamaddins/installer.py": 1,  # rmtree retry backoff
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
    assert "commands/refmanager/entry.py" in literals.get("PTAT_getandupdate", set())
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
