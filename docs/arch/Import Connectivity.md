# Import Connectivity — Architecture
[← Import Connectivity guide](../Import%20Connectivity.md)

## Purpose

Batch-drive `cable_shared.builder` from an edited wire list: every valid
row/cable group becomes a `build_wire` / `build_cable` call — the same
associative construction, colors, member stamps, and route attributes as
Route Wire, without its two-connector dialog. Cable rows carry explicit
row-by-row pin pairing, which is *richer* than Route Wire's sorted
pairing.

## Pipeline

1. **Open** — `FileDialog.showOpen` (CSV filter); read `utf-8-sig`
   (eats Excel's BOM), `errors="replace"`.
2. **Parse** — `connectivity.parse_wire_list`: tolerant (comments,
   short/extra columns), per-row coercion (gauge bounds, ODs, color
   normalization), grouping into single-wire and cable groups with
   per-group structural validation. Everything invalid becomes a problem
   string; nothing blocks the rest of the file.
3. **Resolve** — designator → occurrence map from
   `builder.connector_occurrences` + `builder.occurrence_designator`
   (duplicate designators are reported and excluded); per-connector data
   via `builder.read_connector`, cached per run.
4. **Match existing** — every routed connection's direction-insensitive
   `connectivity.route_key` (ends resolved with
   `builder.resolve_end_occurrence`, the Update Wire ladder). A single
   whose key exists is skipped as "already routed"; a cable is skipped
   only when ALL its keys exist — partial overlap is refused with a
   problem (nothing half-built).
5. **Preflight per group** — pins exist on the resolved connectors, the
   gauge is inside every wire's min/max range, cables have cable points on
   both ends.
6. **Build** — `builder.build_wire` / `build_cable` with the parsed
   name/gauge/ODs/colors; freshly built keys are added to the existing
   set so a duplicated row later in the same file skips instead of
   double-building. Progress uses the NON-modal `ui.progressBar` (the
   externalize lesson: the modal ProgressDialog intercepts events during
   API churn), hidden in a `finally`.
7. **Summary** — built / already-routed / problems (first 12 + count),
   plus the aggregated builder notes (`routing.result_notes` over the
   summed spline_fallback / baked_points / dropped_tangents flags).

## Deliberate semantics

- **Additive only.** The file never deletes or rebuilds anything —
  Update Wire owns rebuilds; absence from the file means nothing.
- **Group-tolerant.** The repo's established style: report and continue.

---

[← Import Connectivity guide](../Import%20Connectivity.md)
