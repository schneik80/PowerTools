# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.
#
# Point the editor debug config at the latest fully-deployed Fusion build.
#
# Dev tooling only: this never runs inside Fusion, imports nothing third party,
# and only rewrites two git-ignored files (`.env` and `.zed/settings.json`).
#
# Why this exists. Fusion installs into
# `<webdeploy>/<channel>/<hash>/`, and every auto-update rotates the hash. The
# debug setup needs two absolute paths out of that tree - the `adsk` packages
# for `PYTHONPATH` and the bundled interpreter for the language server - so both
# configs go stale on their own, silently: a dead `PYTHONPATH` yields no import
# error, just unresolved stubs and breakpoints that never trip.
#
# The trap that makes this more than a `ls | tail -1`: most hash directories are
# *partial*. webdeploy keeps incremental delta payloads next to the real thing,
# and they look plausible from the outside (they have an `Autodesk Fusion.app`
# with a `Contents/`). Only a few carry the full `Api/Python` subtree. On
# 2026-09-03 `pre-production` held 8 hash directories and exactly one was
# complete, while both `.env` and `.zed/settings.json` pointed at a partial one.
# So "latest" has to mean "latest that is actually complete", which is why this
# validates both artifacts before considering a build a candidate.
#
# A hash is also not unique to a channel (`8d5cf31c...` currently appears under
# both `production/` and `pre-production/`), so the channel must be chosen
# explicitly rather than inferred from a hash.
#
# Layout support: the macOS layout is verified. The Windows layout is probed
# from a candidate list and this script has never been run there - if none of
# the candidates match it fails loudly and asks for the real layout rather than
# writing a guess into your config.

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import sys
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]

# `meta` holds webdeploy's own bookkeeping, not a Fusion build.
SKIP_CHANNELS = frozenset({"meta"})

# Candidate webdeploy roots, probed in order (never hardcode one - af05499).
WEBDEPLOY_CANDIDATES = (
    "~/Library/Application Support/Autodesk/webdeploy",  # macOS (verified)
    "~/AppData/Local/Autodesk/webdeploy",  # Windows, unverified
    "~/AppData/Roaming/Autodesk/webdeploy",  # Windows, unverified
)

# Where the `adsk` packages sit, relative to an app root. First match wins.
API_RELS = (
    "Contents/Api/Python/packages",  # macOS (verified)
    "Api/Python/packages",  # Windows / older layouts, unverified
)

# Where the bundled interpreter sits, relative to an app root. First match wins.
PYTHON_RELS = (
    "Contents/Frameworks/Python.framework/Versions/Current/bin/python",  # macOS
    "Contents/Frameworks/Python.framework/Versions/Current/bin/python3",
    "Python/python.exe",  # Windows, unverified
    "python.exe",
)


@dataclass(frozen=True)
class Build:
    """One fully-populated Fusion deployment."""

    channel: str
    build_hash: str
    app_root: Path
    api_packages: Path
    python_bin: Path
    mtime: float
    version: str

    @property
    def label(self) -> str:
        return f"{self.channel}/{self.build_hash[:12]}"


def find_webdeploy_root() -> Path:
    """First existing webdeploy root, or exit with what was tried."""
    tried = []
    for candidate in WEBDEPLOY_CANDIDATES:
        path = Path(candidate).expanduser()
        tried.append(str(path))
        if path.is_dir():
            return path
    sys.exit(
        "No Fusion webdeploy folder found. Tried:\n  "
        + "\n  ".join(tried)
        + f"\n\nPlatform: {platform.platform()}\n"
        "If Fusion is installed somewhere else, add the path to "
        "WEBDEPLOY_CANDIDATES in this script."
    )


def app_roots(build_dir: Path) -> list[Path]:
    """Bundles inside a build dir, or the dir itself on non-bundle platforms."""
    bundles = sorted(build_dir.glob("*.app"))
    return bundles or [build_dir]


def _first_existing(root: Path, rels: tuple[str, ...], want_dir: bool) -> Path | None:
    for rel in rels:
        path = root / rel
        if path.is_dir() if want_dir else path.is_file():
            return path
    return None


def read_version(app_root: Path) -> str:
    """Fusion's version from Info.plist, or '?' if it cannot be read.

    Parsed with a regex rather than `plistlib` so a Windows layout with no
    Info.plist degrades to '?' instead of raising. Cosmetic either way - the
    version is only printed, never used to choose a build.
    """
    plist = app_root / "Contents" / "Info.plist"
    if not plist.is_file():
        return "?"
    try:
        text = plist.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "?"
    match = re.search(
        r"<key>CFBundleShortVersionString</key>\s*<string>([^<]+)</string>", text
    )
    return match.group(1) if match else "?"


def discover(webdeploy: Path) -> dict[str, list[Build]]:
    """Populated builds per channel, newest first.

    A build counts as populated only when both artifacts the debug config needs
    are present - the `adsk` packages *and* the interpreter. Partial delta
    payloads pass a shallower check and are what this exists to filter out.
    """
    found: dict[str, list[Build]] = {}
    for channel_dir in sorted(p for p in webdeploy.iterdir() if p.is_dir()):
        channel = channel_dir.name
        if channel in SKIP_CHANNELS:
            continue
        builds: list[Build] = []
        for build_dir in channel_dir.iterdir():
            # Channel roots hold a launcher bundle beside the hash dirs.
            if not build_dir.is_dir() or build_dir.name.endswith(".app"):
                continue
            for root in app_roots(build_dir):
                api = _first_existing(root, API_RELS, want_dir=True)
                python_bin = _first_existing(root, PYTHON_RELS, want_dir=False)
                if api is None or python_bin is None:
                    continue
                # The packages dir exists in some partial payloads without the
                # `adsk` package itself, which is the part that matters.
                if not (api / "adsk").is_dir():
                    continue
                builds.append(
                    Build(
                        channel=channel,
                        build_hash=build_dir.name,
                        app_root=root,
                        api_packages=api,
                        python_bin=python_bin,
                        mtime=root.stat().st_mtime,
                        version=read_version(root),
                    )
                )
                break
        if builds:
            found[channel] = sorted(builds, key=lambda b: b.mtime, reverse=True)
    return found


def write_env(env_path: Path, api_packages: Path, dry_run: bool) -> str:
    """Set PYTHONPATH in `.env`, preserving any other keys."""
    line = f"PYTHONPATH={api_packages}"
    existing = (
        env_path.read_text(encoding="utf-8").splitlines() if env_path.is_file() else []
    )
    kept = [ln for ln in existing if not ln.startswith("PYTHONPATH=")]
    previous = next((ln for ln in existing if ln.startswith("PYTHONPATH=")), None)
    if previous == line:
        return "unchanged"
    if not dry_run:
        env_path.write_text("\n".join([*kept, line]) + "\n", encoding="utf-8")
    return "created" if previous is None else "updated"


def write_zed_settings(settings_path: Path, python_bin: Path, dry_run: bool) -> str:
    """Point pyright's `pythonPath` at the build's interpreter.

    Only that one key is touched; `extraPaths`, the Debugpy adapter path and any
    unrelated settings are left exactly as they are. Skipped (not created) when
    the file is absent, because the rest of the Zed config is not this script's
    to invent.
    """
    if not settings_path.is_file():
        return "skipped (no file)"
    raw = settings_path.read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return f"skipped (invalid JSON: {exc})"

    node = data
    for key in ("lsp", "pyright", "settings", "python"):
        nxt = node.get(key)
        if not isinstance(nxt, dict):
            return f"skipped (no lsp.pyright.settings.python in {settings_path.name})"
        node = nxt
    if node.get("pythonPath") == str(python_bin):
        return "unchanged"
    node["pythonPath"] = str(python_bin)
    if not dry_run:
        settings_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return "updated"


def print_listing(found: dict[str, list[Build]]) -> None:
    for channel, builds in found.items():
        print(f"\n{channel}")
        for i, build in enumerate(builds):
            marker = "->" if i == 0 else "  "
            stamp = _stamp(build.mtime)
            print(
                f"  {marker} {build.build_hash[:12]}  "
                f"Fusion {build.version:<12} deployed {stamp}"
            )


def _stamp(mtime: float) -> str:
    import datetime

    return datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Point .env and .zed/settings.json at the latest fully-deployed "
            "Fusion build for a channel."
        )
    )
    parser.add_argument(
        "channel",
        nargs="?",
        help="production, pre-production, develop, ... (prompts if omitted)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="show the populated builds per channel and exit",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report what would change without writing",
    )
    args = parser.parse_args(argv)

    webdeploy = find_webdeploy_root()
    print(f"webdeploy: {webdeploy}")
    found = discover(webdeploy)
    if not found:
        sys.exit(
            "No fully-populated Fusion build found under that root.\n"
            "Every hash directory lacked either Api/Python/packages/adsk or the "
            "bundled interpreter. If this is Windows, the layout differs from "
            "the macOS one this was written against - print the real tree and "
            "add its relative paths to API_RELS / PYTHON_RELS."
        )

    if args.list:
        print_listing(found)
        return 0

    channel = args.channel
    if channel is None:
        names = list(found)
        print("\nChannels with a complete build:")
        for i, name in enumerate(names, 1):
            newest = found[name][0]
            print(
                f"  {i}. {name}  (Fusion {newest.version}, "
                f"deployed {_stamp(newest.mtime)})"
            )
        try:
            answer = input("\nSelect a channel [1]: ").strip() or "1"
        except EOFError:
            sys.exit("\nNo channel given and stdin is not a terminal.")
        if answer.isdigit() and 1 <= int(answer) <= len(names):
            channel = names[int(answer) - 1]
        elif answer in found:
            channel = answer
        else:
            sys.exit(f"Not a channel: {answer}")

    if channel not in found:
        sys.exit(
            f"No complete build for channel {channel!r}. Available: {', '.join(found)}"
        )

    build = found[channel][0]
    print(
        f"\nselected {build.label}  Fusion {build.version}  "
        f"deployed {_stamp(build.mtime)}"
    )
    print(f"  packages:   {build.api_packages}")
    print(f"  interpreter: {build.python_bin}")

    env_status = write_env(REPO_ROOT / ".env", build.api_packages, args.dry_run)
    zed_status = write_zed_settings(
        REPO_ROOT / ".zed" / "settings.json", build.python_bin, args.dry_run
    )
    prefix = "would write" if args.dry_run else "wrote"
    print(f"\n{prefix}:")
    print(f"  .env                 PYTHONPATH   {env_status}")
    print(f"  .zed/settings.json   pythonPath   {zed_status}")

    if not args.dry_run:
        print(
            "\nRestart the add-in (Scripts and Add-Ins -> Stop, Run) and "
            "re-attach the debugger for this to take effect."
        )
    return 0


if __name__ == "__main__":
    if os.environ.get("PT_SELFTEST"):  # tiny smoke check, no pytest dependency
        root = find_webdeploy_root()
        assert discover(root), "expected at least one populated build"
        print("selftest ok")
        raise SystemExit(0)
    raise SystemExit(main())
