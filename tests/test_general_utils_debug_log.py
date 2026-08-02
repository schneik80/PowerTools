"""Unit tests for the persistent debug log writer in ptAddInUtils.

Exercises the file-append path that backs ``ptutil.log`` when the .debug
marker is present: line format, directory creation, appending, and the
size cap. ``general_utils`` imports ``adsk`` (fabricated by the conftest
scaffolding) and reads config flags in a guarded try, so it imports
cleanly outside Fusion.
"""

import importlib
from pathlib import Path

PT_PKG = Path(__file__).resolve().parent.parent.name
general_utils = importlib.import_module(f"{PT_PKG}.lib.ptAddInUtils.general_utils")


def test_append_writes_timestamped_line(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(general_utils, "_CACHE_PATH", str(tmp_path))
    general_utils._append_debug_file("hello wire builder", None)
    log_file = tmp_path / "powertools-debug.log"
    assert log_file.exists()
    content = log_file.read_text(encoding="utf-8")
    assert "hello wire builder" in content
    assert "[INFO]" in content  # unknown level tags as INFO


def test_append_accumulates_lines(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(general_utils, "_CACHE_PATH", str(tmp_path))
    general_utils._append_debug_file("first", None)
    general_utils._append_debug_file("second", None)
    lines = (tmp_path / "powertools-debug.log").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert lines[0].endswith("first")
    assert lines[1].endswith("second")


def test_append_creates_missing_cache_dir(tmp_path, monkeypatch) -> None:
    nested = tmp_path / "not-yet-created"
    monkeypatch.setattr(general_utils, "_CACHE_PATH", str(nested))
    general_utils._append_debug_file("made the directory", None)
    assert (nested / "powertools-debug.log").exists()


def test_size_cap_restarts_the_file(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(general_utils, "_CACHE_PATH", str(tmp_path))
    monkeypatch.setattr(general_utils, "_DEBUG_LOG_MAX_BYTES", 10)
    general_utils._append_debug_file("this line pushes the file over the cap", None)
    general_utils._append_debug_file("fresh start", None)
    content = (tmp_path / "powertools-debug.log").read_text(encoding="utf-8")
    assert "fresh start" in content
    assert "pushes the file" not in content  # truncated, not appended


def test_no_cache_path_is_a_noop(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(general_utils, "_CACHE_PATH", "")
    general_utils._append_debug_file("goes nowhere", None)  # must not raise
    assert list(tmp_path.iterdir()) == []
