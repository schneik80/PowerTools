# Environment — what actually works, and where

This project is developed on **three devices**, so a note that says "on this
machine" is worthless. **Every device-specific fact below names the device it
was observed on.** Facts with no device tag are properties of the repo or of
Fusion and hold everywhere.

If you observe something new, tag it the same way — hostname and OS at
minimum. Run `hostname && uname -sm` (or `hostname` + `systeminfo | findstr /B "OS Name"`
on Windows) to find out where you are before writing anything down here.

## Device roster

Tags below are the devices' hostnames, so the tag is itself the identifying
detail. Use them verbatim in notes and commit messages.

| Tag | Device | Runs Fusion? | Notes |
|---|---|---|---|
| **`mac-air-m4`** | `ADSKMVG91G2F5W` — MacBook Air, Apple M4, 32 GB, macOS 26.5.1 (build 25F80), Darwin 25.5.0, arm64 | Yes — **production and pre-production** | The macOS dev box, and the device every fact in this file was verified on (2026-09-03). `debugpy` already installed |
| **`g16win`** | `g16win.local` — **Windows 11**, x86_64 | Yes — **production and pre-production** | Where the Windows-only bugs surface (`25d5f48`, `93c6b36` — Change Cycle Color path + theme resolution). The `README.pdf` toolchain was written against **MiKTeX** here |
| **`ryzen-nobara`** | `ryzen-nobara.local` — **Nobara 44** (Fedora 44 base), AMD Ryzen, x86_64 | **No** — there is no native Fusion client for Linux, so `import adsk` can never resolve | Lint / test / release zip / PDF only (Homebrew pandoc + TeX Live xelatex). Anything verified only here is "not yet exercised in Fusion" |

Three consequences worth holding onto:

- **Both Fusion devices carry both release channels**, so "which device" does
  not imply "which build". A device tag alone is not enough for anything
  build-sensitive — **name the channel too** (see below).
- **Nobara is Fedora-based**, so package installs on `ryzen-nobara` are `dnf`,
  not `apt`. CI runs on `ubuntu-latest`, so the CI runner is *not* a stand-in
  for that device.
- **Both Fusion devices are x86_64; `mac-air-m4` is arm64.** If something ever
  looks architecture-sensitive, that is the split — and note it is the *same*
  split as macOS-vs-Windows, so an arm64 bug and a macOS bug look identical
  from the outside. Distinguishing them needs `g16win` on ARM, which does not
  exist here.

### Channel matters as much as device

`mac-air-m4` has **five** webdeploy trees side by side —
`production`, `pre-production`, `develop`, `feature--1fx-globalnav`, `meta` —
under `~/Library/Application Support/Autodesk/webdeploy/`. Launching "Fusion"
says nothing about which one ran.

So when reporting a repro or a fix, state **device + channel**. A bug that
appears on one and not the other is as likely to be a channel difference as a
platform difference, and the two are easy to confuse when each platform can
present either build.

A hash is **not** channel-unique either — `8d5cf31c…` currently sits under both
`production/` and `pre-production/` — so a webdeploy hash does not identify the
channel on its own.

This repo's **debug** configuration pins one build: `.env` sets `PYTHONPATH`
and `.zed/settings.json` sets pyright's `pythonPath`, both into one channel's
tree. That is a property of the *checkout*, **not** of the device (the same
choice exists on `g16win`), and both go stale on every Fusion update because
the hash rotates.

**Repoint them with the script** rather than by hand — most hash directories
are partial delta payloads, so "newest folder" is the wrong answer:

```bash
python3 tools/debug/update_debug_path.py --list           # what is complete
python3 tools/debug/update_debug_path.py pre-production   # repoint both configs
```

A dead `PYTHONPATH` fails silently — no import error, just unresolved `adsk.*`
and breakpoints that never trip — so check it when a debug session looks wrong:

```bash
ls -d "$(grep -o '/Users/.*packages' .env)" || echo "STALE — re-run the script"
```

Full detail: [`docs/dev/debugging.md`](../docs/dev/debugging.md#pointing-the-config-at-a-build-update_debug_pathpy).

## The four CI gates

`.github/workflows/ci.yml` hard-gates every push on these four. Run all four
before every commit — a file that lints clean can still fail the format gate,
and the PDF stamp has gone stale twice (`48722db`, `28188f7`).

```bash
ruff format --check .                            # CI's exact gate
ruff check .
.venv/bin/python -m pytest -q                    # -> "782 passed, 2 skipped" (count grows)
python3 tools/pandoc/build_readme_pdf.py --check  # -> "README.pdf matches README.md"
```

Use `ruff format .` (no `--check`) to actually fix formatting, then re-run the
check.

### Two invocation traps on `mac-air-m4`

Both are properties of how the toolchain was installed on that device, not of
the repo. On `g16win` and `ryzen-nobara`, check before assuming either way.

1. **`python -m pytest` and `python3 -m pytest` both fail** with
   `No module named pytest`. Neither Homebrew interpreter has it, and `pytest`
   is not on `PATH`. pytest lives **only** in the project venv, so use
   `.venv/bin/python -m pytest -q` (or `.venv/bin/pytest -q`).
2. **`ruff` is not in `.venv`** — `.venv/bin/` has no `ruff` at all. The `ruff`
   on `PATH` (`~/.local/bin/ruff`) is **0.15.20**, which matches the
   `ci.yml` pin, so the bare command is correct *today*. Because
   `ruff format --check` drifts between releases, confirm before trusting it:

   ```bash
   ruff --version                                  # must equal the ci.yml pin
   grep 'ruff==' .github/workflows/ci.yml
   ```

   If they ever disagree, run the pinned version explicitly —
   `uvx ruff@<pin> format --check .` (`uv` is installed on `mac-air-m4` and
   resolves from cache offline, which matters because PyPI is proxy-blocked on
   the Autodesk corporate network). Bumping the pin means bumping `ci.yml`
   **and** reformatting the tree in one commit (`ef14b11`); a mismatch either
   produces spurious diffs or passes on your device and fails CI (`ef424c6`).

Interpreters present **on `mac-air-m4`**: `python3` → 3.14.7 (Homebrew),
`python` → 3.13 (Homebrew), `.venv/bin/python` → 3.14. The venv is not
committed; bootstrap it with

```bash
python3 -m venv .venv && .venv/bin/pip install "ruff==0.15.20" "pytest>=8.0"
```

## Other repo commands

```bash
python3 tools/pandoc/build_readme_pdf.py               # after ANY README.md edit
python3 tools/release/build_release.py --version v0.0.0-test   # dry run -> dist/
python3 commands/<cmd>/resources/generate_icons.py     # regenerate an icon set
```

`build_release.py` reads `git ls-files`, so **`git add` new files before a dry
run** or they will not appear in the zip listing.

## Fusion paths

The macOS column is verified on `mac-air-m4`. The Windows column comes from
the user and from `commands/openrecent` / `fusion_recents.py`, and is **not**
verified by anyone running this file. Nothing on `ryzen-nobara` has these
paths at all — Fusion does not exist there.

**Never hardcode either column in add-in code** (`af05499`) — probe candidates
and log what resolved. Three devices is exactly why that rule exists.

| What | macOS (`mac-air-m4`) | Windows (`g16win`) |
|---|---|---|
| API stubs (ground truth for the API surface) | `~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/Python/defs/adsk/` | `%APPDATA%\Autodesk\Autodesk Fusion 360\API\Python\defs\adsk\` |
| Installed add-ins | `~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns/` | `%APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns\` |
| Crash dumps (CER) | `~/Library/Application Support/Autodesk/CER/<id>/<timestamp>/` | `%LOCALAPPDATA%\Autodesk\CER\` |
| Fusion user options (recents source) | `~/Library/Application Support/Autodesk/Neutron Platform/Options/<userId>/` | `%APPDATA%\Autodesk\Neutron Platform\Options\<userId>\NGlobalOptions.xml` |

**The stubs are the API's real docstrings.** `defs/adsk/core.py`,
`fusion.py`, `cam.py` etc. are large but greppable, and they settle questions
that comments, memory and the web docs get wrong. Grep them before asserting
what a property does (path is `mac-air-m4`; swap the prefix on `g16win`; they
do not exist on `ryzen-nobara`):

```bash
grep -n 'def doExecute' -A12 "$HOME/Library/Application Support/Autodesk/Autodesk Fusion 360/API/Python/defs/adsk/core.py"
```

Fusion runs **its own bundled Python 3.14**, has **no pip and no Pillow**, and
`import adsk` resolves *only* inside Fusion. The add-in and everything in
`tools/` are therefore stdlib-only.

## Reading a crash

A native fault (`SIGSEGV` on macOS, `0xC0000005` on Windows) produces **no
Python traceback** — absence of one is not evidence a handler ran. Fusion
writes a CER report instead. On `mac-air-m4`:

```bash
ls -t ~/Library/Application\ Support/Autodesk/CER/*/*/ | head
# the newest folder holds crashLog.txt.dmp.zip; unzip -o it, then read the
# stack in crashLog.txt
```

On `g16win` the reports are under `%LOCALAPPDATA%\Autodesk\CER\`. On
`ryzen-nobara` there are none, because Fusion never runs there.

Two frames worth recognising, because they name the culprit directly:

- `Xl::APICommandDefinitionImpl::doOnCreateCommand` beneath `createCommand`
  ← `Nu::CommandMgr::executeCommand` → something re-entered the command manager
  from `command_created`, almost always a `doExecute` call (`14871d7`).
- A fault right after a long save/close run → a document or design handle held
  across a pumped wait went stale (`a1d22e1`).

Read the DEBUG log and the crash stack **before** theorising. Two
identical-looking "Preferences needs a document" bugs had different root causes.

## Debug logging

`ptutil.log()` is a **no-op** unless an empty `.debug` file exists in the repo
root, and `handle_error` logs through it — so an unguarded exception in a
palette's `incomingFromHTML` handler reads to the user as "nothing happens"
(`7535954`). The same marker starts the `debugpy` listener. It is git-ignored
and can never ship, so it is **per device** — a fresh clone on `g16win` or
`ryzen-nobara` has no `.debug` until you create one.

On `mac-air-m4`, `debugpy` is already installed into Fusion's user site
(`~/Library/Python/3.14/lib/python/site-packages/debugpy`) and the editor
config points at the **pre-production** Fusion channel
(`webdeploy/pre-production/8d5cf31…`, per `.env`), which the stock
`setup-fusion-debug.sh` will happily repoint at production. `.zed/` is
git-ignored for exactly this reason: the webdeploy hash is per-device and
rotates on every Fusion update. Full setup and the four traps:
[`docs/dev/debugging.md`](../docs/dev/debugging.md).

## MCP servers

Configured **per device** in `~/.claude.json`, not in the repo (there is no
`.mcp.json`), so a fresh clone on a new device gets none of them. The list
below is what `mac-air-m4` has; do not assume the other two match.

| Server | Transport | Use it for |
|---|---|---|
| `autodesk-product-help` | `mcp-remote` → developer.api.autodesk.com | Searching official Autodesk/Fusion help. The sanctioned way to satisfy "verify API names against the reference, not memory" |
| `fusion` | HTTP `localhost:27182/mcp` | Live introspection of a **running** Fusion |
| `drawio`, `pencil`, `atlassian` | — | Diagrams, design files, Jira/Confluence (needs OAuth) |

**`fusion` returning `ConnectionRefused` means Fusion is not running** (or the
"Fusion MCP Addin" in the AddIns folder above is not loaded). It is not a
missing capability — ask the user to start Fusion, then retry. It is also
permanently unavailable on `ryzen-nobara`, where Fusion cannot run at all.

That server is the only way to verify anything against a real Fusion: the test
suite stubs `adsk` with `MagicMock`, so **it proves pure logic only**. Say
"not yet exercised in Fusion" in the commit when that is true — and it is
always true of work done on `ryzen-nobara`.

---
*Copyright © 2026 IMA LLC. All rights reserved.*
