# Assembly Builder

[Back to README](../README.md)

## Overview

Assembly Builder lets you design an assembly hierarchy in a visual node editor, then generates every external component with the correct design intent in one step.

SolidWorks Premium ships Treehouse for this: plan the structure of an assembly as a tree before any geometry exists, then have the files created. Fusion has no equivalent, so a distributed design starts with the same sequence repeated per component: create, name, set intent, save. Assembly Builder is the planning canvas for Fusion. You place Assembly, Part and Hybrid nodes, wire them into a tree, share a child between parents where the real product does, link project [Global Parameters](./Global%20Parameters.md) sets to the components that should derive them, and select **Create Assembly**. It can also build the whole tree from a SysML v2 model, including one written by [Export SysML Architecture Document](./Export%20SysML.md).

## Prerequisites

- A design document must be active.
- The document must be new (unsaved), or saved but still empty: no timeline features, bodies, sketches or child components.
- The design's intent must be Assembly or Hybrid.
- To generate, a project must be active in the Data Panel; the palette opens without one but **Create Assembly** stays disabled until you pick one.
- With shared children or parameter links in the graph, the document must be saved before generating.

If the document is not new-or-empty, or has Part intent, a message says what to change and the palette does not open.

## Where to find it

**Utilities** tab › **Power Tools** panel › **Assembly Builder**, in the Design workspace. The [Assembly Palette](./Assembly%20Palette.md) also opens it for a new, unsaved document.

## How to use

1. Create a new design (**File › New Design**) and confirm the intent is Assembly or Hybrid, or open a saved, still-empty design.
2. Select **Assembly Builder**. The palette opens docked on the right.
3. Select **Assembly**, **Part** or **Hybrid** in the sidebar to add a node. With a node selected, the new node is added already connected as its child.
4. Drag from a parent's output port (bottom) to a child's input port (top) to connect them. A child connected to more than one parent is shared.
5. Double-click a node's name to rename it; the name becomes the component name.
6. To derive a parameter set into components, select its button under **Global Parameters** in the sidebar and connect the resulting node to each component. Each set can be on the canvas once.
7. Use **Arrange** to lay the graph out as an org chart, **Fit** to recentre, Ctrl+scroll or the zoom buttons to zoom, **Clear All** to start over.
8. If a banner asks you to save, save (**Ctrl+S**); if it says *No target project*, open a project in the Data Panel and select **Re-check** (the palette also re-checks when it regains focus).
9. Select **Create Assembly**.

Generation runs in three passes:

1. **Build.** The graph is walked top-down and each child is created as a new external component with the intent of its node type. The root document itself is set to Assembly intent.
2. **Shared children.** When the graph has shared children or parameter links, the document is saved once (comment `Assembly Builder: flushing components`) so the new documents exist in the cloud, and each shared child is inserted into its additional parents by reference.
3. **Parameters.** For every component linked to a parameter node, the component document is opened, the set is derived in as favorites at the start of its timeline, and the document is saved. A cancellable progress dialog shows one step per document, and each upload is awaited (up to 120 seconds) so versions are current. The root then updates all references and is saved with the comment `Updated with Assembly Builder`.

The palette hides when generation finishes. New documents are created in the active document's folder when it is saved, or in the active project's root folder when it is not; you can move them afterwards in the Data Panel.

## Options

| Control | Effect |
|---|---|
| **Assembly**, **Part**, **Hybrid** | Add a node of that type, named `Assembly 1`, `Part 1`, … |
| **Global Parameters** buttons | One per set in the project's `_Global Parameters` folder; adds a parameter node |
| **Import SysML** | Replace the graph with the hierarchy read from a `.sysml` file |
| **Arrange**, **Fit**, zoom, **Clear All** | Layout and view |
| **Create Assembly** | Generate. Disabled while a banner shows |

The root node is the document you are building into: it cannot be deleted and keeps the document's name. Parameter nodes are read-only. The palette follows Fusion's light or dark theme.

## Importing a SysML physical view

**Import SysML** reads a SysML v2 textual model and reconstructs its component hierarchy on the canvas, so a systems model does not have to be redrawn by hand. It is the inverse of Export SysML Architecture Document: export from one design, import into a new one, generate.

1. Select **Import SysML**. If the canvas holds more than the root node, you are asked whether to discard it; importing replaces the graph.
2. Choose a `.sysml` file.
3. A summary reports what was imported and anything that could not be represented.
4. Adjust the graph and select **Create Assembly**.

### What is read

Composition recorded either way is read: inside definitions (`part def Gearbox { part housing : Housing; }`, which is what the export writes) or as a nested usage tree (`part rm500 : MowerProduct { part mower : MowerAssembly { … } }`). A `part` usage always becomes a child of the component that encloses it.

The node type comes from the `classification` attribute the export writes: `part`, `leaf` or `empty` give Part, `subassembly` or `assembly` give Assembly, `hybrid` gives Hybrid. A part classification on a component that turns out to have children is corrected to Assembly, or to Hybrid when it also has bodies. A model with no classification is read from its structure: children and bodies make a Hybrid, children alone an Assembly, neither a Part.

The root is the package-level `part` usage that names the design. Where a file has several, the one whose type has contents wins; if more than one does, the largest is used and the summary says so. The root node keeps the active document's name.

Imports, `doc` blocks, attributes, ports, interfaces, connections, requirements, allocations, views and `@Metadata` are skipped, so a full MBSE model imports without trimming. `item` declarations are not components, so a material declared as an item does not become a part.

### What cannot be represented

The summary names each of these; nothing is dropped silently.

- **Quantities above one.** The canvas holds one node per component and one link between two nodes, so `part shaft : 'Shaft'[2]` imports as one link. Every collapsed quantity is listed so you can add instances after generating. A range contributes its first bound; an optional component (`[0..1]`) still gets its link.
- **Variation points.** Alternatives in a `variation` block are not all fitted, so none is imported; they are listed.
- **Components the root does not contain**, **usages of an undefined type**, and **a component that contains itself** are reported and left out; the rest imports.
- **External references** in the source design are reported and created as new external components rather than links to the originals.

Shared components survive: a definition used by two parents imports as one node with two links.

> **Developers:** see the [architecture notes](./arch/Assembly%20Builder.md).

---

[Back to README](../README.md)

*Copyright © 2026 IMA LLC. All rights reserved.*
