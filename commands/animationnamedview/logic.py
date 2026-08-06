# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.
"""Pure, Fusion-free helpers for the Animation Named View command.

Kept separate from ``entry.py`` so the named-view naming rules and the saved
camera check can be unit-tested without a live Fusion runtime (see
``tests/test_animationnamedview_logic.py``).

Nothing here imports ``adsk``. The Fusion objects are duck-typed on the shapes
the API exposes -- ``count`` / ``item(i)`` / ``itemByName(name)`` for the
``Storyboards`` and ``NamedViews`` collections, ``isActive`` /
``playheadPosition`` for a storyboard, and ``x`` / ``y`` / ``z`` for a point --
the same approach ``closealldocuments.logic`` uses so tests can drive them with
stand-ins.

The naming rules exist because of a gap in the Fusion API: ``Storyboard`` has no
readable ``name`` property (verified against the shipped stubs -- the only
``name`` on the class is the *input* parameter of ``copy()``). Storyboard names
plainly exist, since ``Storyboards.itemByName`` looks them up, but they cannot
be read back off a storyboard object. So the display name is recovered by
probing ``itemByName`` with Fusion's default name for that slot, and the command
falls back to a positional label when the user has renamed the storyboard.

Every attribute read is guarded. These helpers run against API surface that has
already been observed to diverge from its documentation (see
``make_name_taken``), so a read that fails has to degrade rather than abort a
save.
"""

from __future__ import annotations

import math

# The four standard named views. Fusion exposes these through dedicated
# properties on the NamedViews collection and deliberately hides them from
# item() / itemByName() / count, so a name collision with one of them cannot be
# detected by lookup and has to be rejected by comparison instead.
BUILT_IN_VIEW_NAMES = frozenset({"TOP", "FRONT", "RIGHT", "HOME"})

# Fusion's default storyboard names are "Storyboard1", "Storyboard2", ... The
# probe below relies on this pattern; when it does not match, the storyboard has
# been renamed and the positional fallback is used instead.
_DEFAULT_STORYBOARD_PREFIX = "Storyboard"

# Upper bound on the "-2", "-3", ... disambiguation suffix, so a pathological
# collision cannot spin forever.
_MAX_NAME_ATTEMPTS = 999

# How far a saved view's camera may sit from the one submitted before it is
# reported as wrong. Autodesk have an open report that saving a perspective
# camera can yield a named view whose eye is far from the original; it does not
# reproduce on every build, so the command checks rather than assumes.
DRIFT_TOLERANCE = 0.001


def find_active_storyboard_index(storyboards) -> int | None:
    """Locate the active storyboard by position within its collection.

    ``AnimationManager.activeStoryboard`` returns the storyboard itself, but the
    object carries no name and no index, so the position has to be recovered by
    scanning for the one that reports ``isActive``.

    Args:
        storyboards: A Fusion ``Storyboards`` collection (``count`` / ``item``).

    Returns:
        The zero-based index of the active storyboard, or None when the
        collection cannot be read or reports no active storyboard.
    """
    try:
        count = storyboards.count
    except Exception:
        return None
    for index in range(count):
        try:
            storyboard = storyboards.item(index)
            if storyboard is not None and storyboard.isActive:
                return index
        except Exception:
            continue
    return None


def recover_storyboard_name(storyboards, index: int) -> str | None:
    """Recover the active storyboard's display name, if it still has the default.

    Non-destructive: it asks the collection for Fusion's default name for this
    slot and confirms the storyboard that comes back is the active one. A
    renamed storyboard correctly yields None, because there is no API to read a
    storyboard's name directly.

    Args:
        storyboards: A Fusion ``Storyboards`` collection (``itemByName``).
        index: Zero-based index of the active storyboard.

    Returns:
        The recovered name, or None when the storyboard has been renamed or the
        lookup cannot be performed.
    """
    candidate = f"{_DEFAULT_STORYBOARD_PREFIX}{index + 1}"
    try:
        storyboard = storyboards.itemByName(candidate)
    except Exception:
        return None
    if storyboard is None:
        return None
    try:
        return candidate if storyboard.isActive else None
    except Exception:
        return None


def storyboard_label(storyboards, index: int | None) -> str:
    """Build the storyboard portion of a view name.

    Prefers the real display name and falls back to a positional label, so the
    generated name still identifies the storyboard after a rename.

    Args:
        storyboards: A Fusion ``Storyboards`` collection.
        index: Zero-based index of the active storyboard, or None if unknown.

    Returns:
        The recovered name (``"Storyboard2"``), the positional fallback
        (``"Storyboard 2"``, with a space), or ``"Animation"`` when there is no
        active storyboard to describe.
    """
    if index is None:
        return "Animation"
    recovered = recover_storyboard_name(storyboards, index)
    if recovered:
        return recovered
    return f"{_DEFAULT_STORYBOARD_PREFIX} {index + 1}"


def format_playhead(seconds) -> str:
    """Render a playhead position for use inside a view name.

    Fusion parks the playhead in a "scratch zone" at -1, which is a state rather
    than a time, so it is labelled instead of formatted as a duration.

    Args:
        seconds: Playhead position in seconds, as a float.

    Returns:
        A short label such as ``"3.50s"``, or ``"scratch"`` for the scratch zone.
    """
    try:
        value = float(seconds)
    except (TypeError, ValueError):
        return "0.00s"
    if value < 0:
        return "scratch"
    return f"{value:.2f}s"


def derive_view_name(label: str, playhead) -> str:
    """Compose the auto-generated named-view name.

    The playhead is part of the name because a storyboard is normally sampled at
    several points, and the storyboard label alone would collide every time.

    Args:
        label: Storyboard label from ``storyboard_label``.
        playhead: Playhead position in seconds.

    Returns:
        A name such as ``"Storyboard2 @ 3.50s"``.
    """
    return f"{label} @ {format_playhead(playhead)}"


def view_matches_name(view, name: str) -> bool:
    """Confirm a looked-up named view really is the one that was asked for.

    ``NamedViews.itemByName`` is documented to return null for an absent name,
    but it does not reliably do so -- see ``make_name_taken``. Confirming the
    returned object is valid and actually carries the requested name is what
    distinguishes a real collision from a non-answer.

    Args:
        view: The object ``itemByName`` returned.
        name: The name that was looked up.

    Returns:
        True only when the object is a live named view with that exact name.
        An unreadable object counts as no match, leaving ``add()`` as the final
        arbiter of a duplicate rather than blocking on an unverifiable lookup.
    """
    try:
        if not view.isValid:
            return False
    except Exception:
        pass
    try:
        return view.name == name
    except Exception:
        return False


def find_named_view(named_views, name: str):
    """Return the existing named view with exactly this name, or None.

    A lookup that fails, or that answers with something other than a view of
    that name, yields None. That is deliberate and was learned the hard way:
    treating an unusable answer as a hit made every candidate name look taken,
    so ``unique_view_name`` ran its suffix range to exhaustion and produced
    names like ``"View-999"``.

    Args:
        named_views: A Fusion ``NamedViews`` collection (``itemByName``).
        name: The exact name to look for.

    Returns:
        The matching ``NamedView``, or None. The four standard views are never
        returned, because Fusion hides them from ``itemByName``.
    """
    try:
        existing = named_views.itemByName(name)
    except Exception:
        return None
    if existing is None:
        return None
    return existing if view_matches_name(existing, name) else None


def make_name_taken(named_views):
    """Build the "is this named-view name already used" test.

    Two sources of collision have to be covered. ``NamedViews.itemByName``
    reports user-created views but is documented to exclude the four standard
    views, so those are rejected by name comparison as well -- otherwise
    ``add()`` would be handed a name that looks free and fail.

    An unverifiable lookup counts as *free*; Fusion's own ``add()`` rejects a
    genuine duplicate and that failure is surfaced, so deferring to it is safer
    than guessing. See ``find_named_view``.

    Args:
        named_views: A Fusion ``NamedViews`` collection (``itemByName``).

    Returns:
        A callable taking a name and returning True when it is unavailable.
    """

    def name_taken(name: str) -> bool:
        if name.strip().upper() in BUILT_IN_VIEW_NAMES:
            return True
        return find_named_view(named_views, name) is not None

    return name_taken


def unique_view_name(base: str, name_taken) -> str:
    """Disambiguate a view name against the names already in use.

    Args:
        base: The desired name.
        name_taken: Predicate from ``make_name_taken``.

    Returns:
        ``base`` when it is free, otherwise ``base`` with a ``"-2"``, ``"-3"``,
        ... suffix. Falls back to the highest-numbered candidate if every one is
        somehow taken, leaving it to Fusion to reject the duplicate.
    """
    if not name_taken(base):
        return base
    candidate = base
    for suffix in range(2, _MAX_NAME_ATTEMPTS + 1):
        candidate = f"{base}-{suffix}"
        if not name_taken(candidate):
            return candidate
    return candidate


def point_distance(first, second) -> float | None:
    """Measure the distance between two Fusion points.

    Args:
        first: An object exposing ``x`` / ``y`` / ``z``.
        second: An object exposing ``x`` / ``y`` / ``z``.

    Returns:
        The distance, or None when either point cannot be read.
    """
    try:
        return math.sqrt(
            (first.x - second.x) ** 2
            + (first.y - second.y) ** 2
            + (first.z - second.z) ** 2
        )
    except Exception:
        return None


def camera_drift(source, saved) -> float | None:
    """Measure how far a saved named view sits from the camera it was built from.

    A returned ``NamedView`` only proves ``add()`` accepted the input, not that
    the stored view matches the viewport, so the camera is read back and
    compared. This is what catches the reported perspective-camera failure on
    builds where it reproduces.

    Args:
        source: The camera passed to ``NamedViews.add``.
        saved: The camera read back off the created ``NamedView``.

    Returns:
        The largest of the eye, target, and up-vector discrepancies, or None
        when either camera cannot be read.
    """
    try:
        distances = (
            point_distance(source.eye, saved.eye),
            point_distance(source.target, saved.target),
            point_distance(source.upVector, saved.upVector),
        )
    except Exception:
        return None
    if any(distance is None for distance in distances):
        return None
    return max(distances)
