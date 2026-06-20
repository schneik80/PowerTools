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
