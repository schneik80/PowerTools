# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.
#
# Build README.pdf from README.md via pandoc + xelatex, then check the result.
#
# Dev tooling only: this never runs inside Fusion. It shells out to pandoc and
# MiKTeX rather than importing anything third party, so it needs no installs
# beyond those two.
#
# README.pdf is a checked-in artifact that ships in the release zip, so it goes
# stale the moment README.md changes. Every build stamps a hash of the Markdown
# into the PDF's Subject metadata, which lets `--check` answer 'does this PDF
# match this README?' by reading the two files alone - no pandoc, no xelatex,
# and no git history. That is what makes the check cheap enough for CI to run on
# every push (.github/workflows/ci.yml) and for the release build to enforce
# before zipping (tools/release/build_release.py).

from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import subprocess
import sys
import tempfile
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]

# Order matters only for readability; the two filters are independent.
FILTERS = ("hr-to-pagebreak.lua", "table-widths.lua")

# Set every table one size down from body text (10pt -> 9pt). The command
# tables carry ~90 wrapped lines of description between them, so a single step
# reclaims far more vertical space than trimming prose can, and it is what keeps
# the Commands section inside its page budget. etoolbox patches the environment
# rather than us redefining longtable ourselves. Column widths are fractions of
# \linewidth, so they are unaffected - only the wrapping gets tighter.
TABLE_SIZE = r"\usepackage{etoolbox}\AtBeginEnvironment{longtable}{\small}"

# Marks the Subject metadata as ours, so a PDF built by some other route (or by
# an older copy of this script) reads as unstamped rather than as a hash miss.
STAMP_PREFIX = "readme-sha256:"

# Kept here rather than in a template so the whole recipe is in one place.
STYLE_OPTIONS = (
    "-V",
    "geometry:margin=0.9in",
    "-V",
    "colorlinks=true",
    "-V",
    "linkcolor=RoyalBlue",
    "-V",
    "urlcolor=RoyalBlue",
    "-V",
    "fontsize=10pt",
    "-V",
    f"header-includes={TABLE_SIZE}",
)

# MiKTeX installs per-user and is not always on PATH.
_EXTRA_TOOL_DIRS = (
    Path.home() / "AppData/Local/Programs/MiKTeX/miktex/bin/x64",
    Path("C:/Program Files/Pandoc"),
)


def find_tool(name: str) -> Path:
    """Locate an executable on PATH, falling back to known install roots.

    Args:
        name: Executable name without extension, e.g. ``pandoc``.

    Returns:
        Absolute path to the executable.

    Raises:
        FileNotFoundError: If the tool cannot be found anywhere.
    """
    found = shutil.which(name)
    if found:
        return Path(found)
    for folder in _EXTRA_TOOL_DIRS:
        candidate = folder / f"{name}.exe"
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        f"{name} not found on PATH or in {[str(d) for d in _EXTRA_TOOL_DIRS]}"
    )


def source_digest(source: Path) -> str:
    """Hash the Markdown source that a build is made from.

    Args:
        source: Markdown input.

    Returns:
        Hex SHA-256 of the file's bytes.
    """
    return hashlib.sha256(source.read_bytes()).hexdigest()


def _stamp_options(source: Path) -> list[str]:
    """Pandoc options that record *source*'s hash in the PDF's Subject field.

    pandoc's LaTeX template feeds the ``subject`` variable to hyperref's
    ``pdfsubject``, which is metadata only - it never renders on the page.

    Args:
        source: Markdown input.

    Returns:
        A ``-V subject=...`` option pair.
    """
    return ["-V", f"subject={STAMP_PREFIX}{source_digest(source)}"]


def _filter_args() -> list[str]:
    args: list[str] = []
    for name in FILTERS:
        path = HERE / name
        if not path.is_file():
            raise FileNotFoundError(f"missing pandoc filter: {path}")
        args += ["--lua-filter", str(path)]
    return args


def build(source: Path, target: Path) -> None:
    """Run pandoc to produce *target* from *source*.

    Args:
        source: Markdown input.
        target: PDF to write.

    Raises:
        RuntimeError: If pandoc exits non-zero or emits any warning. Pandoc is
            silent on a clean run, so anything on stderr is worth stopping for.
    """
    pandoc = find_tool("pandoc")
    result = subprocess.run(
        [
            str(pandoc),
            str(source),
            "-f",
            "gfm",
            "-o",
            str(target),
            "--pdf-engine=xelatex",
            *_filter_args(),
            *STYLE_OPTIONS,
            *_stamp_options(source),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    noise = (result.stdout + result.stderr).strip()
    if result.returncode != 0 or noise:
        raise RuntimeError(f"pandoc failed (exit {result.returncode}):\n{noise}")


def _inflated_objects(pdf: Path) -> bytes:
    """Return every deflate-compressed stream in *pdf*, inflated and joined.

    xelatex writes PDF 1.7, where the page tree and the document info dictionary
    both live inside compressed object streams - so scanning the raw bytes for
    them finds nothing and silently reports success.

    Args:
        pdf: PDF file to inspect.

    Returns:
        The concatenated inflated streams; empty if none could be inflated.
    """
    raw = pdf.read_bytes()
    chunks: list[bytes] = []
    for match in re.finditer(rb"stream\r?\n", raw):
        start = match.end()
        end = raw.find(b"endstream", start)
        if end == -1:
            continue
        try:
            chunks.append(zlib.decompress(raw[start:end]))
        except zlib.error:
            continue  # not every stream is deflate-compressed
    return b"\n".join(chunks)


def pdf_page_count(pdf: Path) -> int:
    """Count pages in *pdf*.

    Args:
        pdf: PDF file to inspect.

    Returns:
        Number of pages found.
    """
    return len(re.findall(rb"/Type\s*/Page[^s]", _inflated_objects(pdf)))


def _decode_pdf_string(raw: bytes, hexed: bool) -> str:
    """Decode a PDF string object's bytes to text.

    Args:
        raw: The bytes between the delimiters.
        hexed: True for a ``<...>`` hex string, False for a ``(...)`` literal.

    Returns:
        The decoded text, empty if the bytes are malformed.
    """
    if hexed:
        try:
            raw = bytes.fromhex(raw.decode("ascii"))
        except ValueError:
            return ""
    # xdvipdfmx writes non-trivial strings as UTF-16BE behind a byte-order mark;
    # anything else is PDFDocEncoding, which agrees with latin-1 over the hex
    # digits a stamp is made of.
    if raw.startswith(b"\xfe\xff"):
        return raw[2:].decode("utf-16-be", errors="replace")
    return raw.decode("latin-1", errors="replace")


def read_stamp(pdf: Path) -> str | None:
    """Read back the source hash a build stamped into *pdf*.

    Args:
        pdf: PDF file to inspect.

    Returns:
        The hex digest recorded at build time, or None when *pdf* carries no
        stamp (it predates stamping, or was not built by this script).
    """
    objects = _inflated_objects(pdf)
    for pattern, hexed in (
        (rb"/Subject\s*<([^>]*)>", True),
        (rb"/Subject\s*\(([^)]*)\)", False),
    ):
        match = re.search(pattern, objects)
        if not match:
            continue
        value = _decode_pdf_string(match.group(1), hexed)
        if value.startswith(STAMP_PREFIX):
            return value[len(STAMP_PREFIX) :]
    return None


def staleness(source: Path, target: Path) -> str | None:
    """Say whether *target* still corresponds to *source*.

    Compares the hash stamped into the PDF at build time against the Markdown
    on disk, so this needs neither the pandoc toolchain nor git history - it is
    exact even in a shallow clone or a dirty working tree.

    Args:
        source: Markdown input.
        target: PDF that should have been built from it.

    Returns:
        A human-readable reason the PDF is out of date, or None if it is
        current.

    Raises:
        FileNotFoundError: If *source* does not exist.
    """
    if not source.is_file():
        raise FileNotFoundError(f"missing Markdown source: {source}")
    if not target.is_file():
        return f"{target.name} does not exist"
    stamped = read_stamp(target)
    if stamped is None:
        return f"{target.name} carries no source stamp - rebuild it once to add one"
    if stamped != source_digest(source):
        return f"{target.name} was built from a different {source.name}"
    return None


def audit(source: Path) -> tuple[int, int]:
    """Typeset *source* standalone to count layout defects.

    pandoc hides the engine log, so this rebuilds through xelatex directly.
    It runs the engine **twice**: LaTeX resolves cross-references from the aux
    file on the second pass, so a single pass reports every internal link as
    undefined and the count is meaningless.

    Args:
        source: Markdown input.

    Returns:
        ``(overfull_boxes, undefined_references)``. Overfull boxes are content
        past the margin; undefined references are broken internal links.
    """
    pandoc = find_tool("pandoc")
    xelatex = find_tool("xelatex")
    with tempfile.TemporaryDirectory() as work_name:
        work = Path(work_name)
        tex = work / "audit.tex"
        subprocess.run(
            [
                str(pandoc),
                str(source),
                "-f",
                "gfm",
                "-s",
                "-o",
                str(tex),
                *_filter_args(),
                *STYLE_OPTIONS,
                *_stamp_options(source),
            ],
            capture_output=True,
            check=True,
        )
        for _ in range(2):
            subprocess.run(
                [str(xelatex), "-interaction=nonstopmode", tex.name],
                cwd=work,
                capture_output=True,
                check=False,
            )
        log = (work / "audit.log").read_text(encoding="utf-8", errors="replace")
    return log.count("Overfull"), log.count("Hyper reference")


def main() -> int:
    """Build the PDF and report on it."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", type=Path, default=REPO_ROOT / "README.md", help="Markdown input"
    )
    parser.add_argument(
        "--target", type=Path, default=REPO_ROOT / "README.pdf", help="PDF to write"
    )
    parser.add_argument(
        "--skip-audit",
        action="store_true",
        help="Skip the xelatex re-run that counts overfull boxes and broken links",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--check",
        action="store_true",
        help=(
            "Report whether the PDF matches the Markdown and exit non-zero if "
            "not, without building. Needs no pandoc or xelatex."
        ),
    )
    mode.add_argument(
        "--if-stale",
        action="store_true",
        help="Build only when the PDF no longer matches the Markdown",
    )
    args = parser.parse_args()

    try:
        reason = staleness(args.source, args.target)
    except FileNotFoundError as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1

    if args.check:
        if reason:
            print(f"STALE: {reason}", file=sys.stderr)
            print(
                "Rebuild it with: python tools/pandoc/build_readme_pdf.py",
                file=sys.stderr,
            )
            return 1
        print(f"  current: {args.target.name} matches {args.source.name}")
        return 0

    if args.if_stale and not reason:
        print(f"  current: {args.target.name} matches {args.source.name}, not rebuilt")
        return 0

    try:
        build(args.source, args.target)
    except (FileNotFoundError, RuntimeError) as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1

    pages = pdf_page_count(args.target)
    size = args.target.stat().st_size
    print(f"  wrote  : {args.target.relative_to(REPO_ROOT)}")
    print(f"  pages  : {pages}")
    print(f"  size   : {size:,} bytes")

    if args.skip_audit:
        return 0

    overfull, undefined = audit(args.source)
    print(f"  overfull boxes      : {overfull}")
    print(f"  undefined refs      : {undefined}")
    return 1 if (overfull or undefined) else 0


if __name__ == "__main__":
    raise SystemExit(main())
