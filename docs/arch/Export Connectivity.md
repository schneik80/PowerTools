# Export Connectivity — Architecture
[← Export Connectivity guide](../Export%20Connectivity.md)

## Purpose

Write the assembly's connectivity as the industry-practice tabular wire
list (From, From Pin, To, To Pin, Color, Gauge — the CSV convention on
harness drawings, in the IPC/WHMA-A-620 world) so connectivity can be
documented, hand-edited, and round-tripped back through Import
Connectivity.

## The CSV format (v1) — `commands/cable_shared/connectivity.py`

That module is the format's single source of truth (pure, unit-tested in
`tests/test_cable_connectivity.py`); both Export and Import go through it.

```text
# PowerTools connectivity wire list (v1).
# ... editing instructions ...
# Connectors:
#   J1 = Ring Terminal: pins 1 (16-24 AWG); cable point: no
Cable,Wire,From,From Pin,To,To Pin,Color,Gauge (AWG),Wire OD (mm),Cable OD (mm),Length (mm)
,PWR1,J1,1,J2,4,red,22,1.54,,120.5
HARN1,1,J1,1,J3,1,red,24,1.41,6.2,340.2
HARN1,2,J1,2,J3,2,black,24,,,338.9
```

- `#` lines are comments; the export leads with the connector/pin
  reference block so hand-authoring needs no other document.
- Empty `Cable` = single wire (`Wire` = route name). Rows sharing a
  `Cable` value are one cable: one row per wire, **pins paired row by
  row**, one gauge per cable; wire OD / cable OD are carried on the first
  row (parse takes the group's first non-empty cell).
- **A cable's rows may span more than two connectors** (e.g. J1 pigtailing
  out to J3 and J4). Each row names its own From/To; the parser splits the
  refs into the cable's two ends by a **seeded 2-coloring in file order**:
  row 1's From/To seed end A/end B, a row with a known ref orients (or
  flips) to match, a row with neither known reads its columns as A -> B. A
  row whose two refs land on the SAME end is unbuildable and rejects the
  group. Pin uniqueness is scoped to **(connector, pin)** — J3 pin 1 and
  J4 pin 1 can both carry a wire of one cable. The `Wire` label must be
  unique within the cable; when blank it defaults to the From pin,
  qualified as `J1.1` only when end A spans several connectors. The
  export writes each row's OWN refs (all rows oriented A -> B), so a
  re-import partitions without flips and matches as existing.
- The build anchors a multi-connector end on an **implied cable point**
  (averaged and pulled toward the cable run — see
  [Route Wire](./Route%20Wire.md)); every connector of such an end still
  needs its own published cable point.
- `Length (mm)` is export-only documentation (single = conductor stubs +
  sheathed run; cable wire = its out-of-jacket ends + the jacket run).
- Cells that a spreadsheet would evaluate (`=`, `+`, `-`, `@` leads) are
  written with a `'` guard (the `exportbomcsv` hardening) and stripped on
  parse. Unknown trailing columns are ignored by the parser — room for a
  future Signal column.

## Gathering

- Connectors: `builder.connector_occurrences`; the export REFUSES while
  any lacks a designator (`builder.occurrence_designator`) — designators
  are the file's connector identity.
- Routes: `builder.collect_routes`; each end's connector list
  (`routing.end_connectors` — one entry for legacy ends) resolves via
  `builder.resolve_end_occurrence` — the Update Wire ladder
  (`findEntityByToken`, never token-string comparison; unique
  connector-id fallback). Routes with any unresolvable connector are
  skipped and noted. Cable rows carry per-wire refs
  (`routing.end_wire_connectors`) and the stored `wire_labels` in the
  `Wire` column.
- Lengths: the Wire Report measurement helpers, shared via
  `cable_shared.builder` (`member_child_length_cm`, `own_curve_length_cm`,
  `measure_cable_wires` — member-attribute matching with name fallbacks).
- Save dialog: `FileDialog.showSave` (CSV filter, doc-name-derived
  `initialFilename` sanitized per `exportbomcsv`); UTF-8.

---

[← Export Connectivity guide](../Export%20Connectivity.md)
