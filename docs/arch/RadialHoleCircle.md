# Radial Hole Circle — Architecture

[← Radial Hole Circle guide](../RadialHoleCircle.md)

## Architecture

### System context

```mermaid
C4Context
    title System Context — Radial Hole Circle
    Person(user, "Fusion User", "Part designer working in Autodesk Fusion")
    System(addin, "Radial Hole Circle", "Power Tools Add-in command that places a construction circle in an active sketch")
    System_Ext(fusion, "Autodesk Fusion", "CAD platform and host application")
    Rel(user, addin, "Invokes from Sketch > Create panel")
    Rel(addin, fusion, "Creates sketch geometry via Fusion API")
    Rel(fusion, user, "Updates viewport in real time")
```

### Component diagram

```mermaid
C4Component
    title Component Diagram — Radial Hole Circle
    Container_Boundary(addin, "Radial Hole Circle Command") {
        Component(button, "Command Button", "Fusion UI Control", "Toolbar button in Sketch > Create panel")
        Component(created, "command_created()", "Python", "Builds dialog UI and registers all event handlers")
        Component(input_changed, "command_input_changed()", "Python", "Captures selected center point and calibrates viewport offset")
        Component(mouse_move, "command_mouse_move()", "Python", "Computes radius from cursor and redraws preview graphics each frame")
        Component(mouse_click, "command_mouse_click()", "Python", "Locks radius, creates sketch geometry, fires commit event")
        Component(affine, "_mouse_to_sketch_plane()", "Python", "Maps args.position to sketch-plane world coords via affine screen-space inversion")
        Component(preview, "_update_preview()", "Python", "Draws white circle and crosshair via Custom Graphics API")
        Component(geometry, "_create_sketch_geometry()", "Python", "Adds circle, dimension, constraint, point, and guide line to sketch")
        Component(commit, "custom_event_commit()", "Python", "Deferred handler that calls doExecute(True) to close the command cleanly")
    }
    System_Ext(fusion, "Autodesk Fusion Sketch Engine", "Hosts the sketch, evaluates constraints, and renders the viewport")
    Rel(button, created, "Triggers on click")
    Rel(created, input_changed, "Registers handler")
    Rel(created, mouse_move, "Registers handler")
    Rel(created, mouse_click, "Registers handler")
    Rel(input_changed, affine, "Calibrates viewport offset")
    Rel(mouse_move, affine, "Calls each frame")
    Rel(mouse_move, preview, "Passes radius and hit point")
    Rel(mouse_click, geometry, "Calls once on commit click")
    Rel(mouse_click, commit, "Fires custom event")
    Rel(commit, fusion, "Calls doExecute(True) to close command")
    Rel(geometry, fusion, "Writes sketch curves and constraints")
```

### Coordinate space note

Fusion's `MouseEventArgs.position` reports cursor coordinates in **application-window space**, while `Viewport.modelToViewSpace()` returns coordinates in **viewport-local space**. The two share the same pixel scale but differ by a constant offset equal to the viewport's top-left corner within the application window.

The command calibrates this offset once at the moment the center point is selected (when both the click position and the projected center screen position are known simultaneously), then applies the correction on every `mouseMove` event so that the affine screen-space inversion produces accurate sketch-plane coordinates.
