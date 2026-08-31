"""Unit tests for ``tools/pandoc/build_readme_pdf.py``.

The script has no ``adsk`` dependency, so it is loaded directly from its file
path (same pattern as ``test_release_build.py``). Tests cover the source-hash
stamp that ties a built PDF to its Markdown, reading that stamp back out of a
PDF's compressed object streams, and the staleness verdict built on top of it.
Neither pandoc nor xelatex is invoked - PDFs are synthesised in ``tmp_path``.
"""

import hashlib
import importlib.util
import zlib
from pathlib import Path

import pytest

_SCRIPT_PATH = (
    Path(__file__).resolve().parent.parent / "tools" / "pandoc" / "build_readme_pdf.py"
)
_spec = importlib.util.spec_from_file_location("pt_build_readme_pdf", _SCRIPT_PATH)
readme_pdf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(readme_pdf)


def _pdf_with_objects(payload: bytes) -> bytes:
    """Wrap *payload* in a deflate stream shaped like xelatex's output."""
    return (
        b"%PDF-1.7\n7 0 obj\n<</Type/ObjStm>>\nstream\n"
        + zlib.compress(payload)
        + b"\nendstream\nendobj\n%%EOF\n"
    )


def _hex_string(text: str) -> bytes:
    """Encode *text* the way xdvipdfmx writes it: UTF-16BE behind a BOM."""
    return b"<feff" + text.encode("utf-16-be").hex().encode("ascii") + b">"


def _stamped_pdf(path: Path, digest: str, *, literal: bool = False) -> Path:
    """Write a synthetic PDF whose Subject carries *digest*."""
    stamp = f"{readme_pdf.STAMP_PREFIX}{digest}"
    value = f"({stamp})".encode("latin-1") if literal else _hex_string(stamp)
    path.write_bytes(_pdf_with_objects(b"<</Producer(test)/Subject" + value + b">>"))
    return path


def test_source_digest_hashes_file_bytes(tmp_path: Path) -> None:
    """The stamp is a plain SHA-256 of the Markdown's bytes."""
    source = tmp_path / "README.md"
    source.write_bytes(b"# Title\n")

    assert readme_pdf.source_digest(source) == hashlib.sha256(b"# Title\n").hexdigest()


def test_stamp_options_carry_the_digest(tmp_path: Path) -> None:
    """The build passes the digest to pandoc as a ``subject`` variable."""
    source = tmp_path / "README.md"
    source.write_text("# Title\n", encoding="utf-8")

    options = readme_pdf._stamp_options(source)

    assert options[0] == "-V"
    assert (
        options[1]
        == f"subject={readme_pdf.STAMP_PREFIX}{readme_pdf.source_digest(source)}"
    )


@pytest.mark.parametrize("literal", [False, True])
def test_read_stamp_round_trips(tmp_path: Path, literal: bool) -> None:
    """A stamp survives both PDF string encodings pandoc engines emit."""
    digest = "a" * 64
    pdf = _stamped_pdf(tmp_path / "README.pdf", digest, literal=literal)

    assert readme_pdf.read_stamp(pdf) == digest


def test_read_stamp_ignores_a_foreign_subject(tmp_path: Path) -> None:
    """A Subject written by something else is not mistaken for a stamp."""
    pdf = tmp_path / "README.pdf"
    pdf.write_bytes(
        _pdf_with_objects(b"<</Subject" + _hex_string("quarterly report") + b">>")
    )

    assert readme_pdf.read_stamp(pdf) is None


def test_read_stamp_returns_none_when_unstamped(tmp_path: Path) -> None:
    """A PDF built before stamping existed reads as unstamped, not mismatched."""
    pdf = tmp_path / "README.pdf"
    pdf.write_bytes(_pdf_with_objects(b"<</Producer(xdvipdfmx)>>"))

    assert readme_pdf.read_stamp(pdf) is None


def test_staleness_accepts_a_matching_pdf(tmp_path: Path) -> None:
    """A PDF stamped with the current source's hash is current."""
    source = tmp_path / "README.md"
    source.write_text("# Title\n", encoding="utf-8")
    pdf = _stamped_pdf(tmp_path / "README.pdf", readme_pdf.source_digest(source))

    assert readme_pdf.staleness(source, pdf) is None


def test_staleness_flags_an_edited_source(tmp_path: Path) -> None:
    """Editing the Markdown after a build makes the PDF stale."""
    source = tmp_path / "README.md"
    source.write_text("# Title\n", encoding="utf-8")
    pdf = _stamped_pdf(tmp_path / "README.pdf", readme_pdf.source_digest(source))
    source.write_text("# Title\n\nA new command.\n", encoding="utf-8")

    assert (
        readme_pdf.staleness(source, pdf)
        == "README.pdf was built from a different README.md"
    )


def test_staleness_flags_an_unstamped_pdf(tmp_path: Path) -> None:
    """An unstamped PDF cannot be vouched for, so it counts as stale."""
    source = tmp_path / "README.md"
    source.write_text("# Title\n", encoding="utf-8")
    pdf = tmp_path / "README.pdf"
    pdf.write_bytes(_pdf_with_objects(b"<</Producer(xdvipdfmx)>>"))

    assert "no source stamp" in readme_pdf.staleness(source, pdf)


def test_staleness_flags_a_missing_pdf(tmp_path: Path) -> None:
    """A PDF that was never built is stale rather than an error."""
    source = tmp_path / "README.md"
    source.write_text("# Title\n", encoding="utf-8")

    assert readme_pdf.staleness(source, tmp_path / "README.pdf") == (
        "README.pdf does not exist"
    )


def test_staleness_rejects_a_missing_source(tmp_path: Path) -> None:
    """A missing Markdown source is a caller error, not a staleness verdict."""
    with pytest.raises(FileNotFoundError, match="missing Markdown source"):
        readme_pdf.staleness(tmp_path / "README.md", tmp_path / "README.pdf")


def test_repo_readme_pdf_is_current() -> None:
    """The checked-in PDF matches the checked-in Markdown.

    This is the same gate CI runs; having it in pytest means a README edit
    fails locally too, before it reaches the release build.
    """
    repo_root = Path(__file__).resolve().parent.parent

    assert (
        readme_pdf.staleness(repo_root / "README.md", repo_root / "README.pdf") is None
    )
