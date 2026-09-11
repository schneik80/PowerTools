"""Regression tests for the Externalize per-component upload spin.

``_save_to_cloud`` runs a tight ``adsk.doEvents()`` spin on
``DataFileFuture.uploadState`` -- deliberately, because Fusion's upload pipeline
does not drain if the loop sleeps between polls (forum 11164467). It is a fork
of ``ptutil.upload_utils._wait_via_upload_state`` and originally dropped that
helper's timeout, so a future Fusion left in ``UploadProcessing`` spun forever:
a 75-component run wedged on component 34 and was still spinning 430s later with
no way for the user to stop it (``DataFileFuture`` has no abort and the run's
status-bar progress bar has no cancel affordance).

These tests pin the two bounds added in response: the per-upload deadline, and
the consecutive-failure circuit breaker that stops the run from spending the
full deadline on every component that is left.

``entry`` imports ``adsk`` at module scope, so it is loaded via its full package
path with the conftest scaffolding in place.
"""

import importlib
from pathlib import Path

import adsk.core

PT_PKG = Path(__file__).resolve().parent.parent.name
entry = importlib.import_module(f"{PT_PKG}.commands.externalize.entry")

PROCESSING = adsk.core.UploadStates.UploadProcessing
FINISHED = adsk.core.UploadStates.UploadFinished


class FakeFuture:
    """Stand-in for adsk.core.DataFileFuture (only uploadState + dataFile)."""

    def __init__(self, states):
        self._states = list(states)
        self.dataFile = "cloud-file"

    @property
    def uploadState(self):
        # Last state repeats forever, mirroring a future Fusion never advances.
        return self._states.pop(0) if len(self._states) > 1 else self._states[0]


class FakeComponent:
    def __init__(self, future):
        self._future = future
        self.calls = 0

    def saveCopyAs(self, _name, _folder, _desc, _tag):
        self.calls += 1
        return self._future


class FakeClock:
    """Monotonic clock that advances a fixed step on every read."""

    def __init__(self, step=1.0):
        self.now = 0.0
        self.step = step

    def __call__(self):
        self.now += self.step
        return self.now


def _run(monkeypatch, states, timeout_seconds=300.0, step=1.0):
    monkeypatch.setattr(entry.time, "monotonic", FakeClock(step))
    lines = []
    component = FakeComponent(FakeFuture(states))
    result = entry._save_to_cloud(
        component, "PART-1", object(), lines.append, timeout_seconds
    )
    return result, lines


def test_wedged_upload_gives_up_at_the_deadline(monkeypatch):
    """A future stuck in UploadProcessing must not spin forever."""
    result, lines = _run(monkeypatch, [PROCESSING], timeout_seconds=300.0)

    assert result is None
    assert any("TIMED OUT" in line for line in lines)


def test_timeout_is_honoured_and_not_merely_bounded(monkeypatch):
    """The deadline is the configured value, not an arbitrary iteration cap."""
    _, lines = _run(monkeypatch, [PROCESSING], timeout_seconds=30.0, step=1.0)

    timed_out = [line for line in lines if "TIMED OUT" in line]
    assert len(timed_out) == 1
    # Clock steps 1s per read; the deadline check reads once per iteration.
    assert "after 30s" in timed_out[0]


def test_healthy_upload_still_returns_its_datafile(monkeypatch):
    """The bound must not disturb the normal path."""
    result, lines = _run(monkeypatch, [PROCESSING, PROCESSING, FINISHED])

    assert result == "cloud-file"
    assert not any("TIMED OUT" in line for line in lines)


def test_timeout_disabled_when_non_positive(monkeypatch):
    """timeout_seconds <= 0 keeps the old unbounded behaviour for callers that
    explicitly ask for it -- guarded here so the check cannot be inverted."""
    result, _ = _run(monkeypatch, [PROCESSING, FINISHED], timeout_seconds=0)

    assert result == "cloud-file"


def test_upload_timeout_matches_the_shared_helper_default():
    """The fork must not drift below the helper it was copied from."""
    from PowerTools.lib.ptAddInUtils import upload_utils

    assert entry.UPLOAD_TIMEOUT_SECONDS == upload_utils.DEFAULT_UPLOAD_TIMEOUT_SECONDS


def test_circuit_breaker_threshold_is_small_enough_to_matter():
    """Two failures x 300s is the worst case before a wedged run gives up; a
    larger threshold would reintroduce a multi-hour hang on a big assembly."""
    assert 1 < entry.MAX_CONSECUTIVE_UPLOAD_FAILURES <= 3
