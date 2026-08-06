"""Unit tests for the Animation Named View pure-logic helpers.

Covers the naming rules the command depends on -- recovering the active
storyboard's display name through ``itemByName`` (because ``Storyboard`` exposes
no readable ``name``), the positional fallback after a rename, playhead
formatting including Fusion's scratch zone, collision suffixing, and the
built-in view names that ``NamedViews.itemByName`` cannot see -- plus the
saved-camera drift check.

These helpers have no Fusion dependency and are duck-typed on the
``Storyboards`` / ``NamedViews`` collection shapes, so they run against the
stand-ins below; the module uses package-relative imports, so it is loaded via
its full package path with the conftest scaffolding in place.
"""

import importlib
from pathlib import Path

PT_PKG = Path(__file__).resolve().parent.parent.name
logic = importlib.import_module(f"{PT_PKG}.commands.animationnamedview.logic")


class FakeStoryboard:
    """Stand-in for adsk.fusion.Storyboard (note: no name property, as in Fusion)."""

    def __init__(self, is_active=False, playhead=0.0):
        self.isActive = is_active
        self.playheadPosition = playhead


class FakeStoryboards:
    """Stand-in for the Storyboards collection (count / item / itemByName)."""

    def __init__(self, storyboards, names=None):
        self._storyboards = list(storyboards)
        # Maps display name -> storyboard, mirroring itemByName.
        self._names = dict(names or {})

    @property
    def count(self):
        return len(self._storyboards)

    def item(self, index):
        return self._storyboards[index]

    def itemByName(self, name):
        return self._names.get(name)


class RaisingStoryboards:
    """Collection whose reads raise, to exercise the guard paths."""

    @property
    def count(self):
        raise RuntimeError("count unavailable")

    def item(self, index):
        raise RuntimeError("item unavailable")

    def itemByName(self, name):
        raise RuntimeError("itemByName unavailable")


class FakeNamedView:
    """Stand-in for adsk.core.NamedView."""

    def __init__(self, name, is_valid=True):
        self.name = name
        self.isValid = is_valid


class FakeNamedViews:
    """Stand-in for the NamedViews collection, behaving as documented.

    Returns null for an absent name, and mirrors the documented behaviour that
    itemByName cannot see the four standard views, so those names look free.
    """

    def __init__(self, names=()):
        self._names = set(names)

    def itemByName(self, name):
        return FakeNamedView(name) if name in self._names else None


class FakePoint:
    """Stand-in for adsk.core.Point3D / Vector3D."""

    def __init__(self, x=0.0, y=0.0, z=0.0):
        self.x = x
        self.y = y
        self.z = z


class FakeCamera:
    """Stand-in for adsk.core.Camera, exposing only what the delta check reads."""

    def __init__(self, eye, target, up):
        self.eye = eye
        self.target = target
        self.upVector = up


# ── find_active_storyboard_index ──────────────────────────────────────────────


def test_find_active_storyboard_index_returns_active_position():
    # Arrange
    storyboards = FakeStoryboards(
        [FakeStoryboard(), FakeStoryboard(is_active=True), FakeStoryboard()]
    )

    # Act
    index = logic.find_active_storyboard_index(storyboards)

    # Assert
    assert index == 1


def test_find_active_storyboard_index_returns_none_when_none_active():
    # Arrange
    storyboards = FakeStoryboards([FakeStoryboard(), FakeStoryboard()])

    # Act / Assert
    assert logic.find_active_storyboard_index(storyboards) is None


def test_find_active_storyboard_index_survives_unreadable_collection():
    # Arrange / Act / Assert
    assert logic.find_active_storyboard_index(RaisingStoryboards()) is None


# ── recover_storyboard_name / storyboard_label ────────────────────────────────


def test_recover_storyboard_name_finds_default_name():
    # Arrange -- index 1 is active and still carries Fusion's default name.
    active = FakeStoryboard(is_active=True)
    storyboards = FakeStoryboards(
        [FakeStoryboard(), active], names={"Storyboard2": active}
    )

    # Act
    recovered = logic.recover_storyboard_name(storyboards, 1)

    # Assert
    assert recovered == "Storyboard2"


def test_recover_storyboard_name_returns_none_when_renamed():
    # Arrange -- the active storyboard is no longer under its default name.
    active = FakeStoryboard(is_active=True)
    storyboards = FakeStoryboards(
        [FakeStoryboard(), active], names={"Exploded View": active}
    )

    # Act / Assert
    assert logic.recover_storyboard_name(storyboards, 1) is None


def test_recover_storyboard_name_rejects_inactive_match():
    # Arrange -- the default name resolves, but to a different storyboard.
    other = FakeStoryboard(is_active=False)
    storyboards = FakeStoryboards(
        [FakeStoryboard(is_active=True), other], names={"Storyboard2": other}
    )

    # Act / Assert
    assert logic.recover_storyboard_name(storyboards, 1) is None


def test_storyboard_label_prefers_recovered_name():
    # Arrange
    active = FakeStoryboard(is_active=True)
    storyboards = FakeStoryboards([active], names={"Storyboard1": active})

    # Act / Assert
    assert logic.storyboard_label(storyboards, 0) == "Storyboard1"


def test_storyboard_label_falls_back_to_position_after_rename():
    # Arrange
    storyboards = FakeStoryboards([FakeStoryboard(is_active=True)], names={})

    # Act -- the space distinguishes the fallback from a real default name.
    assert logic.storyboard_label(storyboards, 0) == "Storyboard 1"


def test_storyboard_label_handles_no_active_storyboard():
    # Arrange / Act / Assert
    assert logic.storyboard_label(FakeStoryboards([]), None) == "Animation"


# ── playhead / name derivation ────────────────────────────────────────────────


def test_format_playhead_uses_two_decimals():
    assert logic.format_playhead(3.5) == "3.50s"


def test_format_playhead_labels_the_scratch_zone():
    # Fusion parks the playhead at -1 in the scratch zone; that is a state.
    assert logic.format_playhead(-1) == "scratch"


def test_format_playhead_survives_unreadable_value():
    assert logic.format_playhead(None) == "0.00s"


def test_derive_view_name_combines_label_and_playhead():
    assert logic.derive_view_name("Storyboard2", 3.5) == "Storyboard2 @ 3.50s"


# ── name collision handling ───────────────────────────────────────────────────


def test_unique_view_name_passes_through_a_free_name():
    # Arrange
    name_taken = logic.make_name_taken(FakeNamedViews())

    # Act / Assert
    assert logic.unique_view_name("Storyboard1 @ 0.00s", name_taken) == (
        "Storyboard1 @ 0.00s"
    )


def test_unique_view_name_suffixes_past_collisions():
    # Arrange
    name_taken = logic.make_name_taken(FakeNamedViews({"View", "View-2"}))

    # Act / Assert
    assert logic.unique_view_name("View", name_taken) == "View-3"


def test_make_name_taken_rejects_built_in_view_names():
    # Arrange -- itemByName cannot see the standard views, so they look free.
    named_views = FakeNamedViews()
    name_taken = logic.make_name_taken(named_views)

    # Act / Assert
    for builtin in ("TOP", "FRONT", "RIGHT", "HOME"):
        assert name_taken(builtin) is True
        assert name_taken(builtin.lower()) is True
        assert name_taken(f"  {builtin}  ") is True


def test_make_name_taken_allows_names_merely_containing_a_builtin():
    # Arrange
    name_taken = logic.make_name_taken(FakeNamedViews())

    # Act / Assert -- only the exact standard names are reserved.
    assert name_taken("TOP VIEW") is False


def test_make_name_taken_treats_a_raising_lookup_as_free():
    # Arrange -- observed on a real build: itemByName does not return null for
    # an absent name. Treating that as "taken" made every candidate look taken
    # and drove unique_view_name to its "-999" ceiling.
    class RaisingNamedViews:
        def itemByName(self, name):
            raise RuntimeError("itemByName unavailable")

    name_taken = logic.make_name_taken(RaisingNamedViews())

    # Act / Assert -- defer to add(), which rejects a genuine duplicate.
    assert name_taken("Anything") is False


def test_make_name_taken_ignores_a_lookup_answering_with_another_view():
    # Arrange -- a non-null answer that is not the requested view is no answer.
    class MismatchingNamedViews:
        def itemByName(self, name):
            return FakeNamedView("Something Else")

    name_taken = logic.make_name_taken(MismatchingNamedViews())

    # Act / Assert
    assert name_taken("Wanted") is False


def test_make_name_taken_ignores_an_invalid_view():
    # Arrange
    class StaleNamedViews:
        def itemByName(self, name):
            return FakeNamedView(name, is_valid=False)

    name_taken = logic.make_name_taken(StaleNamedViews())

    # Act / Assert
    assert name_taken("Wanted") is False


def test_find_named_view_returns_the_matching_view():
    # Arrange
    named_views = FakeNamedViews({"Storyboard1 @ 1.00s"})

    # Act
    found = logic.find_named_view(named_views, "Storyboard1 @ 1.00s")

    # Assert -- the command overwrites this view's camera rather than adding.
    assert found is not None
    assert found.name == "Storyboard1 @ 1.00s"


def test_find_named_view_returns_none_for_an_absent_name():
    # Arrange / Act / Assert
    assert logic.find_named_view(FakeNamedViews(), "Nothing") is None


def test_find_named_view_returns_none_when_the_lookup_raises():
    # Arrange
    class RaisingNamedViews:
        def itemByName(self, name):
            raise RuntimeError("itemByName unavailable")

    # Act / Assert -- an unusable answer must not be mistaken for a hit, or the
    # command would overwrite a view it never actually found.
    assert logic.find_named_view(RaisingNamedViews(), "Wanted") is None


def test_find_named_view_rejects_a_mismatched_answer():
    # Arrange
    class MismatchingNamedViews:
        def itemByName(self, name):
            return FakeNamedView("Something Else")

    # Act / Assert
    assert logic.find_named_view(MismatchingNamedViews(), "Wanted") is None


def test_unique_view_name_never_reaches_the_suffix_ceiling_on_a_bad_lookup():
    # Arrange -- the regression that produced 'Storyboard1 @ 1.00s [2]-999'.
    class RaisingNamedViews:
        def itemByName(self, name):
            raise RuntimeError("itemByName unavailable")

    name_taken = logic.make_name_taken(RaisingNamedViews())

    # Act
    result = logic.unique_view_name("Storyboard1 @ 1.00s [2]", name_taken)

    # Assert
    assert result == "Storyboard1 @ 1.00s [2]"
    assert "-999" not in result


# ── camera drift ─────────────────────────────────────────────────────────────


def test_camera_drift_is_zero_for_a_clean_round_trip():
    # Arrange
    camera = FakeCamera(FakePoint(1, 2, 3), FakePoint(0, 0, 0), FakePoint(0, 0, 1))
    saved = FakeCamera(FakePoint(1, 2, 3), FakePoint(0, 0, 0), FakePoint(0, 0, 1))

    # Act
    drift = logic.camera_drift(camera, saved)

    # Assert
    assert drift == 0
    assert drift <= logic.DRIFT_TOLERANCE


def test_camera_drift_reports_the_largest_discrepancy():
    # Arrange -- the shape of the reported perspective-camera bug.
    camera = FakeCamera(FakePoint(1, 2, 3), FakePoint(0, 0, 0), FakePoint(0, 0, 1))
    saved = FakeCamera(FakePoint(50, 2, 3), FakePoint(0, 2, 0), FakePoint(0, 0, 1))

    # Act
    drift = logic.camera_drift(camera, saved)

    # Assert -- the eye moved furthest, so it sets the reported drift.
    assert drift == 49
    assert drift > logic.DRIFT_TOLERANCE


def test_camera_drift_survives_an_unreadable_camera():
    # Arrange
    class RaisingCamera:
        @property
        def eye(self):
            raise RuntimeError("eye unavailable")

    # Act / Assert -- unknown is not the same as clean; the caller skips the check.
    assert logic.camera_drift(RaisingCamera(), RaisingCamera()) is None
