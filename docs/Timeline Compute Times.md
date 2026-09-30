# Timeline Compute Report

[Back to README](../README.md)

## Overview

Timeline Compute Report opens an HTML report of the compute time of every feature in the active design's timeline, and saves the source data as a CSV file.

SolidWorks users know this as **Performance Evaluation**: the table of features ranked by rebuild time that tells you which fillet is costing you ten seconds on every change. Fusion measures the same thing but shows it nowhere. This command asks Fusion for the figures and lays them out with a percentage bar per feature and the total at the top.

## Prerequisites

- A parametric design must be open. In Direct Design mode the command reports that there is no timeline.

## Where to find it

**Solid** tab › **Inspect** panel › **Timeline Compute Report**, in the Design workspace.

## How to use

1. Let the model finish computing.
2. Select **Timeline Compute Report**. The report opens in Fusion's built-in browser.
3. Look for features with a large **Percent** bar; those are the candidates for simplification.

## Reading the report

The header shows the document name and the total timeline compute time as `h:mm:ss.ms`.

| Column | Meaning |
|---|---|
| **Component** | The component that owns the feature |
| **Feature** | The feature's name |
| **Time (seconds)** | The feature's own compute time |
| **Percent** | Its share of the total, as a whole number with a bar |
| **Health** | The feature's health state as Fusion reports it, colored for warnings and errors |

Rows are listed by compute time as Fusion reports them.

## What it produces

Two files in your system's temporary folder, each with a random name: the `.csv` Fusion's data was written to and the `.html` report. Neither is deleted.

## Limitations

- Times reflect the last full timeline compute. Let Fusion finish regenerating before running the report.
- The report is a snapshot; it does not update when the model changes.

> **Developers:** see the [architecture notes](./arch/Timeline%20Compute%20Times.md).

---

[Back to README](../README.md)

*Copyright © 2026 IMA LLC. All rights reserved.*
