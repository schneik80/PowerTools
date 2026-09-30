"""Fusion probe: does opening and closing a document inside a command event fault?

Informs the fix for Assign Drawing Number and Version Diff (rule 6, 11cfc51):
both open a second document invisibly inside ``command_execute`` and close it
before the handler returns. This script reproduces that pattern in isolation,
plus the two candidate replacements, so the decision rests on what Fusion does
today rather than on a two-year-old crash report.

Run it as a *script* from Utilities > Add-Ins > Scripts (not as an add-in),
on BOTH channels of ADSKMVG91G2F5W and g16win.local, with a saved design
active whose folder holds at least one other saved design.

Each mode writes a marker line (flushed) to ``pt_close_probe.log`` on the
desktop before and after every risky call. If Fusion dies natively, the last
marker in the file tells you exactly which call killed it; the crash report
lands where .agent/environment.md says.

Modes, run one at a time (edit MODE below, or answer the prompt):
  A  open + close inside command_execute            -- what the two commands do today
  B  open + close inside commandCreated             -- the no-inputs shortcut (rule 1)
  C  execute records the DataFile only; a Timer -> custom event opens + closes
     after the command is destroyed                 -- the proposed fix
  D  as C, but pumps ptutil-style (adsk.doEvents for 250 ms) after the close
     and re-acquires the parent document, checking isValid  -- rule 3 shape
  E  VISIBLE open (documents.open(df, True)) + close inside command_execute
                                                    -- what Version Diff does
  F  as E, but pumps 250 ms between the open and the close, and re-activates
     the parent first                               -- what Bottom-Up Update does

Expected verdicts to record per (device, channel, mode):
  OK          -- both markers present, Fusion alive, parent document isValid
  EXCEPTION   -- Python traceback in the log (copy it)
  NATIVE      -- Fusion gone; last marker names the call
"""

import os
import threading
import traceback

import adsk.core
import adsk.fusion

MODE = None  # None -> ask; or "A" .. "F"

_app = adsk.core.Application.get()
_ui = _app.userInterface
_handlers = []
_CMD_ID = "PT_probe_closeInExecute"
_EVENT_ID = "PT_probe_closeInExecute_deferred"
_LOG = os.path.join(os.path.expanduser("~"), "Desktop", "pt_close_probe.log")
_pending = {}


def _mark(msg):
    line = f"[{MODE}] {msg}"
    _app.log(line)
    with open(_LOG, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def _pick_other_design():
    """First other saved design in the active document's folder, or None."""
    doc = _app.activeDocument
    if doc is None or not doc.isSaved:
        return None
    me = doc.dataFile
    folder = me.parentFolder
    for i in range(folder.dataFiles.count):
        df = folder.dataFiles.item(i)
        if df.id != me.id and df.fileExtension == "f3d":
            return df
    return None


def _pump(seconds):
    import time

    end = time.monotonic() + seconds
    while time.monotonic() < end:
        adsk.doEvents()


def _open_and_close(df, where):
    """The risky pair, instrumented. Returns the opened document's name.

    Modes E and F open VISIBLY; F also re-activates the parent and pumps
    before the close, which is the shape Bottom-Up Update has run in
    production for years.
    """
    visible = MODE in ("E", "F")
    parent = _app.activeDocument
    _mark(f"{where}: before open({df.name!r}, visible={visible})")
    other = _app.documents.open(df, visible)
    _mark(f"{where}: after open -> {other.name!r}")
    if MODE == "F":
        _mark(f"{where}: re-activating parent {parent.name!r}, pumping 250 ms")
        parent.activate()
        _pump(0.25)
    _mark(f"{where}: before close(False)")
    other.close(False)
    _mark(f"{where}: after close")
    return df.name


def _check_parent(where):
    doc = _app.activeDocument
    ok = doc is not None and doc.isValid
    _mark(
        f"{where}: parent re-acquired, isValid={ok}, name={getattr(doc, 'name', None)!r}"
    )


class _Deferred(adsk.core.CustomEventHandler):
    def notify(self, args):
        try:
            df = _pending.pop("df", None)
            if df is None:
                _mark("deferred: nothing pending")
                return
            _open_and_close(df, "deferred")
            if MODE == "D":
                _mark("deferred: pumping 250 ms")
                _pump(0.25)
            _check_parent("deferred")
            _mark("DONE")
        except Exception:
            _mark("deferred EXCEPTION\n" + traceback.format_exc())
        finally:
            _finish()


class _Created(adsk.core.CommandCreatedEventHandler):
    def notify(self, args):
        try:
            cmd = args.command
            df = _pick_other_design()
            if df is None:
                _mark("no other saved design in this folder -- nothing to test")
                _finish()
                return
            _mark(f"commandCreated: target {df.name!r}")
            # Register destroy first so every mode terminates through it; a
            # no-inputs command with no execute handler still gets destroyed.
            on_destroy = _Destroy()
            cmd.destroy.add(on_destroy)
            _handlers.append(on_destroy)
            if MODE == "B":
                _open_and_close(df, "commandCreated")
                _check_parent("commandCreated")
                _mark("DONE")
                return
            on_exec = _Execute(df)
            cmd.execute.add(on_exec)
            _handlers.append(on_exec)
        except Exception:
            _mark("commandCreated EXCEPTION\n" + traceback.format_exc())
            _finish()


class _Execute(adsk.core.CommandEventHandler):
    def __init__(self, df):
        super().__init__()
        self._df = df

    def notify(self, args):
        try:
            if MODE in ("A", "E", "F"):
                _open_and_close(self._df, "execute")
                _check_parent("execute")
                _mark("DONE")
            else:  # C, D: record only, fire later
                _pending["df"] = self._df
                _mark("execute: recorded DataFile, deferring")
        except Exception:
            _mark("execute EXCEPTION\n" + traceback.format_exc())


class _Destroy(adsk.core.CommandEventHandler):
    def notify(self, args):
        _mark("destroy")
        if MODE in ("C", "D") and "df" in _pending:
            # Off the main thread only fireCustomEvent is allowed (rule 7).
            threading.Timer(0.3, lambda: _app.fireCustomEvent(_EVENT_ID)).start()
        elif MODE in ("A", "B", "E", "F"):
            _finish()


def _finish():
    try:
        _app.unregisterCustomEvent(_EVENT_ID)
    except Exception:
        pass
    cd = _ui.commandDefinitions.itemById(_CMD_ID)
    if cd:
        cd.deleteMe()
    _mark("probe finished; terminating script")
    adsk.terminate()


def run(context):
    global MODE
    try:
        if MODE is None:
            res, cancelled = _ui.inputBox(
                "Probe mode: A-F", "Close-in-execute probe", "A"
            )
            if cancelled:
                return
            MODE = res.strip().upper()[:1]
        adsk.autoTerminate(False)
        _mark(f"start; build={_app.version}; log={_LOG}")
        ev = _app.registerCustomEvent(_EVENT_ID)
        h = _Deferred()
        ev.add(h)
        _handlers.append(h)
        cd = _ui.commandDefinitions.itemById(_CMD_ID)
        if cd:
            cd.deleteMe()
        cd = _ui.commandDefinitions.addButtonDefinition(
            _CMD_ID, "Close-in-execute probe", ""
        )
        on_created = _Created()
        cd.commandCreated.add(on_created)
        _handlers.append(on_created)
        cd.execute()
    except Exception:
        _mark("run EXCEPTION\n" + traceback.format_exc())
        _finish()
