---
name: build-readme-pdf
description: Rebuild and audit README.pdf after any README.md change. Repo rule - the PDF is regenerated in the same commit as its source (48722db).
---

# Build README.pdf

`README.pdf` is a committed, derived artifact. A PDF built from a different
revision than `README.md` is worse than no PDF, so any README edit ends with this
skill and both files are staged together.

## Prerequisites

- `pandoc` and `xelatex` on PATH (`pandoc --version`, `xelatex --version`).
  The Linux dev box has both (Homebrew pandoc, TeX Live xelatex); the script
  was written against MiKTeX on Windows and works with either.
- No Python packages: `tools/pandoc/build_readme_pdf.py` is stdlib-only and
  shells out.

## Steps

1. Finish the `README.md` edit first. Remember two Markdown conventions the
   build gives meaning to:
   - A horizontal rule (`---`) is a **page break** in print
     (`tools/pandoc/hr-to-pagebreak.lua`), not a decorative line. Do not
     sprinkle them.
   - Pipe-table column widths are computed by `tools/pandoc/table-widths.lua`
     (sqrt-weighted by widest cell, pooled across tables that share a header),
     so keep the Command / Location / Description headers identical across the
     command tables or they stop lining up.
2. Run the build from the repo root:

   ```bash
   python tools/pandoc/build_readme_pdf.py
   ```

   It runs xelatex twice (cross-references resolve on the second pass) and then
   **audits** the log: any overfull box (content past the margin) or undefined
   reference (broken internal link) makes it exit non-zero.
3. If the audit fails, fix the cause in `README.md` (shorten a cell, split a
   table, correct the anchor). Do **not** pass `--skip-audit` to get a green
   run; that flag exists for diagnosing the toolchain, not for shipping.
4. Verify the stamp: `python tools/pandoc/build_readme_pdf.py --check` must
   print that the PDF is current (it compares the `readme-sha256:` Subject
   stamp with `README.md`; CI and `tests/test_readme_pdf_build.py` run the
   same check, so a stale PDF fails the suite locally). Page count should stay
   in the same ballpark (5 pages as of 2026-09), and `git status` should show
   `README.pdf` modified. `--if-stale` is the variant the release build runs.
5. Stage `README.md` and `README.pdf` together. Mention the regeneration in the
   commit body (see `docs/dev/lessons.md#docs-release`).

## Known environment trap (Linux box, TeX Live 2026)

`build()` treats *any* pandoc stderr as failure on purpose (a99202d). On a
TeX Live install whose `array.sty` is newer than its compiled `xelatex.fmt`,
pandoc emits `LaTeX Warning: You have requested release '2026/06/01' of
LaTeX, but only release '2025-11-01' is available` and the script exits 1
**after** writing a complete PDF and **before** running the audit. Seen
2026-09-03. Do not weaken the check; instead:

1. Confirm the PDF is complete (`pdfinfo README.pdf` shows 5 pages).
2. Run the audit step directly:

   ```bash
   python3 -c "import importlib.util; from pathlib import Path; \
   s=importlib.util.spec_from_file_location('b','tools/pandoc/build_readme_pdf.py'); \
   b=importlib.util.module_from_spec(s); s.loader.exec_module(b); \
   print(b.audit(Path('README.md')))"   # expect (0, 0)
   ```

3. Fix the machine when convenient (`sudo fmtutil-sys --byfmt xelatex`, or a
   TeX Live update) so the wrapper goes green again.

## When to skip

Only when the README did not change. Doc changes under `docs/` do not feed the
PDF.
