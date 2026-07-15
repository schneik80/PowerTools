# Show In Location — Architecture

[← Show In Location guide](../Show%20In%20Location.md)

## Architecture

The Show In Location automation registers application-level event handlers on startup for `documentOpened` and `documentActivated`. Each event passes the event document to a shared helper that resolves the document URN and executes `Dashboard.ShowInLocation <urn>` through `app.executeTextCommand`.

### Command IDs

- Toggle button: `PT_showinlocation_toggle` (in the **PowerTools Settings** dropdown in the QAT File menu)

### Execution flow

1. The add-in starts and registers handlers for `app.documentOpened` and `app.documentActivated`.
2. The add-in installs a **Disable / Enable Show In Location** toggle button into the **PowerTools Settings** sub-menu in the QAT File dropdown.
3. The user opens a document or activates a different document tab.
4. The handler checks the persisted enabled state; if disabled, it exits immediately.
5. The handler validates that the event includes a document and a cloud `dataFile`.
6. The helper reads `doc.dataFile.id` and executes `Dashboard.ShowInLocation <urn>`.
7. The Data Panel selection updates to the current document location.

To toggle the automation, the user selects the toggle button in **PowerTools Settings**. The handler flips the state, saves it to `cache/settings.json`, and updates the button label.

### Component diagram

```mermaid
C4Component
    title Show In Location – Component Architecture

    Person(user, "Designer", "Fusion user switching documents")
    Component(addin, "PowerTools Add-In", "Python, Fusion API", "Registers and hosts automation handlers")
    Component(events, "documentOpened/documentActivated", "Fusion Application Events", "Signals document open and tab activation")
    Component(cmd, "Show In Location Automation", "docopen/entry.py", "Resolves document URN and executes text command; manages toggle state")
    Component(toggleBtn, "PT_showinlocation_toggle", "QAT → File → PowerTools Settings", "Enable/Disable toggle that flips the persisted state")
    Component(settings, "cache/settings.json", "Local JSON", "Persists the enabled/disabled state between sessions")
    Component(fusion, "Dashboard.ShowInLocation", "Fusion Internal Command", "Navigates Data Panel to document location")

    Rel(user, addin, "Loads add-in on Fusion start")
    Rel(user, events, "Opens or switches documents")
    Rel(addin, events, "Subscribes to application document events")
    Rel(events, cmd, "Passes event document")
    Rel(cmd, settings, "Reads enabled state before executing")
    Rel(cmd, fusion, "Executes Dashboard.ShowInLocation <urn> when enabled")
    Rel(user, toggleBtn, "Clicks to enable or disable automation")
    Rel(toggleBtn, settings, "Writes new enabled state")
```
