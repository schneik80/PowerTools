"""Unit tests for ``ptAddInUtils.pump_events_for``.

The helper replaces bare ``time.sleep`` calls in the Bottom-Up Update poll loops
so the Fusion UI thread keeps pumping ``adsk.doEvents()`` instead of freezing for
a whole poll interval. It is imported via the ``PowerTools.*`` package
(``conftest.py`` scaffolding); ``adsk`` and ``time`` are monkeypatched so the
cadence is asserted deterministically without real sleeping.
"""

import importlib

general_utils = importlib.import_module("PowerTools.lib.ptAddInUtils.general_utils")


class _FakeClock:
    """Deterministic stand-in for the ``time`` module used by the helper."""

    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


def _count_doevents(monkeypatch):
    """Patch adsk.doEvents to a counter and return the mutable count holder."""
    calls = {"n": 0}
    monkeypatch.setattr(
        general_utils.adsk,
        "doEvents",
        lambda: calls.__setitem__("n", calls["n"] + 1),
        raising=False,
    )
    return calls


def test_pump_events_for_zero_pumps_once_without_sleeping(monkeypatch):
    """A non-positive duration pumps exactly once and never sleeps."""
    # Arrange
    calls = _count_doevents(monkeypatch)
    clock = _FakeClock()
    monkeypatch.setattr(general_utils, "time", clock)

    # Act
    general_utils.pump_events_for(0)

    # Assert
    assert calls["n"] == 1
    assert clock.sleeps == []


def test_pump_events_for_pumps_repeatedly_until_deadline(monkeypatch):
    """The wait is broken into tick-sized slices, each pumping doEvents."""
    # Arrange
    calls = _count_doevents(monkeypatch)
    clock = _FakeClock()
    monkeypatch.setattr(general_utils, "time", clock)

    # Act
    general_utils.pump_events_for(0.1, tick_seconds=0.03)

    # Assert: several pumps, and the UI is never frozen for more than one tick.
    assert calls["n"] >= 3
    assert clock.sleeps
    assert all(slice_len <= 0.03 for slice_len in clock.sleeps)
    assert sum(clock.sleeps) >= 0.1 - 0.03
