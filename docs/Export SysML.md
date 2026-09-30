# Export SysML Architecture Document...

[Back to README](../README.md)

## Overview

Export SysML Architecture Document writes the active assembly as a 4+1 architecture design document with a SysML v2 physical view.

Model-based systems engineering tools such as Cameo and Capella describe a product's physical architecture in SysML, and a mechanical team is usually asked to retype the assembly structure into them by hand. This command generates that view from the Fusion design itself: hierarchy, quantities, mass, envelope and joints, in SysML v2 textual notation, plus a Markdown design document organized on the [4+1 View Model](https://en.wikipedia.org/wiki/4%2B1_architectural_view_model) with the views a CAD model can populate filled in and the others left for a human.

| View | Source | What is written |
|---|---|---|
| **Logical** | — | Heading and a note that it must be authored by hand |
| **Process** | Fusion joints | A table of joints: type, what they connect, origin, axis and state |
| **Development** | External references | A table of linked documents, versions and instance counts |
| **Physical** | Assembly structure | Hierarchy, quantities, mass, envelope, interfaces, and the SysML model |
| **Scenarios (+1)** | — | Heading and a note that it must be authored by hand |

## Prerequisites

- A design document must be active.
- The root component must contain at least one child component. A design with no children has no physical decomposition, and the command says so and stops.

## Where to find it

**File › Export SysML Architecture Document...** on the Quick Access Toolbar, directly before **Export**, next to **Export BOM as CSV** and **Export Mermaid Diagram...**.

## How to use

1. Open the assembly.
2. Select **File › Export SysML Architecture Document...**.
3. Choose the destination folder and select **OK**. Cancelling writes nothing.
4. On an assembly of 25 or more components a progress dialog appears; cancelling it writes nothing.
5. A dialog lists the two files and the folder.

## What it produces

Two files in the chosen folder, named after the document. Files of the same name are overwritten, so export into a new folder rather than over a document you have written into.

| File | Contents |
|---|---|
| `<document name>-ADD.md` | Document control, the five views, a component inventory, and appendices |
| `<document name>-physical.sysml` | The Physical View as a SysML v2 textual model |

### What the Physical View records

For every unique component:

- **Identity**: name, part number, description, material, and whether it is an external reference.
- **Classification**: `part` (bodies only), `subassembly` (children only), `hybrid` (bodies and children) or `empty` (neither).
- **Quantity**: total instances across the assembly, and the multiplicity under each parent.
- **Mass, volume, surface area** and centre of mass, including the component's children.
- **Bounding box** in millimetres, largest side first, including children. A component that encloses nothing reports no envelope rather than zeros.
- **Interfaces**: joints, rendered as SysML connections.

A component is measured once no matter how many times it is used. Physical properties are read at Fusion's low calculation accuracy (about ±1%).

### Units and missing values

Output units are fixed so two exports compare directly: length in millimetres, mass in kilograms, volume in cm³, area in cm². The document's own unit is recorded in the Document control table but does not change the output.

Where Fusion cannot evaluate a property, the document shows an em dash and the model omits the attribute. A zero is never substituted, because it cannot be told from a measurement. Every value that could not be read is listed in **Appendix A — Collection notes**.

### Figures include children, and do not add up

Mass, volume, area and the bounding box all include a component's children, so the inventory's Mass column does not sum: adding it over every row counts each subassembly's contents twice. The document says so under the table, with the figures for your design, and reports the root's total directly.

### Example

A gearbox whose bearing block carries its own body and two shafts:

```sysml
package 'Gearbox Physical View' {
    private import ScalarValues::*;

    abstract part def FusionComponent;
    abstract connection def FusionJoint { ... }
    connection def RevoluteJoint :> FusionJoint {
        attribute :>> rotationalDOF = 1;
        attribute :>> translationalDOF = 0;
    }

    part def 'Housing' :> FusionComponent {
        attribute partNumber : String = "PN-1001";
        attribute classification : String = "part";
        attribute massKg : Real = 1.24;
        attribute bboxLengthMm : Real = 120;
        attribute bboxWidthMm : Real = 80;
        attribute bboxHeightMm : Real = 60;
    }

    part def 'Bearing Block' :> FusionComponent {
        attribute classification : String = "hybrid";
        part shaft : 'Shaft'[2];
    }

    part def 'Gearbox' :> FusionComponent {
        attribute classification : String = "subassembly";
        part housing : 'Housing';
        part bearingBlock : 'Bearing Block';
        connection 'Pivot' : RevoluteJoint connect housing to bearingBlock;
    }

    part gearbox : 'Gearbox';
}
```

Each unique component is one `part def`, and composition lives inside the definitions, so a subassembly used three times is written once and the file stays proportional to the number of distinct components.

> **Tip:** [Assembly Builder](./Assembly%20Builder.md) reads this file back. Its **Import SysML** button reconstructs the hierarchy as a node graph, so an assembly exported from one design can be regenerated as external components in another.

### Joints

A joint becomes a SysML connection when both of its ends sit below the component that owns the joint and the joint is not suppressed. An end deeper than a direct child is named by a dotted path. Joints that do not meet that test, anchored to geometry outside any component or reaching outside the owning component, are still reported in the Process View table and as comments in the model, with the reason.

Each joint kind is a connection definition carrying the degrees of freedom it permits. Each connection names its ends `occurrenceOne` and `occurrenceTwo` in Fusion's order, carries a comment with the occurrence names, and records where the joint is and which way it acts in the owning component's coordinate space:

| Attribute | Meaning |
|---|---|
| `originXMm`, `originYMm`, `originZMm` | The joint's origin, in millimetres |
| `axisX`, `axisY`, `axisZ` | A unit vector along the joint's primary axis |
| `axisRole` | What that axis governs: `rotation`, `translation`, `normal` or `pitch` |

A revolute or cylindrical joint reports its rotation axis, a slider its slide direction, a planar joint its normal, a ball joint its pitch direction. A rigid joint has no axis; nor does an inferred joint. An as-built joint records no origin, because Fusion has no picked point to report; the Process View says how many there are.

## Limitations

- Nesting deeper than 64 levels is not documented; a note says so.
- The Logical and Scenarios views are headings only.
- Two joint origins under different definitions are in different frames and cannot be compared directly.

> **Developers:** see the [architecture notes](./arch/Export%20SysML.md).

---

[Back to README](../README.md)

*Copyright © 2026 IMA LLC. All rights reserved.*
