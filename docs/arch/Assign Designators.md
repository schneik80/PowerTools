# Assign Designators — Architecture
[← Assign Designators guide](../Assign%20Designators.md)

## Purpose

Fifth piece of the cable prove-out: reference designators (J1, J2, …) are
the connector IDs that harness wire lists and reports use. This command
owns them; Export/Import Connectivity and the Wire Report only consume.

## Storage — occurrence attributes (a repo first)

Designators are stored on the **Occurrence** (`occ.attributes`, group
`PowerTools.Cable`, name `designator`, JSON
`{"schema": 1, "designator": "J1"}` — `schema.build_designator_payload`,
read back via `builder.occurrence_designator`). The alternatives are
wrong, not just worse:

- A **component** attribute is shared by every instance (two instances of
  one connector part must be J1 *and* J2), and for XRef parts it would
  live in the part document instead of this assembly.
- A root-component **map keyed by occurrence token** would re-import the
  token-string-comparison mistake the Update Wire work disproved (the API
  documents token strings as unstable).

This is the repo's first use of occurrence attributes — every other
attribute in the tree sits on components, points, or documents — so the
save/reopen persistence is explicitly part of the smoke test.

## Dialog

The `globalParameters` editable-table pattern: a read-only header row plus
one `StringValueInput` per connector row, values collected positionally
with `table.getInputAtPosition(row, col)` (no id reconstruction; rows are
never deleted so plain index ids suffice). Connector rows come from
`builder.connector_occurrences` (components with a Define Wires manifest).
Unassigned rows are seeded from `connectivity.suggest_designators` (J`n`
skipping taken, case-insensitive); `connectivity.validate_designators`
gates OK (uniqueness, case-insensitive; blanks allowed) and fails closed.

On execute, changed values are written (`attributes.add` overwrites
in place), blanked values delete the stored attribute.

---

[← Assign Designators guide](../Assign%20Designators.md)
