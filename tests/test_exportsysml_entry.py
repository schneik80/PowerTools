"""Tests for the Fusion-facing half of Export SysML Architecture Document.

``entry`` is imported as ``PowerTools.commands.exportsysml.entry`` so its
relative imports resolve and ``adsk`` comes from the stub finder in
``conftest.py``. Almost all of the module is Fusion API calls that only mean
anything inside Fusion; what is testable here is the command's identity, the
contract it keeps with the registry and the docs, and one structural guarantee
that cannot be re-derived from the pure modules:

``test_no_execute_handler_is_registered`` is the guard that matters. This
command does all its work in ``command_created`` because ``execute`` never fires
when no document is open, which is the latent bug in the two sibling export
commands. Adding an execute handler later would silently reintroduce it, and the
AST guard in ``tests/test_command_abort.py`` would not catch it -- that one only
looks for ``doExecute`` inside ``command_created``.
"""

import ast
import importlib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PT_PKG = REPO_ROOT.name

entry = importlib.import_module(f"{PT_PKG}.commands.exportsysml.entry")

DOC_NAME = "Export SysML.md"
ENTRY_SOURCE = REPO_ROOT / "commands" / "exportsysml" / "entry.py"


def test_command_identity_is_stable():
    """The id is the settings key and the control id.

    Changing it orphans a user's Preferences choice and any QAT pin they made
    for this command (6789216, 7dee722).
    """
    assert entry.CMD_ID == "PTE_exportsysml"
    assert entry.CMD_NAME == "Export SysML Architecture Document..."


def test_command_id_uses_underscores_only():
    """A hyphen in a Fusion id logs "invalid characters" on every launch."""
    assert "-" not in entry.CMD_ID
    assert entry.CMD_ID.startswith("PTE_")


def test_description_is_ascii_and_correctly_cased():
    """``CMD_Description`` is read by name and doubles as a Fusion tooltip.

    An all-caps ``CMD_DESCRIPTION`` is silently ignored by the Preferences
    palette and the button, which shipped once as an empty summary (aa6802e).
    """
    assert entry.CMD_Description
    assert entry.CMD_Description.isascii()
    assert not hasattr(entry, "CMD_DESCRIPTION")
    assert entry.CMD_NAME.isascii()


def test_the_registry_entry_matches_this_module():
    """The command is registered in the exports group with the exact doc name."""
    registry = importlib.import_module(f"{PT_PKG}.command_registry")

    exports = [group for group in registry.GROUPS if group["key"] == "exports"][0]
    entries = {command["module"]: command for command in exports["commands"]}

    assert "exportsysml" in entries
    assert entries["exportsysml"]["doc"] == DOC_NAME
    assert entries["exportsysml"]["beta"] is False
    assert entries["exportsysml"]["has_settings"] is False


def test_both_doc_pages_exist_under_the_registered_filename():
    """The doc filename is used verbatim for the guide and the arch note.

    Nothing at build time catches a mismatch: the Preferences palette appends
    the filename to a GitHub URL, so a typo becomes a 404 for the user.
    """
    assert (REPO_ROOT / "docs" / DOC_NAME).is_file()
    assert (REPO_ROOT / "docs" / "arch" / DOC_NAME).is_file()


def test_the_command_is_listed_in_the_readme_and_the_arch_index():
    """A registered command that no index mentions is undiscoverable."""
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    index = (REPO_ROOT / "docs" / "arch" / "index.md").read_text(encoding="utf-8")

    assert "./docs/Export%20SysML.md" in readme
    assert "Export%20SysML.md" in index


def _handler_registrations(tree):
    """Every ``ptutil.add_handler`` first argument, as a dotted string."""
    targets = []
    for call in ast.walk(tree):
        if not isinstance(call, ast.Call):
            continue
        function = call.func
        name = function.attr if isinstance(function, ast.Attribute) else None
        if name != "add_handler" or not call.args:
            continue
        targets.append(ast.unparse(call.args[0]))
    return targets


def test_no_execute_handler_is_registered():
    """The command must not grow an execute handler.

    ``execute`` does not fire when no document is open, so a QAT File-menu
    command whose work lives there does nothing in exactly the case its
    precondition message exists for (f18b911, 11cfc51). This command runs
    everything in ``command_created``; an execute handler would reintroduce the
    bug and would also need the ``_command_abort`` flag machinery to stop it
    acting on a previous run's state (5bae0e3).
    """
    tree = ast.parse(ENTRY_SOURCE.read_text(encoding="utf-8"))

    registered = _handler_registrations(tree)

    assert registered == ["cmd_def.commandCreated"], (
        f"expected only a commandCreated handler, found {registered}"
    )


def test_no_do_execute_call_anywhere_in_the_module():
    """``doExecute`` from ``command_created`` segfaults Fusion (14871d7).

    The repo-wide AST guard already covers ``command_created``; this command has
    no other callback that could legitimately need it, so the whole module is
    held to the stricter rule.
    """
    source = ENTRY_SOURCE.read_text(encoding="utf-8")
    assert "doExecute" not in source


def test_the_pure_modules_stay_free_of_adsk():
    """Quantities and text generation must remain testable outside Fusion."""
    for module in ("model.py", "render.py"):
        source = (REPO_ROOT / "commands" / "exportsysml" / module).read_text(
            encoding="utf-8"
        )
        assert "import adsk" not in source


def test_joint_and_design_type_names_are_mapped_for_every_enum_member():
    """Every Fusion joint type has a name, so none renders as "Unknown"."""
    assert len(entry._JOINT_TYPE_NAMES) == 8
    assert set(entry._JOINT_TYPE_NAMES.values()) == {
        "Rigid",
        "Revolute",
        "Slider",
        "Cylindrical",
        "PinSlot",
        "Planar",
        "Ball",
        "Inferred",
    }
    assert set(entry._DESIGN_TYPE_NAMES.values()) == {"Direct", "Parametric"}


def test_output_suffixes_distinguish_the_two_files():
    """The document and the model must not collide on one name."""
    assert entry.ADD_SUFFIX != entry.SYSML_SUFFIX
    assert entry.ADD_SUFFIX.endswith(".md")
    assert entry.SYSML_SUFFIX.endswith(".sysml")


def test_read_helper_swallows_a_failing_property():
    """Every Fusion read goes through ``_read``; a raise becomes the default.

    A stale handle or an unsupported property must cost one value, not the whole
    export -- the document reports the gap in its notes appendix instead.
    """

    def boom():
        raise RuntimeError("stale handle")

    assert entry._read(boom) is None
    assert entry._read(boom, 0) == 0
    assert entry._read(lambda: 42) == 42


# ---------------------------------------------------------------------------
# key_for


class _FakeComponent:
    def __init__(self, comp_id, name):
        self.id = comp_id
        self.name = name


class _FakeOccurrence:
    """An occurrence whose ``documentReference`` raises, as a nested one does."""

    isReferencedComponent = True

    @property
    def documentReference(self):
        raise RuntimeError(
            "3 : Cannot get allDocumentReferences of a non-top-level document."
        )


def test_two_components_sharing_a_persistent_id_stay_distinct():
    """Fusion's ``Component.id`` is not always unique, and merging is wrong.

    A component copied from another inside a referenced document carries the
    original's id. A real hub assembly has "CVD Pivot Pin" and "CVD Drive Pin"
    sharing one id, and keying on it alone dropped the second component from the
    model and attached its joint to the first.
    """
    scan = entry._Scan(None)
    shared = "012331ee-63d2-46b6-b607-e74d637af56e"
    occurrence = _FakeOccurrence()

    pivot = scan.key_for(_FakeComponent(shared, "CVD Pivot Pin"), occurrence)
    drive = scan.key_for(_FakeComponent(shared, "CVD Drive Pin"), occurrence)

    assert pivot != drive
    # The same component read twice is still one key, so a repeat visit is
    # still skipped and its properties still evaluated once.
    assert scan.key_for(_FakeComponent(shared, "CVD Pivot Pin"), occurrence) == pivot


def test_a_shared_persistent_id_is_reported_not_absorbed():
    """The reader has to be told, because a rename would merge the two."""
    scan = entry._Scan(None)
    shared = "shared-id"
    occurrence = _FakeOccurrence()

    scan.key_for(_FakeComponent(shared, "CVD Pivot Pin"), occurrence)
    assert scan.notes == []

    scan.key_for(_FakeComponent(shared, "CVD Drive Pin"), occurrence)
    assert len(scan.notes) == 1
    assert "share one persistent id" in scan.notes[0]
    assert "'CVD Drive Pin'" in scan.notes[0]
    assert "'CVD Pivot Pin'" in scan.notes[0]

    # Reported once, not once per joint end that reaches the same component.
    scan.key_for(_FakeComponent(shared, "CVD Drive Pin"), occurrence)
    assert len(scan.notes) == 1


def test_a_component_with_no_persistent_id_falls_back_to_its_name():
    scan = entry._Scan(None)

    key = scan.key_for(_FakeComponent("", "Nameless"), None)

    assert key == "name:Nameless"
    assert "reported no persistent id" in scan.notes[0]


# ---------------------------------------------------------------------------
# Cross-platform writing
#
# Both sibling export commands call `open(path, "w")` with neither argument,
# which raises UnicodeEncodeError on a non-ASCII component name under a cp1252
# default and turns every line ending in a .sysml file into CRLF on Windows.
# CI runs on Linux and the dev box is macOS, so nothing here would notice the
# regression; this is a source-level guard instead.


def _write_opens(tree):
    """Every `open(...)` call in the module opened for writing."""
    calls = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = getattr(node.func, "id", None)
        if name != "open":
            continue
        mode = ""
        if len(node.args) > 1 and isinstance(node.args[1], ast.Constant):
            mode = str(node.args[1].value)
        for keyword in node.keywords:
            if keyword.arg == "mode" and isinstance(keyword.value, ast.Constant):
                mode = str(keyword.value.value)
        if "w" in mode or "a" in mode:
            calls.append(node)
    return calls


def test_every_write_pins_its_encoding_and_line_ending():
    """UTF-8 and LF, explicitly, on every file this command writes."""
    tree = ast.parse(ENTRY_SOURCE.read_text(encoding="utf-8"))

    writes = _write_opens(tree)

    assert writes, "expected at least one file write in entry.py"
    for call in writes:
        keywords = {
            k.arg: getattr(k.value, "value", None)
            for k in call.keywords
            if k.arg is not None
        }
        assert keywords.get("encoding") == "utf-8", ast.unparse(call)
        assert keywords.get("newline") == "\n", ast.unparse(call)


# ---------------------------------------------------------------------------
# _record_reference
#
# Fusion marks the contents of a referenced subassembly as referenced too, but
# refuses documentReference for them. A Rear Hub export listed the eight parts
# inside a linked CVD assembly as eight more linked documents, labelled with
# their occurrence names -- 14 rows for 8 real documents.


class _NamedDataFile:
    def __init__(self, name, file_id):
        self.name = name
        self.id = file_id


class _Reference:
    def __init__(self, name, file_id, version=2, out_of_date=False):
        self.dataFile = _NamedDataFile(name, file_id)
        self.version = version
        self.isOutOfDate = out_of_date


class _ResolvableOccurrence:
    """A top-level referenced occurrence: its document can be named."""

    isReferencedComponent = True

    def __init__(self, name, file_id):
        self.name = f"{name}:1"
        self.documentReference = _Reference(name, file_id)


class _LocalOccurrence:
    isReferencedComponent = False
    name = "Local:1"


def test_a_resolvable_reference_is_recorded():
    scan = entry._Scan(None)

    scan._record_reference(_ResolvableOccurrence("CVD ASSY - Rear", "urn:cvd"), "k1")

    assert list(scan.references) == ["urn:cvd"]
    assert scan.references["urn:cvd"]["label"] == "CVD ASSY - Rear"
    assert scan.references["urn:cvd"]["keys"] == {"k1"}


def test_an_unnameable_reference_is_left_out_of_the_module_structure():
    """A part inside a linked assembly is not itself a linked document.

    Listing it would present the contents of one module as several, labelled
    with occurrence names and carrying no version -- which is what the Rear Hub
    export did.
    """
    scan = entry._Scan(None)

    scan._record_reference(_FakeOccurrence(), "k1")

    assert scan.references == {}
    assert scan._unidentified_refs


def test_a_local_component_is_not_a_reference_at_all():
    scan = entry._Scan(None)

    scan._record_reference(_LocalOccurrence(), "k1")

    assert scan.references == {}
    assert not scan._unidentified_refs


def test_instances_of_one_document_aggregate_onto_a_single_row():
    scan = entry._Scan(None)

    scan._record_reference(_ResolvableOccurrence("Bearing", "urn:brg"), "k1")
    scan._record_reference(_ResolvableOccurrence("Bearing", "urn:brg"), "k2")

    assert list(scan.references) == ["urn:brg"]
    assert scan.references["urn:brg"]["keys"] == {"k1", "k2"}
