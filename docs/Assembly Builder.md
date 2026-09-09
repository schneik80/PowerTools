# Assembly Builder

[Back to PowerTools Assembly](../README.md)

The Assembly Builder command opens a visual node editor that lets you design an assembly hierarchy before any components exist. You place Assembly, Part, and Hybrid nodes on a canvas, connect them to form a tree (optionally with shared children), optionally link project **global parameter** sets to specific components, then generate every external component in a single action. Each generated document is created with the correct design intent automatically, shared children are inserted by reference, and linked parameter sets are derived into the components that need them.

## What you can do

- Design an assembly hierarchy in a palette-based visual node editor powered by [Drawflow](https://github.com/jerosoler/Drawflow).
- Add **Assembly**, **Part**, and **Hybrid** nodes by clicking them in the sidebar.
- With a node selected, clicking a sidebar template adds the new node already connected as its child.
- Connect nodes by dragging from the output port (bottom) of a parent to the input port (top) of a child. Connector hit targets are enlarged so wiring is easy without enlarging the visible ports.
- Share a single child between multiple parents by connecting it to more than one parent.
- Add a **Global Parameters** node for any parameter set found in the active project's `_Global Parameters` folder, then connect it to the components that should derive it. Each parameter document can be added once; its button disables while it is on the canvas and re-enables if you delete the node.
- New nodes get incrementing default names per type (`Assembly 1`, `Part 1`, `Hybrid 1`, …); double-click a node's name to rename it before generating.
- **Import SysML** builds the whole hierarchy from a SysML v2 physical view — the file written by [Export SysML Architecture Document](./Export%20SysML.md), or an equivalent model from another tool. See [Importing a SysML physical view](#importing-a-sysml-physical-view).
- **Arrange** lays the graph out as a clean org chart; zoom (Ctrl+scroll) and pan (drag empty canvas); use **Fit** to recenter.
- Generate every external component in one step with **Create Assembly**.
- Design intent is applied per node type automatically (Part / Assembly / Hybrid).
- Palette theme follows the Fusion UI theme — light, dark, or **match OS device theme** — and is correct on first paint.

## Prerequisites

- An Autodesk Fusion 3D Design must be active.
- The active document must be **new (unsaved)**, **or** a **saved document that is still empty** — no timeline features, bodies, sketches, or child components.
- The active design's design intent must be **Assembly** or **Hybrid** (not **Part**).
- The active design must have **no existing child components** at the root.
- An **active project** in the Data Panel is required to store the generated external components.

If any of these conditions is not met, Assembly Builder displays a message explaining what to change and does not open the palette.

> **Note:** When the design contains shared parts or linked global parameters, the document must be saved before generation (these need a cloud `DataFile`). A banner appears across the bottom of the palette and **Create Assembly** is disabled until you save (Ctrl+S); it re-enables automatically. A saved-but-empty starting document satisfies this immediately.

> **Note:** If no project is active (the Data Panel is showing the hub root), a *No target project* banner appears and **Create Assembly** is disabled — the new components have nowhere to be stored. Open the Data Panel, click into the project you want, then press **Re-check** on the banner (or simply click back into the palette; it re-checks automatically when it regains focus). This gate takes precedence over the save banner.

## How to use Assembly Builder

1. In Autodesk Fusion, create a new design with **File > New Design** (or open a saved, still-empty design).
2. Confirm the design intent is **Assembly** or **Hybrid**.
3. On the **Power Tools** panel in the Design workspace, select **Assembly Builder**.
4. Click an **Assembly**, **Part**, or **Hybrid** button in the palette sidebar to add a node to the canvas. Select an existing node first to add the new one already connected as its child.
5. Drag from the output port at the bottom of a parent node to the input port at the top of a child node to connect them.
6. Double-click a node's name to rename it. This name becomes the Fusion component name.
7. To share a child across multiple parents, connect the same child to more than one parent.
8. To apply a project parameter set, click its button under **Global Parameters** in the sidebar and connect the resulting node to each component that should derive it.
9. If the **save** banner is shown (shared parts or global parameters present), save the document (Ctrl+S). **Create Assembly** enables automatically.
   - If a **No target project** banner is shown instead, select a project in the Data Panel and press **Re-check**; **Create Assembly** enables once a project is available.
10. When the hierarchy is complete, select **Create Assembly**.

> **Tip:** To start from an assembly that already exists as a systems model rather than drawing the tree by hand, select **Import SysML** at step 4 — see [Importing a SysML physical view](#importing-a-sysml-physical-view). Steps 5 to 10 are unchanged afterwards.

Generation runs in three passes:

1. **Build** — the graph is walked top-down and `addNewExternalComponent` is called for each child, applying design intent per node type.
2. **Flush & shared inserts** — the document is saved once to flush the new external documents to cloud `DataFile`s, then each shared child is inserted into its additional parents via `addByInsert`.
3. **Derive parameters** — for every component linked to a parameter node, the component document is opened, the parameter set is derived in (favorite parameters, inserted first in the timeline), and the document is saved. Progress is shown in a dialog (one step per document) and each cloud upload is awaited so versions are current. Finally the root assembly pulls all references to latest (`updateAllReferences`) and is saved.

External component saves and the final root save use the comment **"Updated with Assembly Builder"**.

> **Note:** Because `addNewExternalComponent` requires an Autodesk Hub folder, the active project's root folder is used as the destination. You can move the generated documents afterward in the Data Panel. If there is no active project, **Create Assembly** is blocked by the *No target project* banner described above.

> **Note:** All validation and result messages are shown as native Fusion message boxes — there are no browser alert dialogs.

## Importing a SysML physical view

**Import SysML** reads a SysML v2 textual model and reconstructs its component hierarchy on the canvas, so an assembly that already exists as a systems model does not have to be re-drawn by hand. It is the inverse of [Export SysML Architecture Document](./Export%20SysML.md): export an assembly from one design, import it into a new one, and you have the same structure ready to generate.

1. Select **Import SysML** in the palette toolbar.
2. If the canvas already holds more than the root node, Fusion asks whether to discard it. Importing **replaces** the graph rather than merging into it.
3. Choose a `.sysml` file.
4. A summary dialog reports what was imported and anything that could not be represented.
5. Review and adjust the graph, then select **Create Assembly** as usual.

### What is read

SysML v2 has two idiomatic ways to record composition, and both are read:

- **In the definitions** — `part def Gearbox { part housing : Housing; }`. This is what Export SysML Architecture Document writes, since it emits one definition per unique component.
- **In the usage tree** — `part rm500 : MowerProduct { part mower : MowerAssembly { part chassis : ChassisAssembly { … } } }`. This is how a hand-authored physical architecture usually reads: one nested instance tree under a single top-level usage.

Both say the same thing — the enclosing component contains the enclosed one — so a `part` usage always becomes a child of whatever component encloses it, whether that came from a `part def` header or from the type of an enclosing usage.

The node type comes from the `classification` attribute the export command writes (`part`, `empty` → Part; `subassembly` → Assembly; `hybrid` → Hybrid). A model that carries no `classification` is read from its structure instead: a component containing usages becomes an Assembly, one containing none becomes a Part. Hybrid is never guessed from structure alone.

The root is the package-level `part` usage — the line that names the design itself rather than a child. Where a file has several (a stakeholders package that declares `part chiefEngineer : Role;` contributes one for each role), the one whose type actually has contents wins; if more than one does, the largest is used and the summary says so. The root node on the canvas keeps the **active document's** name, because that node *is* the document you are building into; the imported root's own name is not applied to it.

Statements that say nothing about composition — imports, `doc` blocks, attributes, ports, interfaces, connections, concerns, requirements, allocations, views and `@Metadata` annotations — are skipped, so a full model from an MBSE tool imports without being cut down first. Specialisation and redefinition in a usage header (`part mower : MowerAssembly :> subItems { … }`) are read past rather than tripped over.

`item` declarations are deliberately **not** components. SysML uses items for things that flow and for material definitions, so a model that declares `item pa6gf30 : Material` does not import glass-filled nylon as a part.

### What cannot be represented

The summary dialog names each of these; nothing is dropped silently.

- **Quantities above one.** The node editor holds one node per component and the canvas allows only one link between the same two nodes, so `part shaft : 'Shaft'[2]` imports as a single link. The dialog lists every collapsed quantity so you can add the extra instances after generating. Two separate usages of the same type under one parent are summed into that one figure. A multiplicity range contributes its first bound (`[2..4]` reads as two) and an optional component (`[0..1]`) still gets its single link.
- **Variation points.** A `variation part guidance : … { variant part rtkMast : …; variant part wireReceiver : …; }` describes alternatives, not parts that are all fitted, so none of them is imported. Importing every alternative would overstate the assembly. They are named in the summary.
- **Components the root does not contain.** Generation only walks down from the root, so a definition nothing contains would appear on the canvas and never be built. It is reported as not imported instead.
- **Usages of an undefined type.** A `part x : Missing` whose definition is absent from the file is reported and skipped.
- **A component that contains itself.** The offending link is left out and reported; the rest of the hierarchy still imports.
- **External references.** A component that was linked from another document in the source design is reported, and will be created as a **new** external component rather than a link to the original.

Shared components survive intact: a definition used by two parents imports as one node with two links, which is exactly how the editor represents a shared child.

## Access

The **Assembly Builder** command is located on the **Utilities** tab, in the **Power Tools** panel of the Autodesk Fusion Design workspace.

> **Developers:** see the [architecture notes](./arch/Assembly%20Builder.md).

---

[Back to PowerTools Assembly](../README.md)

---

*Copyright © 2026 IMA LLC. All rights reserved.*
