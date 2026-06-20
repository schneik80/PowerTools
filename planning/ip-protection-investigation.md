# Investigation Plan — Source/IP Protection via Compilation

**Status:** Investigation only — no implementation.
**Scope:** Evaluate whether and how the PowerTools add-in's Python source can be
protected (compiled/obfuscated) for release **without** disrupting pure-Python
development. This plan's deliverable is a **go/no-go decision plus findings**, not
a shipped compiled build. Building the release pipeline, CI, signing, and any
licensing/entitlement system are explicitly **out of scope** here and would be
separate plans gated on the outcome of this one.

---

## Objective

Answer one question with evidence:

> Can we ship a compiled/obfuscated PowerTools add-in that (a) meaningfully
> protects the Python source, (b) loads correctly inside Fusion on all target
> platforms, and (c) does **not** force a rebuild every time Autodesk bumps the
> embedded Python — and if churn is unavoidable, what is the cheapest way to
> absorb it?

---

## Background — constraints that shape every option

Fusion add-ins are unusual to compile:

1. **Fusion runs add-ins in its own embedded CPython.** A compiled C-extension
   (`.pyd`/`.so`) is locked to a CPython **ABI**:
   - *Full ABI* (default Cython/Nuitka): tied to one **minor** version
     (`cp311`, `cp312`). Loads on any patch of that minor; **fails to import on a
     different minor**. Failure is at load time — the add-in won't start.
   - *Limited API / stable ABI (abi3)*: one binary loads on **all** Python ≥ a
     chosen floor (3.11, 3.12, 3.13 …).
2. **Three targets every release:** `win-amd64`, `mac-arm64`, `mac-x86_64`
   (manifest is `windows|mac`). Each needs its own build.
3. **`adsk` only exists inside Fusion** — final load/smoke testing must happen
   in Fusion on each OS; it cannot be import-tested off-Fusion.
4. **Compilation protects only Python.** Non-Python assets ship in the clear;
   palette HTML/JS is client-side and fully visible.
5. **`__file__`-relative resource loading** must keep working after compilation
   (a compiled module's `__file__` points at the `.so`/`.pyd`; resources must
   ship alongside their module).
6. **macOS Gatekeeper:** distributed `.so` files should be codesigned + notarized.

### Codebase facts (measured)

| Metric | Value |
|---|---|
| Total `.py` modules | 108 |
| Package `__init__.py` files | 43 |
| Modules importing `adsk` (Fusion-only) | 57 |
| Modules using `__file__`-relative resource paths | 39 |
| Non-Python assets (html/js / json / icons) | 4 / 1 / 440 |
| Already proprietary-licensed | yes (headers + LICENSE) |

---

## The core risk: unknown-interval Python bumps

The breaking event is not "Fusion updated Python" — it is specifically a **minor
version bump** (e.g. 3.11 → 3.12). Patch bumps (3.12.0 → 3.12.7) are free.
Autodesk does minor bumps roughly once a year but at an **unpredictable** time.
With default Cython/Nuitka, each minor bump silently bricks shipped binaries
until we recompile and re-release. This risk is the primary driver of the
recommendation below.

---

## Options to evaluate

| Option | Protection | Effort | Version-bump fragility | Notes |
|---|---|---|---|---|
| Ship `.pyc` bytecode | very weak | trivial | high | Trivially decompiled. Not real protection. Baseline only. |
| **Cython, abi3 (Limited API)** | strong | medium | **low** | One binary per platform survives minor bumps. Cython limited-API support is *partial* — must be validated. **Primary hypothesis.** |
| Cython, full ABI (per-module) | strong | medium | high | Maps cleanly to package layout; recompile every minor bump. |
| Nuitka `--module` | strongest | med–high | high | Hardest to reverse; packaging a 43-package tree + data needs care; weak Limited-API story. |
| PyArmor (obfuscate + bind) | medium | low–med | medium | No C toolchain; supports machine-binding/expiry (also addresses *use*, not just *reading*). Runtime is per-Python-version; adds a third-party dependency to release timing. |
| Server-side for "crown jewels" | highest | varies | none | Immune to version churn — no client binary to break. For a small sensitive subset only. |
| Nuitka standalone/onefile | n/a | n/a | n/a | **Not applicable** — Fusion must load into its own interpreter. |

---

## Primary hypothesis to test

> **Cython built against the Limited API (abi3) can compile this codebase and
> load inside Fusion across two different Python minor versions.**

If true, the unknown-interval bump problem is largely neutralized (build once per
platform; minor bumps stop mattering). If false, we fall back to version-tagged
multi-builds + a pure-Python entry shim that selects the right binary and shows a
graceful "please update" message when none matches — backed by standing CI and
Autodesk preview-build monitoring.

---

## Investigation tasks (spikes)

1. **Confirm targets.** Read Fusion's `sys.version` on Windows and macOS (both
   arches). Record the exact embedded CPython minor version(s) in use today.
2. **abi3 feasibility spike.** Cython-compile a 2-module slice —
   `lib/ptAddInUtils` + one simple command (e.g. `exportbomcsv`) — in **two
   variants**: default full-ABI and Limited-API (abi3). Success criteria:
   - both variants build for each platform;
   - inside Fusion, the add-in loads and the command runs;
   - `__file__`-relative icon/resource paths resolve from the compiled module;
   - **the abi3 variant loads unchanged on a second Fusion release whose embedded
     Python is a different minor version.**
3. **macOS distribution spike.** Codesign + notarize the compiled `.so`; confirm
   it passes Gatekeeper on a clean machine.
4. **Reverse-engineering sanity check.** Spot-check the compiled output to
   confirm source/docstrings are not trivially recoverable (and document what
   *does* remain visible — strings, asset files, palette JS).
5. **Fallback design (only if abi3 fails).** Prototype the pure-`.py` entry
   shim doing `sys.version_info`/platform selection + "incompatible, please
   update" messaging.

---

## Decision gates

- **Gate A (abi3 viable?)** → if yes, recommend Cython-abi3 and open an
  implementation plan. If no, proceed to Gate B.
- **Gate B (full-ABI churn acceptable?)** → weigh per-bump rebuild cost vs.
  multi-build complexity vs. PyArmor vs. server-side for the sensitive subset.
- **Gate C (threat model match?)** → confirm the chosen option matches the
  required protection level (casual viewing vs. determined RE) and whether
  *use/redistribution* control is also required (→ licensing layer, separate).

---

## Out of scope for this plan

- Building the production release pipeline / `build.py` transform.
- CI matrix (win-amd64, mac-arm64, mac-x86_64 / universal2) and release signing.
- Any licensing/entitlement/activation system.
- Migrating sensitive logic server-side (its own design effort).

These become follow-on plans only if this investigation returns "go."

---

## Open questions for stakeholders

1. **Threat model:** protect against *casual* source viewing (Cython is ample) or
   *determined* reverse-engineering (add server-side for crown jewels)?
2. **Use control:** do we also need to stop unauthorized *use/redistribution*
   (→ licensing/binding), or only hide source?
3. **Platform coverage:** Windows + both Mac arches, or can Intel Macs be dropped?
4. **Tooling preference for the spike:** proceed with Cython (recommended) for
   the abi3 test, or also trial Nuitka full-ABI in parallel?

---

## References

- Source consolidation & structure: [`docs/arch/architecture.md`](../docs/arch/architecture.md)
- DEBUG toggle (dev/release separation already in place): `config.py`, `.debug` marker

---

## Appendix: Additional options considered

Added to round out the option space. None of these displace the primary
hypothesis (Cython-abi3); documented so the spike doesn't have to revisit them
and so Gate C has the full menu.

### Extended options matrix

| Option | Protection | Effort | Version-bump fragility | Notes |
|---|---|---|---|---|
| Source minification only (python-minifier, pyminifier, Oxyry) | very weak | trivial | none | Renames locals, strips comments/docstrings. Defeats casual viewing only; AST tools recover structure. Useful as a free additive layer on top of any other option, not a standalone answer. |
| Hybrid: pure-Python shell + compiled sensitive modules | matches inner option | medium | matches inner option | Strategy rather than a separate tool. Keep UI/glue/`adsk` event handlers as `.py` (fast iteration, trivially survives version bumps); compile only modules that are actually sensitive (algorithms, license/auth logic, network calls). Shrinks the blast radius of every concern above — fewer compiled modules to rebuild on a Python bump, fewer `__file__`-relative resource paths to verify, less to codesign/notarize. Recommend defining the "sensitive set" *before* the abi3 spike so the spike compiles a representative slice rather than an arbitrary one. |
| pybind11 / native C++ extension for surgical hotspots | strongest | high (per module) | high (unless Limited API) | Drop a real `.so`/`.pyd` written in C++ for one or two modules where Cython-level protection isn't enough. Same ABI fragility as full-ABI Cython unless built against the Limited API. Only justified if a specific module is both highly sensitive *and* small/stable enough to port. |
| Full port of the add-in to C++ | strongest | **5–8× original dev cost** | n/a (different SDK) | Fusion's C++ API is a 1:1 superset of the Python API, so the *Fusion* surface ports mechanically. The cost lives in: (a) replacing every non-stdlib Python dependency (HTTP, JSON, any pandas/numpy/etc.), (b) standing up Win/Mac toolchains + signing/notarization, (c) permanent ~3–5× slowdown of the inner dev loop (compile + restart Fusion + reattach debugger every change), (d) verbose `Ptr<>`/event boilerplate, (e) manual lifetime/threading rules Python hid. Not recommended for a 108-module add-in; listed so it's explicitly off the table. |

### What compilation does *not* hide

Stated explicitly so the Gate C threat-model conversation is grounded:

- **String literals** — user-facing text, URLs, format strings, dict keys
  survive in the binary. Often what an attacker actually wants (license
  server URL, API endpoints, secret prompts).
- **Public API surface** — module/class/method names must remain visible
  for Fusion and sibling modules to import them.
- **Inter-module call graph** — Cython compiles per module, so which
  command calls which helper is observable from import structure alone.
- **Palette HTML/JS** — client-side, fully readable. Any logic living in
  a palette is unprotected regardless of what we do to the Python.
- **Asset files** — icons, JSON, manifest, docs ship as-is.
- **Anything `__file__`-relative loads** — both the path and the file it
  points at are visible.

Implication for task #4: when sampling compiled output, also enumerate
which *strings* survive, not just whether bytecode is recoverable.

### Dev-loop cost (separate from release-time fragility)

The plan covers version-bump fragility at release time but not the
day-to-day cost of compiled modules in the tree:

- Pure Python today: edit `.py` → "Stop add-in / Run add-in" in Fusion →
  test. Seconds.
- With compiled modules in-tree: edit `.pyx`/`.py` → rebuild that module
  → restart Fusion (it caches loaded extensions and will not pick up a
  rebuilt `.so` mid-session) → test. Tens of seconds to minutes.

Mitigation that preserves the Objective's "does not disrupt pure-Python
development" requirement: keep DEBUG/dev mode entirely source — no
compilation in dev — and compile only for release builds. The existing
`.debug` marker in `config.py` already provides the switch point.
Honoring this is a constraint on the (out-of-scope) build pipeline, not
the spike, but worth noting now so the pipeline isn't designed in a way
that forces developers through a compile step.

### Layering

The options in both matrices are not mutually exclusive. A plausible
production stack is:

- **Source minification** (free, additive) +
- **Cython-abi3 on the sensitive subset** (primary protection, per the
  hybrid strategy above) +
- **Server-side for any true crown jewels** (immune to client-side RE) +
- **PyArmor-style or custom license binding** *separately* if
  use/redistribution control is required (Gate C, open question #2 —
  this is a different problem from hiding source).

The spike should still validate one primary mechanism end-to-end
(Cython-abi3); this note exists so the eventual recommendation isn't
framed as an exclusive choice when it doesn't have to be.
