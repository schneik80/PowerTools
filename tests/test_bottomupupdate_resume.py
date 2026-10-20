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


def test_analyze_resume_state_resumes_past_the_last_document(tmp_path):
    """Every document checkpointed but the run unfinished resumes at the end.

    A crash during the root save leaves exactly this state, and it is a valid
    resume: the loop has nothing left and only the root phase remains. It also
    made the command unlaunchable once, because the progress dialog was handed
    this index as both its minimum and its maximum.
    """
    # Arrange
    log_path = _write_log(
        tmp_path,
        "\n".join(
            [
                "Fusion client version: 2.0.1",
                "",
                "Bottom-up order:",
                "docA|A",
                "docB|B",
                "",
                "Document save log:",
                "CHECKPOINT|SAVE_UPLOAD_COMPLETE|doc_id=docA|component=A|saved_index=1|total=2",
                "CHECKPOINT|SAVE_UPLOAD_COMPLETE|doc_id=docB|component=B|saved_index=2|total=2",
            ]
        ),
    )
    current_ids = ["docA", "docB"]

    # Act
    result = entry._analyze_resume_state(log_path, "2.0.1", current_ids)

    # Assert
    assert result["should_resume"] is True
    assert result["resume_start_index"] == len(current_ids)
    assert result["last_saved_index"] == 2


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


# --- crash suspects -----------------------------------------------------------
#
# Both 2026-10-20 crashes (ADSKMVG91G2F5W, pre-production) faulted natively
# inside updateAllReferences on the same document, and the second one was the
# resume re-opening the document the first one died on. OPEN_BEGIN is written
# before every open so the next resume can recognise that document.


def _open(doc_id, name):
    return f"CHECKPOINT|OPEN_BEGIN|doc_id={doc_id}|component={name}|timestamp=t"


def _saved(doc_id, name, index):
    return (
        f"CHECKPOINT|SAVE_UPLOAD_COMPLETE|doc_id={doc_id}|component={name}"
        f"|saved_index={index}|total=3"
    )


def test_extract_crash_suspects_flags_open_with_nothing_after_it():
    """An OPEN_BEGIN that is the last checkpoint of the log is a suspect."""
    # Arrange: docA saved, docB opened, then silence (the crash).
    log_lines = [_saved("docA", "A", 1), _open("docB", "B"), "Opened component: B"]

    # Act
    suspects = entry._extract_crash_suspects(log_lines)

    # Assert
    assert suspects == [{"doc_id": "docB", "name": "B"}]


def test_extract_crash_suspects_ignores_opens_that_reached_a_checkpoint():
    """A later checkpoint of any kind clears the pending open."""
    # Arrange: saved, open-failed, save-failed, and the root checkpoint all follow
    # an OPEN_BEGIN; none of them is a crash.
    log_lines = [
        _open("docA", "A"),
        _saved("docA", "A", 1),
        _open("docB", "B"),
        "CHECKPOINT|OPEN_FAILED|doc_id=docB|component=B",
        _open("docC", "C"),
        "CHECKPOINT|SAVE_FAILED|doc_id=docC|component=C",
        _open("docD", "D"),
        "CHECKPOINT|SAVE_UPLOAD_COMPLETE|component=main assembly|saved_index=1|total=3",
    ]

    # Act / Assert
    assert entry._extract_crash_suspects(log_lines) == []


def test_extract_crash_suspects_next_open_clears_the_previous_one():
    """A second OPEN_BEGIN means the first document finished without a checkpoint."""
    # Arrange
    log_lines = [_open("docA", "A"), _open("docB", "B")]

    # Act / Assert: only docB is still pending at the end.
    assert entry._extract_crash_suspects(log_lines) == [{"doc_id": "docB", "name": "B"}]


def test_extract_crash_suspects_survives_a_resume_that_died_on_the_same_document():
    """Two attempts ending on the same document yield one suspect."""
    # Arrange: exactly the 2026-10-20 shape.
    log_lines = [
        _saved("docA", "A", 1),
        _open("docB", "B"),
        entry.RESUME_ATTEMPT_MARKER,
        "Resume available. Processing will continue after the last saved document.",
        _open("docB", "B"),
    ]

    # Act / Assert
    assert entry._extract_crash_suspects(log_lines) == [{"doc_id": "docB", "name": "B"}]


def test_extract_crash_suspects_keeps_a_skipped_suspect_across_attempts():
    """A suspect the next attempt skipped stays a suspect for the one after."""
    # Arrange: attempt 1 dies on docB; attempt 2 skips it and saves docC.
    log_lines = [
        _open("docB", "B"),
        entry.RESUME_ATTEMPT_MARKER,
        _open("docC", "C"),
        _saved("docC", "C", 1),
    ]

    # Act / Assert
    assert entry._extract_crash_suspects(log_lines) == [{"doc_id": "docB", "name": "B"}]


def test_extract_crash_suspects_drops_a_suspect_a_later_attempt_saved():
    """A retried suspect that saved is no longer a suspect."""
    # Arrange
    log_lines = [
        _open("docB", "B"),
        entry.RESUME_ATTEMPT_MARKER,
        _open("docB", "B"),
        _saved("docB", "B", 1),
    ]

    # Act / Assert
    assert entry._extract_crash_suspects(log_lines) == []


def test_extract_crash_suspects_completion_line_clears_pending():
    """The completion marker ends the run cleanly."""
    # Arrange
    log_lines = [_open("docB", "B"), "Bottom-up Update completed successfully"]

    # Act / Assert
    assert entry._extract_crash_suspects(log_lines) == []


def test_analyze_resume_state_reports_suspects_and_still_resumes(tmp_path):
    """A resumable log that died on docB resumes after docA and names docB."""
    # Arrange
    body = _resumable_log() + "\n" + _open("docB", "B") + "\nOpened component: B"
    log_path = _write_log(tmp_path, body)

    # Act
    result = entry._analyze_resume_state(log_path, "2.0.1", ["docA", "docB", "docC"])

    # Assert
    assert result["should_resume"] is True
    assert result["resume_start_index"] == 1
    assert result["crash_suspects"] == [{"doc_id": "docB", "name": "B"}]
    assert "B" in result["status_message"]
    assert "will be skipped" in result["status_message"]


def test_analyze_resume_state_suspect_without_any_checkpoint_restarts_as_resume(
    tmp_path,
):
    """A run that died on its first document restarts from 0 but keeps the log."""
    # Arrange: no SAVE_UPLOAD_COMPLETE at all, one dangling OPEN_BEGIN.
    body = "\n".join(
        [
            "Fusion client version: 2.0.1",
            "",
            "Bottom-up order:",
            "docA|A",
            "docB|B",
            "",
            "Document save log:",
            _open("docA", "A"),
        ]
    )
    log_path = _write_log(tmp_path, body)

    # Act
    result = entry._analyze_resume_state(log_path, "2.0.1", ["docA", "docB"])

    # Assert: should_resume keeps the log in append mode so OPEN_BEGIN survives.
    assert result["should_resume"] is True
    assert result["resume_start_index"] == 0
    assert result["last_saved_index"] == 0
    assert result["crash_suspects"] == [{"doc_id": "docA", "name": "A"}]


def test_analyze_resume_state_ignores_suspects_not_in_the_current_order(tmp_path):
    """A suspect that left the assembly is not reported."""
    # Arrange: the order still matches (docA..docC) but the dangling open names docZ.
    body = _resumable_log() + "\n" + _open("docZ", "Z")
    log_path = _write_log(tmp_path, body)

    # Act
    result = entry._analyze_resume_state(log_path, "2.0.1", ["docA", "docB", "docC"])

    # Assert
    assert result["crash_suspects"] == []
    assert "skipped" not in result["status_message"]
