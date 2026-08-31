"""Tests for the Fusion-facing half of Flatten Surface.

``entry`` is imported as ``PowerTools.commands.flattensurface.entry`` so its
relative imports resolve and ``adsk`` comes from the stub finder in
``conftest.py``. Most of the module is Fusion API calls that only mean anything
inside Fusion; what is testable here is the arithmetic that decides how the
pattern is meshed and where it lands, plus the guarantee that the module
imports at all - a broken import would take the whole add-in's command list
down with it, since ``commands/__init__.py`` imports each entry module to start
it.
"""

import importlib
import math

entry = importlib.import_module("PowerTools.commands.flattensurface.entry")


class FakePoint:
    def __init__(self, x, y, z):
        self.x = x
        self.y = y
        self.z = z


class FakeBox:
    """Stand-in for a BoundingBox3D that records what it was combined with."""

    def __init__(self, low, high):
        self.minPoint = FakePoint(*low)
        self.maxPoint = FakePoint(*high)

    def combine(self, other):
        self.minPoint = FakePoint(
            min(self.minPoint.x, other.minPoint.x),
            min(self.minPoint.y, other.minPoint.y),
            min(self.minPoint.z, other.minPoint.z),
        )
        self.maxPoint = FakePoint(
            max(self.maxPoint.x, other.maxPoint.x),
            max(self.maxPoint.y, other.maxPoint.y),
            max(self.maxPoint.z, other.maxPoint.z),
        )


class FakeFace:
    def __init__(self, box, token="t"):
        self.boundingBox = box
        self.entityToken = token


def test_command_identity_is_stable():
    # The id is the settings key and the panel control id; changing it silently
    # orphans a user's preference for this command.
    assert entry.CMD_ID == "PTPM_flattensurface"
    assert entry.CMD_NAME == "Flatten Surface"


def test_the_registry_entry_matches_this_module():
    registry = importlib.import_module("PowerTools.command_registry")
    modules = [
        command["module"] for group in registry.GROUPS for command in group["commands"]
    ]

    assert "flattensurface" in modules


def test_quality_levels_run_coarse_to_fine():
    sags = [sag for sag, _side in entry._QUALITY.values()]
    sides = [side for _sag, side in entry._QUALITY.values()]

    assert sags == sorted(sags, reverse=True)
    assert sides == sorted(sides, reverse=True)
    assert entry._DEFAULT_QUALITY in entry._QUALITY


def test_every_quality_caps_the_triangle_side():
    # Sag tolerance alone leaves a planar face as two triangles, which will not
    # weld against a finely meshed curved neighbour.
    for sag, side in entry._QUALITY.values():
        assert 0.0 < side < 1.0
        assert side > sag


def test_selection_diagonal_spans_every_face():
    faces = [
        FakeFace(FakeBox((0.0, 0.0, 0.0), (1.0, 0.0, 0.0))),
        FakeFace(FakeBox((0.0, 0.0, 0.0), (0.0, 0.0, 2.0))),
    ]

    diagonal = entry._selection_diagonal(faces)

    assert abs(diagonal - math.sqrt(1.0 + 4.0)) < 1e-9


def test_selection_diagonal_survives_a_face_without_a_box():
    class Awkward:
        @property
        def boundingBox(self):
            raise RuntimeError("no box")

    assert entry._selection_diagonal([Awkward()]) > 0.0


def test_selection_diagonal_never_returns_zero():
    # A zero would be divided by when the mesh tolerance is chosen.
    faces = [FakeFace(FakeBox((1.0, 1.0, 1.0), (1.0, 1.0, 1.0)))]

    assert entry._selection_diagonal(faces) > 0.0


def test_selection_key_changes_with_every_input_that_changes_the_result():
    faces = [FakeFace(FakeBox((0.0, 0.0, 0.0), (1.0, 1.0, 1.0)), token="a")]
    base = entry._selection_key(faces, "Medium", True)

    assert base == entry._selection_key(faces, "Medium", True)
    assert base != entry._selection_key(faces, "Fine", True)
    assert base != entry._selection_key(faces, "Medium", False)
    other = [FakeFace(FakeBox((0.0, 0.0, 0.0), (1.0, 1.0, 1.0)), token="b")]
    assert base != entry._selection_key(other, "Medium", True)


def test_selection_key_falls_back_when_a_face_has_no_token():
    class Tokenless:
        @property
        def entityToken(self):
            raise RuntimeError("unsupported")

    face = Tokenless()

    assert entry._selection_key([face], "Medium", True) is not None


class RecordingInputs:
    """Records the order and ids of the inputs a dialog adds."""

    def __init__(self):
        self.order = []
        self.made = {}

    def _make(self, kind, input_id):
        self.order.append(input_id)
        made = _FakeInput(kind)
        self.made[input_id] = made
        return made

    def addSelectionInput(self, input_id, *_args):
        return self._make("selection", input_id)

    def addTriadCommandInput(self, input_id, *_args):
        return self._make("triad", input_id)

    def addDropDownCommandInput(self, input_id, *_args):
        return self._make("dropdown", input_id)

    def addBoolValueInput(self, input_id, *_args):
        return self._make("bool", input_id)

    def addTextBoxCommandInput(self, input_id, *_args):
        return self._make("text", input_id)

    def itemById(self, input_id):
        return self.made.get(input_id)


class _FakeInput:
    def __init__(self, kind):
        self.kind = kind
        self.isVisible = True
        self.handlesHidden = False
        self.listItems = _FakeListItems()

    def addSelectionFilter(self, _name):
        pass

    def setSelectionLimits(self, *_args):
        pass

    def hideAll(self):
        self.handlesHidden = True


class _FakeListItems:
    def __init__(self):
        self.items = []

    def add(self, name, selected):
        self.items.append((name, selected))


def _build_dialog(monkeypatch):
    """Run command_created against a recording inputs collection."""

    class FakeCommand:
        def __init__(self, inputs):
            self.commandInputs = inputs
            self.execute = object()
            self.executePreview = object()
            self.inputChanged = object()
            self.destroy = object()

    class FakeArgs:
        def __init__(self, command):
            self.command = command

    inputs = RecordingInputs()
    monkeypatch.setattr(entry.ptutil, "add_handler", lambda *a, **k: None)
    entry.command_created(FakeArgs(FakeCommand(inputs)))
    return inputs


def test_the_placement_plane_is_asked_for_first(monkeypatch):
    # Nothing can be previewed until there is a plane to draw the pattern on,
    # so it leads the dialog rather than following the face selection.
    inputs = _build_dialog(monkeypatch)

    assert inputs.order[0] == entry.INPUT_PLANE
    assert inputs.order.index(entry.INPUT_PLANE) < inputs.order.index(entry.INPUT_FACES)


def test_the_manipulator_starts_hidden(monkeypatch):
    # It has nowhere meaningful to sit until a plane is picked. Hiding the
    # handles is the part that matters: isVisible governs the input's row in
    # the dialog, so on its own it leaves a full triad sitting at the origin
    # that visibly reshapes itself when the plane is finally picked.
    inputs = _build_dialog(monkeypatch)
    triad = inputs.made[entry.INPUT_TRIAD]

    assert triad.handlesHidden is True
    assert triad.isVisible is False


def test_the_dialog_offers_every_control(monkeypatch):
    inputs = _build_dialog(monkeypatch)

    for input_id in (
        entry.INPUT_PLANE,
        entry.INPUT_TRIAD,
        entry.INPUT_CHAIN,
        entry.INPUT_FACES,
        entry.INPUT_QUALITY,
        entry.INPUT_RELAX,
        entry.INPUT_WIREFRAME,
        entry.INPUT_EXPORT,
        entry.INPUT_STATS,
    ):
        assert input_id in inputs.made


def test_input_ids_are_unique():
    ids = [
        entry.INPUT_PLANE,
        entry.INPUT_TRIAD,
        entry.INPUT_CHAIN,
        entry.INPUT_FACES,
        entry.INPUT_QUALITY,
        entry.INPUT_RELAX,
        entry.INPUT_WIREFRAME,
        entry.INPUT_EXPORT,
        entry.INPUT_STATS,
    ]

    assert len(set(ids)) == len(ids)


def test_triangle_budget_leaves_the_preview_usable():
    # The solver is pure Python: this budget is roughly a one-second solve, and
    # raising it trades a responsive dialog for detail nobody asked for.
    assert 1000 <= entry._MAX_TRIANGLES <= 6000
    assert entry._COARSEN_ATTEMPTS >= 2


class ChainFace:
    """A face that knows its smooth neighbours, as BRepFace does."""

    def __init__(self, token):
        self.entityToken = token
        self.tangentiallyConnectedFaces = []
        self.assemblyContext = None


def tangent_run(*tokens):
    """A chain of faces each smoothly joined to the next."""
    faces = [ChainFace(t) for t in tokens]
    for left, right in zip(faces, faces[1:], strict=False):
        left.tangentiallyConnectedFaces.append(right)
        right.tangentiallyConnectedFaces.append(left)
    return faces


def test_chaining_walks_the_whole_tangent_run():
    # tangentiallyConnectedFaces only reports a face's immediate smooth
    # neighbours, so a filleted run is only reached by walking outward from
    # each of them in turn.
    faces = tangent_run("a", "b", "c", "d")

    found = entry.tangent_closure([faces[0]])

    assert set(found) == {"a", "b", "c", "d"}


def test_chaining_starts_from_the_middle_too():
    faces = tangent_run("a", "b", "c", "d", "e")

    found = entry.tangent_closure([faces[2]])

    assert set(found) == {"a", "b", "c", "d", "e"}


def test_chaining_does_not_cross_a_sharp_edge():
    smooth = tangent_run("a", "b")
    other = tangent_run("x", "y")

    found = entry.tangent_closure([smooth[0]])

    assert set(found) == {"a", "b"}
    assert other[0].entityToken not in found


def test_chaining_terminates_on_a_loop():
    # A fillet running right around a boss closes on itself; the walk has to
    # notice it has been there before.
    faces = tangent_run("a", "b", "c")
    faces[0].tangentiallyConnectedFaces.append(faces[-1])
    faces[-1].tangentiallyConnectedFaces.append(faces[0])

    found = entry.tangent_closure([faces[0]])

    assert set(found) == {"a", "b", "c"}


def test_chaining_merges_runs_reached_from_several_seeds():
    left = tangent_run("a", "b")
    right = tangent_run("x", "y")

    found = entry.tangent_closure([left[0], right[0]])

    assert set(found) == {"a", "b", "x", "y"}


def test_chaining_includes_the_seed_when_it_stands_alone():
    lone = ChainFace("solo")

    assert set(entry.tangent_closure([lone])) == {"solo"}


def test_chaining_survives_a_face_that_refuses_to_report_neighbours():
    class Awkward:
        entityToken = "awkward"

        @property
        def tangentiallyConnectedFaces(self):
            raise RuntimeError("unsupported in this context")

    assert set(entry.tangent_closure([Awkward()])) == {"awkward"}


def test_face_identity_falls_back_to_position_without_a_token():
    class Tokenless:
        @property
        def entityToken(self):
            raise RuntimeError("unsupported")

        boundingBox = FakeBox((0.0, 0.0, 0.0), (1.0, 2.0, 3.0))

    key = entry._face_key(Tokenless())

    assert "1.000000" in key
