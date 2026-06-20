# Timeline Compute Report — Architecture

[← Timeline Compute Report guide](../Timeline%20Compute%20Times.md)

## Architecture

### System context

The following diagram shows the relationship between the user, the Timeline Compute Report command, Autodesk Fusion, and the file system.

```mermaid
C4Context
    title System Context — Timeline Compute Report
    Person(user, "Fusion User", "Part designer analyzing model performance")
    System(addin, "Timeline Compute Report", "Power Tools Add-in command that generates a feature compute time report")
    System_Ext(fusion, "Autodesk Fusion", "CAD platform and host application")
    System_Ext(filesystem, "File System", "System temporary directory that stores CSV and HTML output files")
    Rel(user, addin, "Invokes from Solid > Inspect panel")
    Rel(addin, fusion, "Queries feature compute data via text commands API")
    Rel(addin, filesystem, "Writes CSV and HTML report files")
    Rel(fusion, user, "Opens HTML report in built-in browser")
```

### Component diagram

The following diagram shows how the internal components of the command interact during execution.

```mermaid
C4Component
    title Component Diagram — Timeline Compute Report
    Container_Boundary(addin, "Timeline Compute Report Command") {
        Component(button, "Command Button", "Fusion UI Control", "Toolbar button in Solid > Inspect panel")
        Component(handler, "command_execute()", "Python", "Validates design type and orchestrates the full report generation pipeline")
        Component(csvgen, "_create_temp_csv_file()", "Python", "Writes raw Fusion feature compute data to a temp CSV file")
        Component(calc, "_calculate_total_compute_time()", "Python", "Reads CSV and sums all feature compute times")
        Component(htmlgen, "_generate_html_report()", "Python", "Builds a formatted HTML report with a sortable table and SVG percentage bars")
        Component(browser, "QTWebBrowser.Display", "Fusion Text Command", "Opens the generated HTML file in the Fusion built-in browser")
    }
    System_Ext(fusion, "Autodesk Fusion", "Provides DumpFeaturesByComputeTime /csv text command")
    System_Ext(filesystem, "File System (Temp)", "Stores the output CSV and HTML files")
    Rel(button, handler, "Triggers on click")
    Rel(handler, fusion, "Calls DumpFeaturesByComputeTime /csv")
    Rel(handler, csvgen, "Passes raw CSV string")
    Rel(csvgen, filesystem, "Writes .csv file")
    Rel(handler, calc, "Reads CSV to calculate total time")
    Rel(handler, htmlgen, "Passes CSV path and total time")
    Rel(htmlgen, filesystem, "Writes .html file")
    Rel(handler, browser, "Passes HTML file path to open")
```
