"""Unit tests for the Assembly Palette lazy thumbnail pump.

The palette used to ship every cached thumbnail inline with the gallery payload,
which meant a Recent list of a few hundred documents sent megabytes of data URIs
to paint a dozen visible cards -- and a document that had never been opened on
this machine had no thumbnail at all, because the only producer was
``Component.createThumbnail`` on a live design. The pump replaces that: the page
asks for the cards it actually shows, and anything not already cached is fetched
from the cloud through ``DataFile.thumbnail``.

That API returns a ``DataObjectFuture`` with no completion event, so the pump
polls it one custom-event tick at a time rather than blocking the UI thread.
These tests drive ``_pump_thumbs`` turn by turn with fake futures, covering the
states that actually occur: a download that finishes, one that fails (the
documented answer for "this DataFile has no thumbnail"), one that never settles,
and the back-pressure that keeps a single turn from spending too many cloud
round-trips.

``entry`` is imported via the ``PowerTools.*`` scaffolding in ``conftest.py``.
"""

import importlib

import pytest

entry = importlib.import_module("PowerTools.commands.assemblypalette.entry")

PROCESSING = entry._FUTURE_PROCESSING
FINISHED = entry._FUTURE_FINISHED
FAILED = 2  # adsk.core.FutureStates.FailedFutureState


class FakeFuture:
    """Stand-in for adsk.core.DataObjectFuture with a settable state."""

    def __init__(self, state=PROCESSING, data_object="obj"):
        self.state = state
        self.dataObject = data_object


class FakePalette:
    """Palette that records the setThumbs batches pushed to the page."""

    def __init__(self, visible=True):
        self.isVisible = visible
        self.sent = []

    def sendInfoToHTML(self, action, data):
        self.sent.append((action, data))
        return True


@pytest.fixture
def pump(monkeypatch):
    """Isolate the pump: empty state, no palette lookup, no real timer.

    Returns a namespace of the fakes the tests drive, so each test can decide
    what the cloud, the disk cache and the clock report.
    """
    entry._reset_thumb_pump()
    monkeypatch.setattr(entry, "_thumb_tick_pending", False)
    monkeypatch.setattr(entry, "_thumb_tick_scheduled_at", 0.0)

    palette = FakePalette()
    monkeypatch.setattr(
        entry.ui, "palettes", type("P", (), {"itemById": lambda self, _id: palette})()
    )

    # The timer is what makes the pump asynchronous in Fusion; tests step it by
    # calling _pump_thumbs directly, so scheduling only needs to be recorded.
    ticks = []
    monkeypatch.setattr(
        entry.threading,
        "Timer",
        lambda delay, fn: type(
            "T", (), {"daemon": False, "start": lambda self: ticks.append(delay)}
        )(),
    )

    clock = {"now": 0.0}
    monkeypatch.setattr(entry.time, "monotonic", lambda: clock["now"])

    # No document is open and nothing is on disk unless a test says otherwise.
    monkeypatch.setattr(entry, "_open_docs_by_data_file_id", dict)
    monkeypatch.setattr(entry.recents, "cached_thumbnail_data_url", lambda _id: "")

    yield type(
        "Pump",
        (),
        {
            "palette": palette,
            "ticks": ticks,
            "clock": clock,
            "monkeypatch": monkeypatch,
        },
    )()
    entry._reset_thumb_pump()


def _sent_thumbs(palette):
    """The setThumbs batches the palette received, decoded, newest last."""
    import json

    return [json.loads(data) for action, data in palette.sent if action == "setThumbs"]


# ---------------------------------------------------------------------------
# Serving from cache
# ---------------------------------------------------------------------------


def test_cached_ids_answer_immediately_without_queueing(pump):
    """A thumbnail already on disk goes back in the same turn, never queued."""
    pump.monkeypatch.setattr(
        entry.recents, "cached_thumbnail_data_url", lambda df_id: f"data:{df_id}"
    )
    entry._action_request_thumbs(pump.palette, {"ids": ["a", "b"]})

    assert _sent_thumbs(pump.palette) == [{"a": "data:a", "b": "data:b"}]
    assert entry._thumb_queue == []
    assert pump.ticks == []  # nothing to pump, so no tick armed


def test_open_document_is_rendered_locally_rather_than_downloaded(pump):
    """An open doc's thumbnail comes from a live render, not a cloud round-trip."""
    pump.monkeypatch.setattr(
        entry, "_open_docs_by_data_file_id", lambda: {"open1": "doc"}
    )
    pump.monkeypatch.setattr(
        entry.recents, "render_thumbnail_for_doc", lambda doc, df_id: f"live:{df_id}"
    )
    entry._action_request_thumbs(pump.palette, {"ids": ["open1"]})

    assert _sent_thumbs(pump.palette) == [{"open1": "live:open1"}]
    assert entry._thumb_queue == []


def test_uncached_ids_are_queued_and_arm_a_tick(pump):
    """Anything not available locally becomes queued work with a tick pending."""
    entry._action_request_thumbs(pump.palette, {"ids": ["x", "y"]})

    assert entry._thumb_queue == ["x", "y"]
    assert _sent_thumbs(pump.palette) == []
    assert pump.ticks == [entry._THUMB_TICK_SECONDS]


def test_repeat_requests_do_not_double_queue(pump):
    """The page may re-ask as cards scroll in and out; the queue stays deduped."""
    entry._action_request_thumbs(pump.palette, {"ids": ["x"]})
    entry._action_request_thumbs(pump.palette, {"ids": ["x", "x"]})

    assert entry._thumb_queue == ["x"]


def test_known_missing_ids_are_never_requeued(pump):
    """A document with no cloud thumbnail is not retried for the rest of the open."""
    entry._thumb_missing.add("nope")
    entry._action_request_thumbs(pump.palette, {"ids": ["nope"]})

    assert entry._thumb_queue == []
    assert _sent_thumbs(pump.palette) == []


# ---------------------------------------------------------------------------
# Pumping the queue
# ---------------------------------------------------------------------------


def test_pump_starts_downloads_up_to_the_per_tick_cap(pump):
    """findFileById is a cloud round-trip, so only a few start per turn."""
    started = []

    def fake_start(df_id):
        started.append(df_id)
        return FakeFuture()

    pump.monkeypatch.setattr(entry, "_start_thumb_download", fake_start)
    wanted = [f"id{i}" for i in range(entry._THUMB_START_PER_TICK + 2)]
    entry._action_request_thumbs(pump.palette, {"ids": wanted})

    entry._pump_thumbs()

    assert started == wanted[: entry._THUMB_START_PER_TICK]
    assert len(entry._thumb_inflight) == entry._THUMB_START_PER_TICK
    assert entry._thumb_queue == wanted[entry._THUMB_START_PER_TICK :]


def test_finished_future_is_stored_and_pushed_to_the_page(pump):
    """A settled download lands in the shared cache and reaches the page once."""
    future = FakeFuture(state=PROCESSING)
    pump.monkeypatch.setattr(entry, "_start_thumb_download", lambda _id: future)
    stored = []
    pump.monkeypatch.setattr(
        entry.recents,
        "store_thumbnail_object",
        lambda obj, df_id: stored.append((obj, df_id)) or f"/cache/{df_id}.png",
    )
    pump.monkeypatch.setattr(
        entry.recents, "png_to_data_url", lambda path: f"data:{path}"
    )

    entry._action_request_thumbs(pump.palette, {"ids": ["a"]})
    entry._pump_thumbs()  # starts the download
    assert _sent_thumbs(pump.palette) == []

    future.state = FINISHED
    entry._pump_thumbs()  # harvests it

    assert stored == [("obj", "a")]
    assert _sent_thumbs(pump.palette) == [{"a": "data:/cache/a.png"}]
    assert entry._thumb_inflight == {}


def test_failed_future_is_remembered_as_missing(pump):
    """FailedFutureState means 'no thumbnail exists' — record it, do not retry."""
    future = FakeFuture(state=FAILED)
    pump.monkeypatch.setattr(entry, "_start_thumb_download", lambda _id: future)

    entry._action_request_thumbs(pump.palette, {"ids": ["a"]})
    entry._pump_thumbs()
    entry._pump_thumbs()

    assert "a" in entry._thumb_missing
    assert _sent_thumbs(pump.palette) == []
    assert entry._thumb_inflight == {}


def test_unresolvable_data_file_is_remembered_as_missing(pump):
    """A DataFile that will not resolve is dropped rather than retried forever."""
    pump.monkeypatch.setattr(entry, "_start_thumb_download", lambda _id: None)

    entry._action_request_thumbs(pump.palette, {"ids": ["ghost"]})
    entry._pump_thumbs()

    assert entry._thumb_missing == {"ghost"}
    assert entry._thumb_inflight == {}


def test_wedged_future_is_abandoned_after_the_timeout(pump):
    """One download that never settles must not keep the pump ticking forever."""
    future = FakeFuture(state=PROCESSING)
    pump.monkeypatch.setattr(entry, "_start_thumb_download", lambda _id: future)

    entry._action_request_thumbs(pump.palette, {"ids": ["slow"]})
    entry._pump_thumbs()
    assert entry._thumb_inflight

    pump.clock["now"] += entry._THUMB_FUTURE_TIMEOUT_SECONDS + 1
    entry._pump_thumbs()

    assert entry._thumb_inflight == {}
    assert entry._thumb_missing == {"slow"}


def test_pump_stops_and_clears_when_the_palette_is_gone(pump):
    """Nobody is looking — abandon the queue instead of spending round-trips."""
    pump.monkeypatch.setattr(entry, "_start_thumb_download", lambda _id: FakeFuture())
    entry._action_request_thumbs(pump.palette, {"ids": ["a", "b"]})
    pump.palette.isVisible = False

    entry._pump_thumbs()

    assert entry._thumb_queue == []
    assert entry._thumb_inflight == {}


def test_pump_stops_arming_ticks_once_the_work_is_done(pump):
    """The tick chain ends with the queue, so an idle palette costs nothing."""
    future = FakeFuture(state=FINISHED)
    pump.monkeypatch.setattr(entry, "_start_thumb_download", lambda _id: future)
    pump.monkeypatch.setattr(
        entry.recents, "store_thumbnail_object", lambda obj, df_id: "/p.png"
    )
    pump.monkeypatch.setattr(entry.recents, "png_to_data_url", lambda path: "data:x")

    entry._action_request_thumbs(pump.palette, {"ids": ["a"]})
    entry._pump_thumbs()  # starts and (same future) settles immediately
    entry._pump_thumbs()  # harvests it; nothing left to do

    assert entry._thumb_queue == []
    assert entry._thumb_inflight == {}

    # With the queue drained, arming is a no-op however often it is asked for.
    idle = len(pump.ticks)
    entry._schedule_thumb_tick()
    entry._schedule_thumb_tick()
    assert len(pump.ticks) == idle


# ---------------------------------------------------------------------------
# Tick scheduling
# ---------------------------------------------------------------------------


def test_schedule_is_idempotent_while_a_tick_is_pending(pump):
    """Repeat requests share one pending tick rather than stacking timers."""
    entry._action_request_thumbs(pump.palette, {"ids": ["a"]})
    entry._action_request_thumbs(pump.palette, {"ids": ["b"]})
    entry._action_request_thumbs(pump.palette, {"ids": ["c"]})

    assert pump.ticks == [entry._THUMB_TICK_SECONDS]


def test_a_lost_tick_is_re_armed_once_it_goes_stale(pump):
    """fireCustomEvent can be lost; a stale pending flag must not wedge the pump."""
    entry._action_request_thumbs(pump.palette, {"ids": ["a"]})
    assert len(pump.ticks) == 1

    pump.clock["now"] += entry._THUMB_TICK_STALE_SECONDS + 0.1
    entry._schedule_thumb_tick()

    assert len(pump.ticks) == 2


def test_reset_clears_the_negative_cache_too(pump):
    """A reopened palette retries misses — Fusion may have generated one since."""
    entry._thumb_queue.append("a")
    entry._thumb_inflight["b"] = (FakeFuture(), 0.0)
    entry._thumb_missing.add("c")

    entry._reset_thumb_pump()

    assert entry._thumb_queue == []
    assert entry._thumb_inflight == {}
    assert entry._thumb_missing == set()
