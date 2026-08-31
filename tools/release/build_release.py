# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.
#
# Build an end-user release zip of the PowerTools add-in.
#
# Dev tooling only: this never runs inside Fusion. It uses only the standard
# library plus the `git` CLI, so it works locally and in the release workflow
# (.github/workflows/release.yml) without any installs. The one exception is a
# stale README.pdf, which needs pandoc and xelatex to regenerate - CI keeps the
# checked-in PDF current so that path stays cold. See refresh_readme_pdf.
#
# The file list comes from `git ls-files`, so everything git-ignored (.debug,
# .env, .claude/, caches, venvs, settings/preferences.json, generated palette
# init.js, ...) is stripped by construction. On top of that, tracked dev-only
# paths (tests, tools, CI config, architecture docs, design sources) are
# excluded below. What remains is exactly what an end user needs to run the
# add-in, zipped under a top-level `PowerTools/` folder so extracting into
# Fusion's AddIns directory yields a correctly named add-in folder.

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]

# The add-in folder name Fusion requires (also the zip's top-level folder).
ADDIN_NAME = "PowerTools"

# README.pdf ships in the zip but is a checked-in artifact, so it goes stale
# whenever README.md changes. This script refreshes it before zipping.
PDF_BUILDER = HERE.parent / "pandoc" / "build_readme_pdf.py"

# Tracked directories that are dev-only. Matched as path prefixes.
EXCLUDED_DIRS = (
    "tests/",
    "tools/",
    ".github/",
    "docs/arch/",
    "docs/dev/",
)

# Tracked individual files that are dev-only or must not ship. `hub.json` is
# the stale root copy carrying org-specific hub IDs; the live one the add-in
# reads is cache/hub.json (git-ignored, per-machine).
EXCLUDED_FILES = (
    ".gitignore",
    ".git-blame-ignore-revs",
    "pyproject.toml",
    "hub.json",
)

# Design sources checked in next to runtime resources. fnmatch patterns.
EXCLUDED_GLOBS = (
    "commands/*/resources/generate_icons.py",
    "commands/*/resources/*.idraw",
    "commands/*/resources/*.pxd/*",
    "commands/*/resources/fusion_icon_resources.zip",
    "commands/*/resources/fusion_icon_resources/*",
)

# Machine-local state that is git-ignored and therefore should never appear in
# `git ls-files` output. If one of these shows up anyway (e.g. a .gitignore
# regression let it get committed), abort the build rather than ship it:
# .debug enables verbose logging plus a debugpy listener on the user's machine,
# and settings/preferences.json carries a developer's accumulated preferences
# instead of new-install defaults.
FORBIDDEN_FILES = (
    ".debug",
    ".env",
    "settings/preferences.json",
)


def refresh_readme_pdf(repo_root: Path) -> None:
    """Bring README.pdf up to date with README.md before it gets zipped.

    Nothing else regenerates the shipped PDF, so without this a release can
    carry a PDF that disagrees with the Markdown next to it - which is exactly
    what happened between b41923d and b5946ea.

    A PDF that already matches costs one subprocess and needs no toolchain;
    only a stale one shells out to pandoc and xelatex. CI gates staleness on
    every push (.github/workflows/ci.yml), so the release runner should never
    reach the rebuild path - and if it does on a machine without the toolchain,
    the build aborts rather than quietly shipping the stale PDF.

    Args:
        repo_root: Repository root containing README.md and README.pdf.

    Raises:
        RuntimeError: If the PDF is out of date and cannot be rebuilt, or if
            the rebuild reports a layout defect.
    """
    result = subprocess.run(
        [sys.executable, str(PDF_BUILDER), "--if-stale"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stdout + result.stderr).strip()
        raise RuntimeError(
            "Refusing to build a release: README.pdf is out of date and could "
            f"not be rebuilt.\n{detail}"
        )
    print(result.stdout.strip())


def tracked_files(repo_root: Path) -> list[str]:
    """Return the repo's git-tracked file paths (forward-slash, repo-relative).

    Args:
        repo_root: Repository root directory to run git in.

    Returns:
        Repo-relative POSIX-style paths, one per tracked file.

    Raises:
        subprocess.CalledProcessError: If git is missing or the command fails.
    """
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=repo_root,
        capture_output=True,
        check=True,
    )
    return [path for path in result.stdout.decode("utf-8").split("\0") if path]


def is_excluded(path: str) -> bool:
    """Return True if a tracked path is dev-only and must not ship.

    Args:
        path: Repo-relative POSIX-style file path.

    Returns:
        True when the path matches an excluded directory, file, or pattern.
    """
    if path.startswith(EXCLUDED_DIRS):
        return True
    if path in EXCLUDED_FILES:
        return True
    return any(fnmatch.fnmatch(path, pattern) for pattern in EXCLUDED_GLOBS)


def release_files(paths: list[str]) -> list[str]:
    """Filter tracked paths down to the shippable set, sorted for determinism.

    Args:
        paths: Repo-relative tracked file paths.

    Returns:
        Sorted paths that belong in the release zip.

    Raises:
        RuntimeError: If a forbidden machine-local file (e.g. ``.debug`` or
            ``settings/preferences.json``) appears in the tracked set.
    """
    forbidden = sorted(set(paths) & set(FORBIDDEN_FILES))
    if forbidden:
        raise RuntimeError(
            "Refusing to build a release: forbidden machine-local files are "
            f"git-tracked: {', '.join(forbidden)}. Untrack them and restore "
            "their .gitignore entries first."
        )
    return sorted(path for path in paths if not is_excluded(path))


def manifest_version(repo_root: Path) -> str:
    """Read the add-in version from ``PowerTools.manifest``.

    Args:
        repo_root: Repository root containing the manifest.

    Returns:
        The manifest's ``version`` string.

    Raises:
        KeyError: If the manifest has no ``version`` field.
    """
    manifest = json.loads(
        (repo_root / f"{ADDIN_NAME}.manifest").read_text(encoding="utf-8")
    )
    return manifest["version"]


def normalize_version(version: str) -> str:
    """Strip a leading ``v`` from a release tag (``v1.2.0`` -> ``1.2.0``).

    Args:
        version: Version label or git tag.

    Returns:
        The version without a ``v``/``V`` tag prefix; other strings unchanged.
    """
    return re.sub(r"^[vV](?=\d)", "", version)


def release_manifest(manifest_text: str, version: str) -> str:
    """Stamp the shipped manifest with the release version and lock editing.

    ``editEnabled: false`` marks the add-in as non-editable in Fusion's
    Add-Ins dialog, which is what a distributed build should be.

    Args:
        manifest_text: The repo manifest's JSON text.
        version: Release version to stamp into the ``version`` field.

    Returns:
        Manifest JSON text with ``version`` replaced and ``editEnabled``
        set to false; all other fields and key order preserved.
    """
    manifest = json.loads(manifest_text)
    manifest["version"] = version
    manifest["editEnabled"] = False
    return json.dumps(manifest, indent="\t", ensure_ascii=False) + "\n"


def build_zip(repo_root: Path, out_path: Path, files: list[str], version: str) -> None:
    """Write the release zip with every entry under a ``PowerTools/`` prefix.

    The manifest is not copied verbatim: it is stamped via
    :func:`release_manifest` so the shipped add-in reports the release
    version and is not editable. The repo's manifest file is untouched.

    Args:
        repo_root: Repository root the file paths are relative to.
        out_path: Destination zip path; parent directories are created.
        files: Repo-relative paths to include, already filtered and sorted.
        version: Release version stamped into the shipped manifest.
    """
    manifest_name = f"{ADDIN_NAME}.manifest"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            if path == manifest_name:
                stamped = release_manifest(
                    (repo_root / path).read_text(encoding="utf-8"), version
                )
                archive.writestr(f"{ADDIN_NAME}/{path}", stamped)
            else:
                archive.write(repo_root / path, arcname=f"{ADDIN_NAME}/{path}")


def main(argv: list[str] | None = None) -> int:
    """Build ``dist/PowerTools-<version>.zip`` from the git-tracked tree.

    Args:
        argv: CLI arguments; defaults to ``sys.argv[1:]``.

    Returns:
        Process exit code (0 on success).
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--version",
        default=None,
        help=(
            "Version label for the zip filename (the release workflow passes "
            "the release tag). Defaults to the PowerTools.manifest version."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "dist",
        help="Directory to write the zip into (default: <repo>/dist).",
    )
    args = parser.parse_args(argv)

    version = normalize_version(args.version or manifest_version(REPO_ROOT))
    # Before the file list is taken, so a rebuilt PDF is the one that ships.
    refresh_readme_pdf(REPO_ROOT)
    files = release_files(tracked_files(REPO_ROOT))
    out_path = args.output_dir / f"{ADDIN_NAME}-{version}.zip"

    build_zip(REPO_ROOT, out_path, files, version)

    size_kib = out_path.stat().st_size / 1024
    print(f"Wrote {out_path} ({len(files)} files, {size_kib:.0f} KiB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
