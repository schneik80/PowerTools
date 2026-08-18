"""Unit tests for the post-insert chain in ``assemblypalette/entry.py``.

A palette insert is only ``addByInsert`` -- the import and commit half of what
Fusion's own Insert Component does -- so ``_finish_insert_like_fusion`` adds the
select, fit and position steps, ending in **Edit Initial Position** instead of
Move/Copy. Fusion ships two definitions with the same label
(``FusionDcEditInitialPositionCommand`` and ``FusionEditInitialPositionCommand``),
and *neither* reports ``isEnabled`` True even when the command is startable, so
the routing decides by observing ``execute()`` and ``ui.activeCommand`` rather
than by asking. Pure routing logic, tested with fakes; ``entry`` is imported via
the ``PowerTools.*`` scaffolding in ``conftest.py``.
"""

import importlib

import pytest

entry = importlib.import_module("PowerTools.commands.assemblypalette.entry")

DC_ID, PLAIN_ID = entry._EDIT_POSITION_CMD_IDS

# What Fusion reports while no real command is running.
IDLE = "SelectCommand"


class FakeControlDefinition:
    """Stand-in for the command definition's control definition."""

    def __init__(self, is_enabled=True):
        self.isEnabled = is_enabled


class FakeCommandDefinition:
    """Stand-in for adsk.core.CommandDefinition that records execute() calls.

    ``starts`` models whether the command actually comes up: on execute() a
    starting definition becomes the fake ui's activeCommand, a non-starting one
    leaves it idle -- which is exactly how Fusion behaves for a command that
    quietly declines.
    """

    def __init__(self, is_enabled=False, raises=False, starts=True, returns=True):
        self.controlDefinition = FakeControlDefinition(is_enabled)
        self.execute_calls = 0
        self._raises = raises
        self._starts = starts
        self._returns = returns
        self._ui = None
        self._cmd_id = None

    def bind(self, fake_ui, cmd_id):
        """Wire the definition to the fake ui it will make itself active on."""
        self._ui = fake_ui
        self._cmd_id = cmd_id

    def execute(self):
        self.execute_calls += 1
        if self._raises:
            raise RuntimeError("Fusion refused the command")
        if self._starts and self._ui is not None:
            self._ui.activeCommand = self._cmd_id
        return self._returns


class FakeSelections:
    """Stand-in for ui.activeSelections, recording what the chain selected.

    ``add`` returns a bool in the real API, so ``add_returns=False`` models a
    selection that fails without raising.
    """

    def __init__(self, add_raises=False, add_returns=True):
        self.added = []
        self.clear_calls = 0
        self._add_raises = add_raises
        self._add_returns = add_returns

    def clear(self):
        self.clear_calls += 1
        return True

    def add(self, entity):
        if self._add_raises:
            raise RuntimeError("selection rejected")
        self.added.append(entity)
        return self._add_returns


class FakeViewport:
    """Stand-in for app.activeViewport, counting fit() calls."""

    def __init__(self, raises=False):
        self.fit_calls = 0
        self._raises = raises

    def fit(self):
        self.fit_calls += 1
        if self._raises:
            raise RuntimeError("no viewport")


class FakeOccurrence:
    """Stand-in for the inserted Occurrence.

    ``isVaildForEditInitialPosition`` carries the typo the Fusion API itself
    ships with; ``valid=None`` models a build that does not expose it at all, and
    ``raises=True`` a property that blows up rather than answering.
    """

    def __init__(self, valid=True, grounded=True, raises=False):
        self._raises = raises
        if raises:
            return  # leave every flag unset so __getattr__ answers instead
        if valid is not None:
            self.isVaildForEditInitialPosition = valid
        self.isGroundToParent = grounded

    def __getattr__(self, name):
        if self._raises:
            raise RuntimeError(f"{name} unavailable")
        raise AttributeError(name)


class FakeUI:
    """Stand-in for entry's module-level ``ui``.

    ``activeCommand`` starts idle and is moved by whichever fake definition
    actually starts, so the routing sees the same evidence Fusion gives it.
    """

    def __init__(self, definitions, selections, looked_up, active_raises=False):
        self._definitions = definitions
        self._looked_up = looked_up
        self._active_raises = active_raises
        self.activeSelections = selections
        self._active_command = IDLE
        self.commandDefinitions = self

    def itemById(self, cmd_id):
        self._looked_up.append(cmd_id)
        return self._definitions.get(cmd_id)

    @property
    def activeCommand(self):
        if self._active_raises:
            raise RuntimeError("activeCommand not exposed on this build")
        return self._active_command

    @activeCommand.setter
    def activeCommand(self, value):
        self._active_command = value


def _install_ui(monkeypatch, definitions, selections=None, active_raises=False):
    """Point entry's module-level ``ui`` at a fake resolving *definitions*.

    Returns the list of ids the chain looked up, so a test can assert the order
    the two Edit Initial Position variants were tried in.
    """
    looked_up = []
    fake_ui = FakeUI(
        definitions,
        selections if selections is not None else FakeSelections(),
        looked_up,
        active_raises,
    )
    for cmd_id, cmd_def in definitions.items():
        cmd_def.bind(fake_ui, cmd_id)
    monkeypatch.setattr(entry, "ui", fake_ui)
    return looked_up


def _install_app(monkeypatch, viewport=None, fired=True, fire_raises=False):
    """Point entry's module-level ``app`` at a fake viewport + customEvent pair.

    Returns the list of event ids fired, so a test can assert the insert queued
    the chain rather than running it inline.
    """
    fired_ids = []

    class FakeApp:
        activeViewport = viewport if viewport is not None else FakeViewport()

        def fireCustomEvent(self, event_id):
            fired_ids.append(event_id)
            if fire_raises:
                raise RuntimeError("event not registered")
            return fired

    monkeypatch.setattr(entry, "app", FakeApp())
    return fired_ids


class FakeTimer:
    """Stand-in for threading.Timer that never actually runs on a thread."""

    def __init__(self, interval, function):
        self.interval = interval
        self.function = function
        self.daemon = None
        self.started = False

    def start(self):
        self.started = True


def _capture_timers(monkeypatch):
    """Replace threading.Timer with FakeTimer, returning the list of timers made."""
    timers = []

    def _make(interval, function):
        timer = FakeTimer(interval, function)
        timers.append(timer)
        return timer

    monkeypatch.setattr(entry.threading, "Timer", _make)
    return timers


@pytest.fixture(autouse=True)
def _silence_log(monkeypatch):
    """Keep the chain's per-step logs out of the test output."""
    monkeypatch.setattr(entry.ptutil, "log", lambda *a, **k: None)


@pytest.fixture(autouse=True)
def _skip_event_pump(monkeypatch):
    """The real pump waits ~0.4s per command probe; nothing to wait for here."""
    monkeypatch.setattr(entry.ptutil, "pump_events_for", lambda *a, **k: None)


@pytest.fixture(autouse=True)
def _clear_pending():
    """The pending occurrence is module state — never leak it between tests."""
    entry._pending_finish = None
    yield
    entry._pending_finish = None


def test_dc_variant_is_preferred(monkeypatch):
    """When the Dc variant starts, the plain one is never touched."""
    # Arrange
    dc = FakeCommandDefinition()
    plain = FakeCommandDefinition()
    looked_up = _install_ui(monkeypatch, {DC_ID: dc, PLAIN_ID: plain})

    # Act
    entry._start_edit_initial_position()

    # Assert
    assert dc.execute_calls == 1
    assert plain.execute_calls == 0
    assert looked_up == [DC_ID]


def test_disabled_flag_does_not_block_execute(monkeypatch):
    """isEnabled False is not a veto — Fusion reports it for a startable command.

    Both Edit Initial Position definitions report False even with a valid selected
    occurrence, because they live only in the marking menus. Gating on it skipped
    both ids and left the insert with no follow-up at all.
    """
    # Arrange
    dc = FakeCommandDefinition(is_enabled=False)
    plain = FakeCommandDefinition()
    _install_ui(monkeypatch, {DC_ID: dc, PLAIN_ID: plain})

    # Act
    entry._start_edit_initial_position()

    # Assert
    assert dc.execute_calls == 1
    assert plain.execute_calls == 0


def test_missing_dc_variant_falls_back(monkeypatch):
    """A build without the Dc definition still gets a position dialog."""
    # Arrange
    plain = FakeCommandDefinition()
    looked_up = _install_ui(monkeypatch, {PLAIN_ID: plain})

    # Act
    entry._start_edit_initial_position()

    # Assert
    assert plain.execute_calls == 1
    assert looked_up == [DC_ID, PLAIN_ID]


def test_silently_declined_dc_variant_falls_back(monkeypatch):
    """A command that never becomes active is a no-op — try the other id."""
    # Arrange
    dc = FakeCommandDefinition(starts=False)
    plain = FakeCommandDefinition()
    _install_ui(monkeypatch, {DC_ID: dc, PLAIN_ID: plain})

    # Act
    entry._start_edit_initial_position()

    # Assert
    assert dc.execute_calls == 1
    assert plain.execute_calls == 1
    assert entry.ui.activeCommand == PLAIN_ID


def test_unreadable_active_command_trusts_execute(monkeypatch):
    """Without activeCommand to observe, execute()'s own answer decides.

    Firing the second id on top of a command that already started would be worse
    than trusting it.
    """
    # Arrange
    dc = FakeCommandDefinition(returns=True)
    plain = FakeCommandDefinition()
    _install_ui(monkeypatch, {DC_ID: dc, PLAIN_ID: plain}, active_raises=True)

    # Act
    entry._start_edit_initial_position()

    # Assert
    assert dc.execute_calls == 1
    assert plain.execute_calls == 0


def test_unreadable_active_command_falls_back_on_false(monkeypatch):
    """Same blind case, but execute() said no — the other id gets its turn."""
    # Arrange
    dc = FakeCommandDefinition(returns=False)
    plain = FakeCommandDefinition()
    _install_ui(monkeypatch, {DC_ID: dc, PLAIN_ID: plain}, active_raises=True)

    # Act
    entry._start_edit_initial_position()

    # Assert
    assert dc.execute_calls == 1
    assert plain.execute_calls == 1


def test_raising_dc_variant_falls_back(monkeypatch):
    """A definition that rejects execute() must not swallow the other one."""
    # Arrange
    dc = FakeCommandDefinition(raises=True)
    plain = FakeCommandDefinition()
    _install_ui(monkeypatch, {DC_ID: dc, PLAIN_ID: plain})

    # Act
    entry._start_edit_initial_position()

    # Assert
    assert dc.execute_calls == 1
    assert plain.execute_calls == 1


def test_no_definition_available_is_tolerated(monkeypatch):
    """The component is already inserted, so an unavailable dialog only logs."""
    # Arrange
    looked_up = _install_ui(monkeypatch, {})

    # Act / Assert: no raise
    entry._start_edit_initial_position()
    assert looked_up == [DC_ID, PLAIN_ID]


def test_chain_selects_fits_then_positions(monkeypatch):
    """The full chain replays Fusion's select → fit → position order."""
    # Arrange
    dc = FakeCommandDefinition()
    selections = FakeSelections()
    viewport = FakeViewport()
    _install_ui(monkeypatch, {DC_ID: dc}, selections)
    _install_app(monkeypatch, viewport)
    occurrence = FakeOccurrence()

    # Act
    entry._finish_insert_like_fusion(occurrence)

    # Assert
    assert selections.clear_calls == 1
    assert selections.added == [occurrence]
    assert viewport.fit_calls == 1
    assert dc.execute_calls == 1


def test_invalid_occurrence_skips_the_dialog(monkeypatch):
    """Fusion refuses the edit for some occurrences — do not open the dialog."""
    # Arrange
    dc = FakeCommandDefinition()
    viewport = FakeViewport()
    _install_ui(monkeypatch, {DC_ID: dc})
    _install_app(monkeypatch, viewport)

    # Act
    entry._finish_insert_like_fusion(FakeOccurrence(valid=False))

    # Assert: still framed, but no position command.
    assert viewport.fit_calls == 1
    assert dc.execute_calls == 0


def test_unreported_validity_still_positions(monkeypatch):
    """A build that does not expose the flag leaves the call to Fusion."""
    # Arrange
    dc = FakeCommandDefinition()
    _install_ui(monkeypatch, {DC_ID: dc})
    _install_app(monkeypatch)

    # Act
    entry._finish_insert_like_fusion(FakeOccurrence(valid=None))

    # Assert
    assert dc.execute_calls == 1


def test_chain_selects_once_and_starts_nothing_else(monkeypatch):
    """When nothing comes up, the chain reports it — it does not try other commands.

    An earlier diagnostic build escalated to a timeline-node retry and a Move/Copy
    control; both are gone, so a failure must leave the model and the selection
    exactly as the insert left them.
    """
    # Arrange: neither Edit Initial Position id ever comes up.
    dc = FakeCommandDefinition(starts=False)
    plain = FakeCommandDefinition(starts=False)
    selections = FakeSelections()
    _install_ui(monkeypatch, {DC_ID: dc, PLAIN_ID: plain}, selections)
    _install_app(monkeypatch)

    # Act
    occurrence = FakeOccurrence()
    entry._finish_insert_like_fusion(occurrence)

    # Assert: one id each, one selection, nothing else touched.
    assert dc.execute_calls == 1
    assert plain.execute_calls == 1
    assert selections.added == [occurrence]


def test_raising_flag_properties_do_not_stop_the_dialog(monkeypatch):
    """A property that blows up instead of answering is read as "unknown"."""
    # Arrange
    dc = FakeCommandDefinition()
    _install_ui(monkeypatch, {DC_ID: dc})
    _install_app(monkeypatch)

    # Act
    entry._finish_insert_like_fusion(FakeOccurrence(raises=True))

    # Assert
    assert dc.execute_calls == 1


def test_failed_select_and_fit_do_not_stop_the_dialog(monkeypatch):
    """Each step degrades on its own — the position dialog still opens."""
    # Arrange
    dc = FakeCommandDefinition()
    _install_ui(monkeypatch, {DC_ID: dc}, FakeSelections(add_raises=True))
    _install_app(monkeypatch, FakeViewport(raises=True))

    # Act
    entry._finish_insert_like_fusion(FakeOccurrence())

    # Assert
    assert dc.execute_calls == 1


def test_schedule_delays_the_fire_off_the_event_turn(monkeypatch):
    """The fire is delayed on a worker thread, not made inside the HTML event.

    Firing inline let Fusion dispatch the handler in the same turn, and the command
    it started was torn down when the HTML event finished.
    """
    # Arrange
    dc = FakeCommandDefinition()
    _install_ui(monkeypatch, {DC_ID: dc})
    fired_ids = _install_app(monkeypatch)
    timers = _capture_timers(monkeypatch)
    occurrence = FakeOccurrence()

    # Act
    entry._schedule_finish_insert(occurrence)

    # Assert: queued for later, nothing fired or run yet.
    assert entry._pending_finish is occurrence
    assert fired_ids == []
    assert dc.execute_calls == 0
    assert len(timers) == 1
    assert timers[0].interval == entry._FINISH_DELAY_SECONDS
    assert timers[0].daemon is True
    assert timers[0].started

    # Act: let the timer come due.
    timers[0].function()

    # Assert: now the main thread has been handed the work.
    assert fired_ids == [entry._FINISH_EVENT_ID]
    assert entry._pending_finish is occurrence


def test_false_return_still_leaves_the_occurrence_pending(monkeypatch):
    """A False return does not mean the event was skipped.

    Fusion returns False from ``fireCustomEvent`` and then fires the event anyway
    (observed in cache/powertools-debug.log). Clearing the pending occurrence on
    that return is what made an earlier attempt look dead: the handler ran on time
    and found nothing to work on.
    """
    # Arrange
    _install_ui(monkeypatch, {})
    _install_app(monkeypatch, fired=False)
    timers = _capture_timers(monkeypatch)
    occurrence = FakeOccurrence()

    # Act
    entry._schedule_finish_insert(occurrence)
    timers[0].function()

    # Assert
    assert entry._pending_finish is occurrence


def test_raising_fire_keeps_the_worker_thread_quiet(monkeypatch):
    """A fire that raises must not escape onto the timer thread.

    Nothing on that thread may touch the Fusion API — including ptutil.log — so the
    failure is swallowed there and the handler does the reporting.
    """
    # Arrange
    _install_ui(monkeypatch, {})
    _install_app(monkeypatch, fire_raises=True)
    timers = _capture_timers(monkeypatch)

    # Act / Assert: no raise reaches the caller.
    entry._schedule_finish_insert(FakeOccurrence())
    timers[0].function()
