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


def test_triangle_budget_leaves_the_preview_usable():
    # The solver is pure Python: this budget is roughly a one-second solve, and
    # raising it trades a responsive dialog for detail nobody asked for.
    assert 1000 <= entry._MAX_TRIANGLES <= 6000
    assert entry._COARSEN_ATTEMPTS >= 2
