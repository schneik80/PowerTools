# Round Sketch Dimensions — Architecture

[← Round Sketch Dimensions guide](../Round%20Sketch%20Dimensions.md)

## Command identity

- **CMD_ID:** `PTPM-roundsketchdimensions`
- **Location:** Design workspace → **Sketch** tab → **Modify** panel (`SketchTab` / `SketchModifyPanel`).
- **Module:** `commands/roundsketchdimensions/` — `entry.py` (Fusion wiring + apply) and `rounding.py` (pure math).

## Design decisions

- **Pure/impure split.** All value math — increment grids, plain-numeric-expression detection, rounding, label formatting, and the smart-default heuristic — lives in `rounding.py`, which imports no `adsk` and no sibling module, so it is unit-tested outside Fusion (`tests/test_roundsketchdimensions_rounding.py`). `entry.py` holds only the command lifecycle, dialog, and the sketch read/write.
- **Idempotent apply.** `_apply_rounding` reads each dimension's *current* value and snaps it, so re-running it (as happens on every preview refresh) never compounds. This is what makes the preview/rollback model robust.
- **Parametric-intent preservation.** Only dimensions whose expression is a plain constant are rounded; formula/parameter-driven expressions and read-only (driven/reference) parameters are skipped. Read-only writes are additionally guarded by try/except.
- **Fixed-length increment grids.** For imperial documents the Fractions and Decimal grids share a length, so the increment slider is created once (min/max never change) and only its index interpretation and label change when the format is toggled.
- **Grid unit.** Metric documents round on a millimetre grid; imperial documents round on an inch grid. Values are read from the parameter in internal centimetres and converted with a fixed `cm-per-unit` factor, avoiding a dependency on `unitsManager.convert`.

### System context

```mermaid
C4Context
    title System Context — Round Sketch Dimensions
    Person(user, "Fusion User", "Designer editing a sketch in Autodesk Fusion")
    System(addin, "Round Sketch Dimensions", "Power Tools command that rounds a sketch's dimensions to a grid")
    System_Ext(fusion, "Autodesk Fusion", "CAD platform and host application")
    Rel(user, addin, "Invokes from Sketch > Modify; sets increment/mode/preview")
    Rel(addin, fusion, "Reads and writes SketchDimension parameter expressions")
    Rel(fusion, user, "Shows live preview and recomputes the sketch")
```

### Component diagram

```mermaid
C4Component
    title Component Diagram — Round Sketch Dimensions
    Container_Boundary(addin, "Round Sketch Dimensions Command") {
        Component(dialog, "command_created()", "Python", "Builds the dialog: units, mode, selection, format, increment slider, preview")
        Component(changed, "command_input_changed()", "Python", "Toggles selection visibility, swaps grid, refreshes the increment label")
        Component(preview, "command_execute_preview()", "Python", "Applies rounding live when Preview is on; sets isValidResult to commit on OK")
        Component(execute, "command_execute()", "Python", "Applies rounding for the no-preview path")
        Component(validate, "command_validate()", "Python", "Enables OK only when there is eligible, targeted work")
        Component(apply, "_apply_rounding()", "Python", "Iterates eligible dimensions and writes rounded expressions (idempotent)")
        Component(pure, "rounding.py", "Pure Python", "Increment grids, eligibility parser, round-to-grid, labels, smart default")
    }
    System_Ext(fusion, "Autodesk Fusion Sketch Engine", "Recomputes the sketch as dimension expressions change")
    Rel(dialog, changed, "Wires event")
    Rel(dialog, pure, "Smart default + labels")
    Rel(changed, pure, "Increment labels")
    Rel(preview, apply, "On each refresh")
    Rel(execute, apply, "On OK (no preview)")
    Rel(apply, pure, "Eligibility + rounding")
    Rel(apply, fusion, "Sets parameter.expression")
    Rel(preview, fusion, "Live preview; reverts on Cancel")
```
