"""Unit tests for the id-based resume/log parsing in ``bottomupupdate/entry.py``.

These helpers are pure text parsing, so they are tested directly (imported as
``PowerTools.commands.bottomupupdate.entry`` via the ``conftest.py``
scaffolding). They are the trickiest part of the document-id migration: the
bottom-up order is logged as ``doc_id|name`` lines and checkpoints now carry a
``doc_id`` field, and resume decisions must key on the stable id.
"""

import importlib

entry = importlib.import_module("PowerTools.commands.bottomupupdate.entry")


def test_extract_latest_bottom_up_order_returns_doc_ids():
    """The order section is parsed to its stable doc_id column."""
    # Arrange: a later section supersedes an earlier one.
    log_lines = [
        "Bottom-up order:",
        "old1|Old",
        "",
        "Bottom-up order:",
        "docA|Bracket",
        "docB|Bushing",
        "Document save log:",
        "CHECKPOINT|SAVE_UPLOAD_COMPLETE|doc_id=docA|component=Bracket|saved_index=1",
    ]

    # Act
    order = entry._extract_latest_bottom_up_order(log_lines)

    # Assert: latest section only, doc_ids not names.
    assert order == ["docA", "docB"]


def test_extract_last_checkpoint_reads_doc_id_and_skips_main_assembly():
    """The last per-document checkpoint wins; the main-assembly one is ignored."""
    # Arrange: two document checkpoints then the final main-assembly checkpoint.
    log_lines = [
        "CHECKPOINT|SAVE_UPLOAD_COMPLETE|doc_id=docA|component=A|saved_index=1|total=3",
        "CHECKPOINT|SAVE_UPLOAD_COMPLETE|doc_id=docB|component=B|saved_index=2|total=3",
        "CHECKPOINT|SAVE_UPLOAD_COMPLETE|component=main assembly|saved_index=2|total=3",
    ]

    # Act
    last_doc_id, last_saved_index = entry._extract_last_checkpoint(log_lines)

    # Assert: the main-assembly line has no doc_id and is skipped.
    assert last_doc_id == "docB"
    assert last_saved_index == 2


def _write_log(tmp_path, body):
    """Write ``body`` to a temp log file and return its path."""
    path = tmp_path / "assembly.log"
    path.write_text(body, encoding="utf-8")
    return str(path)


def _resumable_log(version="2.0.1"):
    """Return a log body for a run that stopped after saving docA."""
    return "\n".join(
        [
            f"Fusion client version: {version}",
            "",
            "Bottom-up order:",
            "docA|A",
            "docB|B",
            "docC|C",
            "",
            "Document save log:",
            "CHECKPOINT|SAVE_UPLOAD_COMPLETE|doc_id=docA|component=A|saved_index=1|total=3",
        ]
    )


def test_analyze_resume_state_resumes_after_last_saved_document(tmp_path):
    """A matching, incomplete run resumes at the document after the last saved."""
    # Arrange
    log_path = _write_log(tmp_path, _resumable_log())
    current_ids = ["docA", "docB", "docC"]

    # Act
    result = entry._analyze_resume_state(log_path, "2.0.1", current_ids)

    # Assert: resume from index 1 (docB), carrying the last saved count.
    assert result["should_resume"] is True
    assert result["dag_matches"] is True
    assert result["resume_start_index"] == 1
    assert result["resume_doc_id"] == "docA"
    assert result["last_saved_index"] == 1


def test_analyze_resume_state_full_run_when_doc_order_changed(tmp_path):
    """A changed document id list forces a full run, never a bad resume."""
    # Arrange: the logged order no longer matches the current graph.
    log_path = _write_log(tmp_path, _resumable_log())
    current_ids = ["docA", "docX", "docC"]

    # Act
    result = entry._analyze_resume_state(log_path, "2.0.1", current_ids)

    # Assert
    assert result["dag_matches"] is False
    assert result["should_resume"] is False


def test_analyze_resume_state_full_run_on_version_mismatch(tmp_path):
    """A log from another Fusion client version is not resumed."""
    # Arrange
    log_path = _write_log(tmp_path, _resumable_log(version="1.0.0"))

    # Act
    result = entry._analyze_resume_state(log_path, "2.0.1", ["docA", "docB", "docC"])

    # Assert
    assert result["matches_version"] is False
    assert result["should_resume"] is False


def test_analyze_resume_state_clears_after_completed_run(tmp_path):
    """A previously completed run signals a log reset rather than a resume."""
    # Arrange
    body = _resumable_log() + "\nBottom-up Update completed successfully"
    log_path = _write_log(tmp_path, body)

    # Act
    result = entry._analyze_resume_state(log_path, "2.0.1", ["docA", "docB", "docC"])

    # Assert
    assert result["completed_successfully"] is True
    assert result["clear_log"] is True
    assert result["should_resume"] is False
