# Export SysML Architecture Document

[Back to README](../README.md)

## Overview

The **Export SysML Architecture Document** command exports the active Autodesk Fusion assembly as a 4+1 architecture design document with a SysML physical view. Use this command to hand a mechanical design to a systems engineering team, or to a Model-Based Systems Engineering (MBSE) toolchain, without retyping the assembly structure by hand.

Two files are written: an **Architecture Design Document (ADD)** in Markdown, organised on the [4+1 View Model](https://en.wikipedia.org/wiki/4%2B1_architectural_view_model), and a **SysML v2 model** in textual notation that the document references.

A Fusion design is the authoritative source for exactly one of the five 4+1 views — the Physical View — so that view is generated in full. Two more views are partly derivable and are populated with what the design actually records. The remaining two require human intent, and the document says so rather than leaving a heading empty.

| View | Source | What the command does |
|---|---|---|
| **Logical** | — | Adds the heading and states that it must be authored by hand |
| **Process** | Fusion joints | Derived: a table of joints — type, what they connect, origin, axis, and which permit motion |
| **Development** | Fusion external references | Derived: a table of linked documents, versions and instance counts |
| **Physical** | Fusion assembly structure | Generated: hierarchy, quantities, mass, envelope, interfaces, and the SysML model |
| **Scenarios (+1)** | — | Adds the heading and states that it must be authored by hand |

## Prerequisites

- An Autodesk Fusion design document must be active.
- The design must be an assembly or a hybrid — that is, the root component must contain at least one child component. A design with no child components has no physical decomposition to document, and the command declines to export one.

## How to use this command

1. Open an assembly design in Autodesk Fusion.
2. From the **File** drop-down menu in the Quick Access Toolbar, select **Export SysML Architecture Document...**.
3. In the folder browser dialog, navigate to the destination folder for the two output files.
4. Click **OK**. Power Tools walks the assembly and writes both files. On a large assembly a progress dialog appears; you can cancel it, and nothing is written if you do.
5. A confirmation dialog lists both filenames and the folder they were written to.

## Output

Two files are written directly into the folder you chose, both named after the active document:

| File | Contents |
|---|---|
| `{DocumentName}-ADD.md` | The architecture design document: document control, the five 4+1 views, a component inventory, and appendices |
| `{DocumentName}-physical.sysml` | The Physical View as a SysML v2 textual model |

Files of the same name in that folder are overwritten. Because the Logical View and Scenarios sections are meant to be written by hand, export into a new folder and copy your authored sections across rather than exporting over a document you have already written into.

### What the Physical View records

For every unique component in the assembly:

- **Identity** — name, part number, description, and material.
- **Classification** — `part` (bodies only), `subassembly` (children only), `hybrid` (bodies *and* children), or `empty` (neither).
- **Quantity** — the total number of instances across the whole assembly, and the multiplicity under each parent.
- **Mass, volume and surface area**, and the centre of mass.
- **Bounding box** — the component's envelope, in millimetres.
- **Interfaces** — joints, rendered as SysML connections.

A component is measured once no matter how many times it is used, so a fastener used two hundred times costs one measurement rather than two hundred.

### Units

The output uses fixed units so that two exports of the same design can be compared directly: **length in millimetres, mass in kilograms, volume in cm³, area in cm²**. The document's own default length unit is recorded in the Document control table for reference, but it does not change the output.

### Missing values

Fusion cannot always evaluate a physical property. Where it could not, the document shows an em dash (—) and the SysML model omits the attribute entirely. Neither ever substitutes a zero, because a zero cannot be told apart from a real measurement. Every value that could not be read is listed in the document's **Collection notes** appendix.

The command also declines to compute a total assembly mass. The Fusion API does not document whether a component's reported mass and bounding box include its child components, so the document reproduces what Fusion returns per component rather than summing figures that might double-count subassemblies.

## Example output

The SysML model for a small assembly — a gearbox whose bearing block carries both its own body and two shafts:

```sysml
package 'Gearbox Physical View' {
    private import ScalarValues::*;

    connection def RevoluteJoint;

    part def 'Housing' {
        attribute partNumber : String = "PN-1001";
        attribute classification : String = "part";
        attribute massKg : Real = 1.24;
        attribute bboxLengthMm : Real = 120;
    }

    part def 'Shaft' {
        attribute classification : String = "part";
    }

    part def 'Bearing Block' {
        attribute classification : String = "hybrid";
        part shaft : 'Shaft'[2];
    }

    part def 'Gearbox' {
        attribute classification : String = "subassembly";
        part housing : 'Housing';
        part bearingBlock : 'Bearing Block';

        connection 'Pivot' : RevoluteJoint connect housing to bearingBlock;
    }

    part gearbox : 'Gearbox';
}
```

Each unique component becomes one `part def`, and composition lives inside the definitions — so a subassembly used three times is written once, and the model file stays proportional to the number of distinct components rather than the number of occurrences.

> **Tip:** The generated `.sysml` file can be read back in. [Assembly Builder](./Assembly%20Builder.md)'s **Import SysML** button reconstructs this hierarchy as a node graph, so an assembly exported from one design can be regenerated as external components in another.

The accompanying document opens like this:

```markdown
# Gearbox — Architecture Design Document

> Generated file. Regenerate it with File › Export SysML Architecture
> Document... in Autodesk Fusion rather than editing the generated sections.

## Document control
## Architectural representation
## 1. Logical View
## 2. Process View
## 3. Development View
## 4. Physical View
## 5. Scenarios (+1)
## Appendix A — Collection notes
## Appendix B — Regeneration
```

### Joints that cannot be modelled

A joint becomes a SysML connection when both of its ends sit somewhere below the component that owns the joint, and the joint is not suppressed. An end deeper than a direct child is named by a dotted path, so a joint between two different subassemblies is still expressed. Fusion also allows joints that do not meet that test — one anchored to geometry belonging to no component, or one reaching outside the owning component altogether. Those are still reported, in the Process View table and as comments in the model file, together with the reason they could not be expressed. A suppressed joint is never written as a connection, because it is not part of the built configuration.

### What a connection records

Each joint kind is written as a connection definition carrying the degrees of freedom that kind permits, so a revolute joint is distinguishable from a ball joint without opening Fusion. A kind whose motion its name does not fix — an inferred joint — omits the counts rather than claiming zero. The connection definition names its two ends `occurrenceOne` and `occurrenceTwo`, and each connection gives them **in Fusion's order** — the first named component is `occurrenceOne`, the one that moves relative to the second. Each connection also carries a comment giving the occurrence names Fusion gave those ends. Those names are the only record of *which* of two identical parts a joint holds, because the model file declares one usage per component.

Each connection also records **where the joint is and which way it acts**, in the root component's coordinates:

| Attribute | Meaning |
|---|---|
| `originXMm`, `originYMm`, `originZMm` | The joint's origin, in millimetres |
| `axisX`, `axisY`, `axisZ` | A unit vector along the joint's primary axis |
| `axisRole` | What that axis governs — `rotation`, `translation`, `normal` or `pitch` |

The axis read depends on the kind: a revolute or cylindrical joint reports its rotation axis, a slider its slide direction, a planar joint its normal, a ball joint its pitch direction. A rigid joint has no axis and reports none; nor does an inferred joint, whose motion its kind does not fix. A pin-slot and a planar joint each have a second axis, and only the primary one is exported — `axisRole` says which it is.

Any of these may be absent. A joint whose geometry Fusion could not evaluate leaves the origin unset, and an unset attribute is not zero: writing zeros would place the joint at the model origin pointing nowhere, indistinguishable from a measurement.

```sysml
connection 'Pivot' : RevoluteJoint connect housing to bearingBlock {
    attribute :>> originXMm = 12;
    attribute :>> originYMm = 0;
    attribute :>> originZMm = 45;
    attribute :>> axisZ = 1;
    attribute :>> axisRole = "rotation";
}
```

## Access

From the design document's **File** drop-down menu in the Quick Access Toolbar, select **Export SysML Architecture Document...**. It sits alongside **Export BOM as CSV** and **Export Mermaid Diagram...**.

> **Developers:** see the [architecture notes](./arch/Export%20SysML.md).

---

[Back to README](../README.md)

*Copyright © 2026 IMA LLC. All rights reserved.*
