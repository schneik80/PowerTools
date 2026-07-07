# Create Related Data — Architecture

[← Create Related Data guide](../Related%20Data.md)

## Architecture

### How the command works

When you run **Create Related Data**, the add-in follows this sequence:

1. Reloads the in-memory hub configuration from `hub.json` to pick up any recently added hubs.
2. Checks whether the active hub ID is in the configured hub list. If it is not, an error message is displayed.
3. Calls `_load_templates_for_hub()`, which checks for a local cache file at `cache/[hub-id].json`. On a cache hit, templates are loaded from disk. On a cache miss, templates are fetched from the Fusion API, then written to the cache for future use.
4. Verifies that the source document is saved.
5. Presents the command dialog with a **Type** drop-down listing all available templates and an **Auto-Name** toggle.
6. When the user selects a template, the document name field updates automatically to `<source name> ‹+› <template name>`.
7. On confirmation (OK):
   - Opens the selected template document from the hub.
   - Saves it as a new document with the specified name, into the same folder as the source document.
   - Inserts the source document into the new document's root component as an external reference (X-Ref).
   - Saves the new document.

### System context

```mermaid
C4Context
  title System Context — Create Related Data

  Person(user, "Fusion User", "Has a saved source document open in Fusion")

  System_Boundary(addin, "PowerTools Add-in") {
    System(relatedData, "Create Related Data Command", "Copies a template, inserts the source document as an external reference, and saves the new document")
  }

  SystemDb(hubJson, "hub.json", "Local configuration file — registered hub, project, and folder IDs")
  SystemDb(cache, "Template Cache", "cache/[hub-id].json — cached list of available templates per hub")
  System_Ext(fusionTeam, "Autodesk Fusion Team", "Hosts hub data, template .f3d files, and the destination folder for new documents")

  Rel(user, relatedData, "Selects template, optionally sets name, clicks OK")
  Rel(relatedData, hubJson, "Reads hub and folder configuration")
  Rel(relatedData, cache, "Reads template list; writes cache on first fetch")
  Rel(relatedData, fusionTeam, "Fetches templates (cache miss); opens template document; saves new document")
```

### Container detail

```mermaid
C4Container
  title Container Diagram — Create Related Data

  Person(user, "Fusion User")

  Container_Boundary(addin, "PowerTools Add-in") {
    Container(cmdCreated, "command_created handler", "Python / Fusion API", "Validates the active hub; loads templates via _load_templates_for_hub(); builds the Type drop-down and Auto-Name toggle")
    Container(cmdInputChanged, "command_input_changed handler", "Python", "Updates the document name field when the user changes the Type or toggles Auto-Name")
    Container(cmdExecute, "command_execute handler", "Python / Fusion API", "Opens the selected template; saves as new document with X-Ref to source; saves the new document")
    Container(loadTemplates, "_load_templates_for_hub()", "Python / json", "Returns templates from cache or fetches from Fusion API and writes cache on miss")
    Container(configModule, "config.py", "Python", "In-memory COMPANY_HUB list and COMPANY_HUB_CONFIGS map loaded from hub.json")
  }

  SystemDb(hubJson, "hub.json", "Local JSON configuration file")
  SystemDb(cache, "cache/[hub-id].json", "Local template cache file per hub")
  System_Ext(fusionApi, "Fusion API (adsk.core / adsk.fusion)", "Provides documents.open(), document.saveAs(), occurrences.addByInsert(), dataProjects, dataFolders")

  Rel(user, cmdCreated, "Clicks Create Related Data")
  Rel(cmdCreated, configModule, "Calls reload_hub_config(); checks COMPANY_HUB")
  Rel(cmdCreated, loadTemplates, "Calls _load_templates_for_hub(hub_id)")
  Rel(loadTemplates, cache, "Reads cache on hit; writes cache on miss")
  Rel(loadTemplates, fusionApi, "Fetches folder contents on cache miss")
  Rel(cmdCreated, cmdInputChanged, "Fires on Type or Auto-Name change")
  Rel(cmdCreated, cmdExecute, "Fires on OK")
  Rel(cmdExecute, fusionApi, "Opens template; saves new document; inserts X-Ref")
  Rel(configModule, hubJson, "Reads hub entries on load or reload")
```
