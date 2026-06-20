# Infer Constraints

[Back to PowerTools Assembly](../README.md)

The Infer Constraints command looks at an assembly whose components are already in their final spatial position — most often a STEP import — but which has no relationships between them, and proposes relationships based on the geometry that is already mating. It detects coaxial cylindrical faces (shaft-in-hole) and flush planar faces, grounds the first component, and lists what it finds with a confidence score so you can choose which relationships to apply. Everything it applies is **position-preserving** — components do not move when a relationship is created — and it automatically skips redundant relationships so the assembly is not over-constrained.

## What you can do

- **Ground the first component:** the first entry is always a *Ground to Parent* relationship on the first component in the browser, giving the assembly a fixed reference.
- Detect **concentric** relationships between coaxial cylindrical faces (including shaft-in-hole pairs with clearance).
- Detect **coincident** relationships between planar faces that lie flush against one another.
- Recognize **centered** coincident faces (whose centroids also coincide) and connect them with a **Joint** at the shared face center. For these rows you pick the joint motion type from a dropdown — **Rigid** (default), Revolute, Slider, Cylindrical, Pin-Slot, Planar, or Ball.
- Review every inferred relationship in a preview table with the participating components and a confidence score, and click a row's **Components** button to highlight that pair in the graphics.
- Adjust the linear and angular tolerances and re-scan to widen or tighten detection.
- Select exactly which relationships to apply; high-confidence rows are pre-selected.
- Apply everything in one step without moving the components, and let the command **drop redundant relationships** that would over-constrain the assembly.

## Prerequisites

- An Autodesk Fusion 3D Design must be active.
- The assembly should already be **positioned** — the command infers relationships from geometry that is mating in the current pose; it does not move components into place.
- The design needs **component occurrences** (or solid bodies in the root) that expose analytic **planar** or **cylindrical** faces — typical of imported solids.
- **Preview API:** creating assembly constraints relies on Fusion's Assembly Constraints API, which Autodesk currently ships as a **preview** capability. On builds where it is unavailable, detection and the preview table still work, but applying a constraint reports an error. Joints (used for centered pairs and grounding) use the released API. See the [architecture notes](./Arch/Infer%20Constraints.md).

## How to use Infer Constraints

1. Open the assembly you want to constrain (for example, after inserting a STEP file).
2. On the **Utilities** tab, open the **Power Tools** panel and click **Infer Constraints**.
3. The command scans the assembly and fills the **Inferred relationships** table. Each row shows the relationship type, the two components, and a confidence score. The first row is always a **Ground to Parent** relationship on the first component in the browser.
4. Click a row's **Components** button to **highlight that relationship's pair in the graphics window** (for a Ground row, the single grounded component is highlighted), so you can see exactly what each relationship connects.
5. (Optional) Adjust **Linear tolerance** or **Angular tolerance** and click **Re-scan** to refine the results. Looser tolerances find more (and weaker) candidates; tighter tolerances keep only near-exact matches.
6. For any centered (Joint) row, choose the motion type from its dropdown (Rigid by default).
7. Check the relationships you want to apply. Rows with a confidence of 0.60 or higher are checked for you.
8. Click **OK** to apply. The command captures the current position first, then applies the selected relationships — grounding first, then strongest relationships first — and reports how many were created, how many redundant ones were skipped, and whether anything moved.

> **Note:** Inferring relationships is inherently ambiguous — research on this problem puts the realistic single-best-answer accuracy near 73%. Treat the list as ranked suggestions and review the low-confidence rows before applying.

## Access

**Infer Constraints** is on the **Design** workspace **Utilities** tab, in the **Power Tools** panel.

> **Developers:** see the [architecture notes](./Arch/Infer%20Constraints.md).

---

[Back to PowerTools Assembly](../README.md)

---

*Copyright © 2026 IMA LLC. All rights reserved.*
