# Power Tools — Developer Guide

This folder holds developer-oriented documentation for working *on* the
consolidated **Power Tools** add-in for Autodesk Fusion — setting up a local
development environment, the repository layout, the tooling, and how to debug the
add-in from VS Code or Zed.

- New to the codebase's internals? Read the [Architecture](../arch/architecture.md)
  first — it covers the C4 diagrams, the add-in lifecycle, the shared UI
  access-point model, and the command-module pattern.
- Looking for **end-user command guides**? See the [`docs/`](..) folder.
- Installing the add-in as a user? See the project [README](../../README.md).

---

## Contents

- [Prerequisites](#prerequisites)
- [Getting the source into Fusion](#getting-the-source-into-fusion)
- [Repository layout](#repository-layout)
- [The command-module pattern](#the-command-module-pattern)
- [Developer tooling](#developer-tooling)
- [The `.debug` marker](#the-debug-marker)
- [Debugging](#debugging)
- [Documentation map](#documentation-map)

---

## Prerequisites

- **Autodesk Fusion** with Python add-in support, on **macOS** or **Windows 10/11**.
  Fusion ships its own bundled Python (currently **3.14**); the add-in runs inside
  that interpreter, not a system Python.
- A local **Python 3.10+** for the developer tooling (lint / type-check / tests).
  The repo's `.venv` is created with Python 3.14 via [`uv`](https://docs.astral.sh/uv/),
  but any 3.10+ works.
- **Git**, and (optionally) [`uv`](https://docs.astral.sh/uv/) for fast virtualenv
  and dependency management.

The add-in itself has **no runtime dependencies** beyond Fusion's API. `pyproject.toml`
configures developer tools *only* — Fusion loads `PowerTools.py` and the
`commands/` tree directly and ignores that file entirely.

## Getting the source into Fusion

Fusion can load an add-in from **any path on disk** — you do not need to place or
symlink it under `~/Library/.../API/AddIns/`. To develop against your working copy:

1. Clone the repository (e.g. to `~/Source/PowerTools`).
2. In Fusion, open **Utilities › Add-Ins** (or press **Shift+S**).
3. On the **Add-Ins** tab, click the green **+** next to *My Add-Ins* and select
   the repository folder.
4. Select **PowerTools** in the list and click **Run** (enable **Run on Startup**
   to load it automatically each session).

Fusion remembers the absolute path and reloads from it every session. See the
[README Installation section](../../README.md#installation) for the user-facing
version of these steps.

## Repository layout

| Path | Purpose |
|---|---|
| `PowerTools.py` | Add-in entry point. Fusion calls `run()` on start and `stop()` on stop. |
| `PowerTools.manifest` | Fusion add-in manifest (id, author, `runOnStartup`, supported OS). |
| `config.py` | Merged configuration: global flags, shared panel/flyout IDs, settings cache, hub config, palette IDs, and the debugger gate. |
| `commands/` | One package per command (~48 of them). |
| `commands/__init__.py` | Command registry — imports every command, bootstraps the shared UI, then starts each command. |
| `commands/_ui_bootstrap.py` | Creates the two shared UI access points once (the **Power Tools** panel and the **PowerTools Settings** QAT flyout). |
| `lib/ptAddInUtils/` | Shared utility library (logging, event-handler registration, attributes, caches, dates, JSON, uploads, UI placement). |
| `cache/` | Runtime caches (git-ignored). |
| `settings/` | Per-user preferences store, auto-created on first run (git-ignored). |
| `docs/` | End-user command guides. |
| `docs/arch/` | Architecture documentation (C4 diagrams, lifecycle). |
| `docs/dev/` | Developer documentation (this folder). |
| `tests/` | Pytest suite (runs outside Fusion; see [Developer tooling](#developer-tooling)). |
| `pyproject.toml` | Ruff / mypy / pytest configuration (developer tooling only). |

For the full narrative — system context, component diagram, the add-in lifecycle,
command registration and execution, and the merged `config.py` — see
[**docs/arch/architecture.md**](../arch/architecture.md).

## The command-module pattern

Every command lives in its own package under `commands/<name>/` and exposes a
consistent surface the registry drives:

- `__init__.py` — a `start()` / `stop()` pair the registry calls in order.
- `entry.py` — the command's UI wiring and Fusion event handlers
  (`command_created`, `command_execute`, input-changed, etc.).
- `resources/` — icons and any palette HTML.
- optional pure-logic helper modules (e.g. `rounding.py`, `sketch_hash.py`) kept
  free of Fusion dependencies so they can be unit-tested.

`commands/__init__.py` imports every command module, calls
`commands/_ui_bootstrap.py` to create the shared access points once, then calls
each command's `start()`. On shutdown the order is reversed. See
[Command registration](../arch/architecture.md#command-registration) and the
[Command execution model](../arch/architecture.md#command-execution-model) in the
architecture doc.

If your command draws in the viewport — a highlight, a marker, a manipulator —
read [**Custom graphics that stay painted**](Custom%20graphics%20that%20stay%20painted.md)
*before* you write the draw code. Graphics created outside `executePreview` are
undone by Fusion's next preview cycle, which looks like flaky rendering and is
not.

If your command needs real geometry processing, [**the Flatten Surface
solver**](Flatten%20Surface%20solver.md) is the worked example of the pattern this
repo uses for it: all the mathematics in a module that imports no `adsk`, taking
and returning plain tuples, so it can be developed and tested without launching
Fusion at all.

## Developer tooling

The tooling is configured in `pyproject.toml` and installed as the `dev` extra.

```bash
# From the repository root:
uv venv                       # or: python3 -m venv .venv
uv pip install -e ".[dev]"    # or: pip install ruff mypy pytest

ruff check .                  # lint (pyflakes, pycodestyle, isort, bugbear)
ruff format .                 # format in place (double quotes, line length 88)
ruff format --check .         # verify formatting without writing (used in CI)
mypy .                        # type-check (advisory; not a gate)
python -m pytest -q           # run the test suite
```

**Formatting is standardized on `ruff format`** (double-quote style, ruff's
default). Run `ruff format .` before committing. The repo carries a
`.git-blame-ignore-revs` file so the one-time bulk-reformat commit is skipped by
`git blame`; enable it locally once with:

```bash
git config blame.ignoreRevsFile .git-blame-ignore-revs
```

**`adsk` only resolves inside Fusion.** The `adsk.*` API packages do not exist on
a developer machine, so:

- The test suite stubs `adsk` via a meta-path finder in `tests/conftest.py` and
  imports the add-in under the `PowerTools` package name (the same name Fusion
  uses). Tests therefore target **pure logic** only.
- `mypy` and the Zed/VS Code language servers are configured to ignore the missing
  `adsk` imports and to resolve them against Fusion's API stubs
  (`.../API/Python/defs`) for autocomplete.

`ruff`, `mypy`, and `pytest` exclude `cache/`, `settings/`, `**/resources/`, and
`docs/`.

**Continuous integration.** `.github/workflows/ci.yml` runs on every push and
pull request and enforces three hard gates: `ruff check .`, `ruff format --check .`,
and `pytest`. Keep them green locally before pushing.

## The `.debug` marker

Create an empty file named **`.debug`** in the repository root to enable
developer **debug mode**. The marker is git-ignored, so it never ships in a
distribution. Its presence is read once when the add-in loads (`config.py`), and
it turns on two things at the same time:

1. **Verbose logging** (`config.DEBUG`) — `ptutil.log(...)` writes to stdout, the
   Fusion log file, and the Fusion **Text Commands** window. When the marker is
   absent, `ptutil.log()` is a no-op.
2. **The attach-debug server** (`config.WAIT_FOR_DEBUGGER`) — the add-in starts an
   in-process `debugpy` server on startup so an editor can attach. See
   [Debugging](#debugging).

Toggle debug mode by creating or deleting the file — no code change is required.
The [release build](release.md) works from the git-tracked file list, so the
marker can never ship, but delete it before testing a build you intend to hand
to anyone directly.

On macOS you can follow the live log in Console.app; `lib/ptAddInUtils/log_utils.py`
provides `open_live_log_viewer()` for a platform-native tail.

## Debugging

Power Tools supports two debuggers:

- **VS Code** — via Fusion's built-in **Debug** button (Fusion injects `debugpy`
  and VS Code attaches).
- **Zed** — via the in-process `debugpy` server this add-in starts when the
  `.debug` marker is present; Zed *attaches* to it.

Full step-by-step instructions, the port map, the non-obvious setup traps, a
verification checklist, and how to disable debugging for a shipping build are in
**[debugging.md](debugging.md)**.

## Documentation map

| Folder | Audience | Contents |
|---|---|---|
| [`docs/`](..) | End users | Per-command usage guides. |
| [`docs/arch/`](../arch) | Developers | Architecture — C4 diagrams, lifecycle, shared library, `config.py`. |
| [`docs/dev/`](.) | Developers | This guide, the [debugging guide](debugging.md), the [release process](release.md), the [insert-and-position recipe](Insert%20and%20position%20a%20component%20from%20a%20palette.md), [custom graphics that stay painted](Custom%20graphics%20that%20stay%20painted.md), and the [Flatten Surface solver](Flatten%20Surface%20solver.md) with its [method background](Flatten%20Surface%20research.md). |

---

*Copyright © 2026 IMA LLC. All rights reserved.*
