# Create Mirrored Design

[Back to README](../README.md)

## Overview

**Create Mirrored Design** derives all solid bodies from the active saved design into a brand-new document, saves the new document as `<active-name>-mirror` in the same Fusion data folder, and applies a uniform scale of `-1` to all derived bodies — producing a geometrically mirrored copy of the part without modifying the source ( this trick to use scale with a factor of -1 is known as the "Lockwood Manuever")

> **Note:** The source design must be saved to Fusion before running this command. Unsaved designs cannot be Mirrored.

## Prerequisites

- An Autodesk Fusion design is open and active.
- The design has been saved to Fusion (it has a cloud data file).
- The active workspace is the **Design** workspace (`FusionSolidEnvironment`).

## Access

**Create Mirrored Design** is located in the Design workspace under **Solid &rsaquo; Create**, immediately after the built-in Derive command.

1. Open a saved 3D design in Autodesk Fusion.
2. Switch to the **Design** workspace if not already active.
3. Click the **Solid** tab in the toolbar.
4. Expand the **Create** panel.
5. Click **Create Mirrored Design** (listed after **Derive**).

## How to use

1. Open the 3D design you want to mirror and make it the active document.
2. Confirm the design has been saved to Fusion (a cloud icon with no unsaved indicator).
3. Navigate to **Solid &rsaquo; Create** and click **Create Mirrored Design**.
4. The command validates the active design, collects all solid bodies, and derives them into a new Fusion design document.
5. The new document is saved automatically as `<source-name>-mirror` in the same Fusion data folder as the source.
6. A scale feature (factor `1`) is created for each component's bodies using the component origin as the reference point.
7. Each scale feature's parameter expression is immediately edited to `-1` via the ModelParameter API.
8. The mirror document is saved a second time to commit the scale changes.
9. A confirmation message displays the name of the mirrored design.

## Expected results

- A new document named `<source-name>-mirror` appears in the same Fusion project folder as the source design.
- All solid bodies in the mirrored design are flipped — equivalent to a mirror through the world origin — via a parametric scale `-1` feature.
- The source design is not modified.
- The parametric scale features in the mirror document remain editable in the timeline.

## Limitations

- The source design **must be saved** to Fusion. Local/unsaved designs are rejected with an error message.
- If a document named `<source-name>-mirror` already exists in the same folder, the Save As operation will fail. Rename or delete the existing document first.
- Only **BRep solid bodies** are derived. Mesh bodies, sketch geometry, and construction geometry are not included in the derive operation.
- The command must be run from the **Design workspace**. It is not available in Drawing, Simulation, or Manufacturing workspaces.
- Multi-body components are each scaled independently using their own origin construction point.

---

## Architecture

### System context

```mermaid
C4Context
  title Create Mirrored Design — System Context

  Person(user, "Designer", "Runs the command from the Solid &gt; Create panel.")

  System(addin, "Create Mirrored Design", "Fusion Python add-in command that derives and mirrors design bodies.")

  System_Ext(fusion, "Autodesk Fusion", "Hosts the active design, runs derive and scale operations, and manages the document lifecycle.")

  System_Ext(fusiondata, "Fusion Data (Hub)", "Cloud storage layer that persists design documents and folders.")

  Rel(user, addin, "Clicks command button", "Toolbar UI")
  Rel(addin, fusion, "Reads source bodies, creates derive feature, creates scale features, edits parameters", "Fusion Python API")
  Rel(addin, fusiondata, "Saves mirror document to parent folder of source", "Document.saveAs()")
  Rel(fusion, fusiondata, "Persists documents", "Fusion internal")
```

### Component diagram

```mermaid
C4Component
  title Create Mirrored Design — Component Diagram

  Container_Boundary(addin, "Create Mirrored Design Add-In") {
    Component(button, "Toolbar Button", "CommandDefinition", "Entry point registered in the Create panel under the Solid tab, positioned after the built-in Derive command.")
    Component(cmd_execute, "command_execute()", "Python function", "Orchestrates the full workflow: validate → collect name → derive → saveAs → scale → parameter edit → save → notify.")
    Component(validate, "_validate_source_design()", "Python function", "Checks active product is a Design, workspace is FusionSolidEnvironment, and document has a cloud DataFile.")
    Component(collect_bodies, "_collect_source_bodies()", "Python function", "Iterates all components in the source design and collects every BRep body into a list for derive input.")
    Component(derive, "_derive_into_new_document()", "Python function", "Creates a new Fusion document, builds a DeriveFeatureInput with sourceEntities, executes the derive, and validates the result.")
    Component(scale, "_apply_post_derive_scale()", "Python function", "Iterates unique components in the derived design and creates a scale feature (factor 1) for each component's bodies using its origin construction point.")
    Component(param_edit, "_set_scale_parameter_to_negative_one()", "Python function", "Accesses ScaleFeature.scaleFactor (ModelParameter) and sets its expression to '-1' after feature creation.")
    Component(save_doc, "_save_mirror_document()", "Python function", "Resolves the parent folder of the source DataFile and calls Document.saveAs() with the <name>-mirror naming pattern.")
  }

  System_Ext(fusion_derive, "Fusion Derive Engine", "DeriveFeatures API — creates a parametric link from source bodies into the new document.")
  System_Ext(fusion_scale, "Fusion Scale Engine", "ScaleFeatures API — creates uniform scale features; ModelParameter API used to edit expressions post-creation.")
  System_Ext(fusion_data, "Fusion Data (Hub)", "Stores the saved mirror document in the same cloud folder as the source.")

  Rel(button, cmd_execute, "Triggers on click", "CommandEvent")
  Rel(cmd_execute, validate, "Calls first")
  Rel(cmd_execute, collect_bodies, "Calls after validation")
  Rel(cmd_execute, derive, "Calls with source design")
  Rel(cmd_execute, scale, "Calls after derive and saveAs")
  Rel(cmd_execute, save_doc, "Calls after derive, before scale")
  Rel(derive, fusion_derive, "Calls deriveFeatures.add(input)", "Fusion Python API")
  Rel(scale, param_edit, "Calls per scale feature")
  Rel(scale, fusion_scale, "Calls scaleFeatures.add(input)", "Fusion Python API")
  Rel(param_edit, fusion_scale, "Sets scaleFactor.expression = '-1'", "ModelParameter API")
  Rel(save_doc, fusion_data, "Saves mirror document", "Document.saveAs()")
```

---

[Back to README](../README.md)

*Copyright © 2026 IMA LLC. All rights reserved.*
