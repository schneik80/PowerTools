# Hide Objects — Architecture

[← Hide Objects guide](../HideObjects.md)

## Architecture

### System context

The following diagram shows the relationship between the user, the Hide Objects command, and Autodesk Fusion.

```mermaid
C4Context
    title System Context — Hide Objects
    Person(user, "Fusion User", "Part designer working in Autodesk Fusion")
    System(addin, "Hide Objects", "Power Tools Add-in command that hides selected object categories across all components")
    System_Ext(fusion, "Autodesk Fusion", "CAD platform and host application")
    Rel(user, addin, "Invokes from Tools > Utility panel")
    Rel(addin, fusion, "Sets isLightBulbOn / folder visibility flags via Fusion API")
    Rel(fusion, user, "Updates viewport and browser to reflect hidden objects")
```

### Component diagram

The following diagram shows how the internal components of the command interact during execution.

```mermaid
C4Component
    title Component Diagram — Hide Objects
    Container_Boundary(addin, "Hide Objects Command") {
        Component(button, "Command Button", "Fusion UI Control", "Toolbar button in Tools > Utility panel")
        Component(dialog, "Command Dialog", "Fusion UI", "Eight checkboxes for object categories, all enabled by default")
        Component(handler, "command_execute()", "Python", "Iterates design.allComponents and applies visibility flags per selected category")
        Component(api, "Fusion Visibility API", "adsk.fusion", "isOriginFolderLightBulbOn, isLightBulbOn, isJointsFolderLightBulbOn, isSketchFolderLightBulbOn, isCanvasFolderLightBulbOn")
    }
    System_Ext(fusion, "Autodesk Fusion Design Engine", "Applies visibility changes to all components in the active design")
    Rel(button, dialog, "Opens")
    Rel(dialog, handler, "Passes checkbox values on OK")
    Rel(handler, api, "Sets visibility flags per component")
    Rel(api, fusion, "Updates model state")
```
