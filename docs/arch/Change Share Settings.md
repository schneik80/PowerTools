# Change Share Settings — Architecture

[← Change Share Settings guide](../Change%20Share%20Settings.md)

## Architecture — command flow

The following diagram shows what the add-in does when you select **Change Share Settings**.

```mermaid
C4Context
    title Change Share Settings — System Interactions

    Person(designer, "Designer", "Autodesk Fusion user selecting the command")
    System(addin, "Share Menu Add-in", "Validates preconditions and delegates to native Fusion dialog")
    System_Ext(fusionDialog, "Fusion Share Settings Dialog", "Native Fusion UI: SimpleSharingPublicLinkCommand")
    System_Ext(aps, "Autodesk Platform Services", "Persists updated sharing configuration")

    Rel(designer, addin, "Selects Change Share Settings")
    Rel(addin, fusionDialog, "Calls SimpleSharingPublicLinkCommand.execute()")
    Rel(designer, fusionDialog, "Adjusts share settings in dialog")
    Rel(fusionDialog, aps, "Saves updated sharing preferences")
```

### Detailed command flow

```mermaid
flowchart TD
    A([User selects Change Share Settings]) --> B{Document saved?\napp.activeDocument.isSaved}
    B -- No --> C[Show save-required dialog\nCommand exits]
    B -- Yes --> D{Hub sharing enabled?\nSimpleSharingPublicLinkCommand.isEnabled}
    D -- No --> E[Show sharing-disabled message\nCommand exits]
    D -- Yes --> F[Execute SimpleSharingPublicLinkCommand\nNative Fusion share settings dialog opens]
    F --> G([User modifies sharing settings\nand confirms or cancels])
```

---

## Key API surface

| API element | Purpose |
|---|---|
| `ui.commandDefinitions.itemById("SimpleSharingPublicLinkCommand")` | Retrieves the native Fusion share command and checks whether sharing is enabled |
| `controlDefinition.isEnabled` | Reflects the Hub administrator's sharing policy |
| `futil.isSaved()` | Guards against operating on unsaved documents (checks `app.activeDocument.isSaved`; shows a "Please Save" prompt if not) |
| `commandDefinitions.itemById("SimpleSharingPublicLinkCommand").execute()` | Opens the native Fusion share settings dialog |
