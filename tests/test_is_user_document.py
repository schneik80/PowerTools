"""Unit tests for ``ptAddInUtils.is_user_document``.

The helper is the first line of every document-event handler (issue #11): an
invisible ``app.documents.open(dataFile, False)`` fires ``documentOpened`` /
``documentActivated`` like any open, so handlers must confirm the event is about
the user's visible, active document before acting. It is imported via the
``PowerTools.*`` package (``conftest.py`` scaffolding); the documents are plain
stand-ins because only attribute reads are exercised.
"""

import importlib

import pytest

general_utils = importlib.import_module("PowerTools.lib.ptAddInUtils.general_utils")


class _Doc:
    """Minimal Document stand-in with the three flags the helper reads."""

    def __init__(self, valid=True, visible=True, active=True):
        self.isValid = valid
        self.isVisible = visible
        self.isActive = active


class _Faulting:
    """Document whose property read raises, standing in for a mid-close handle."""

    def __init__(self, failing: str):
        self._failing = failing

    def __getattr__(self, name):
        if name == self._failing:
            raise RuntimeError(f"{name} unavailable")
        return True


def test_none_is_not_a_user_document():
    assert general_utils.is_user_document(None) is False


def test_all_flags_true_is_a_user_document():
    assert general_utils.is_user_document(_Doc()) is True


@pytest.mark.parametrize(
    "kwargs",
    [
        {"valid": False},
        {"visible": False},
        {"active": False},
    ],
    ids=["invalid", "invisible", "inactive"],
)
def test_any_false_flag_rejects(kwargs):
    assert general_utils.is_user_document(_Doc(**kwargs)) is False


@pytest.mark.parametrize("prop", ["isValid", "isVisible", "isActive"])
def test_raising_property_rejects(prop):
    """A stale handle must be treated as 'not the user's', never propagated."""
    assert general_utils.is_user_document(_Faulting(prop)) is False


def test_missing_property_rejects():
    """An object without the flags (wrong type, partial wrapper) is rejected."""
    assert general_utils.is_user_document(object()) is False


def test_exported_through_package():
    ptutil = importlib.import_module("PowerTools.lib.ptAddInUtils")
    assert ptutil.is_user_document is general_utils.is_user_document
