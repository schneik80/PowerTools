# Insert STEP File

[Back to README](../README.md)

## Overview

Insert STEP File browses your computer for a STEP file and inserts it as a component in the active design.

SolidWorks and Inventor insert a STEP file into an assembly straight from disk. In Fusion the file has to be uploaded to a project first, opened or converted, and then inserted from the Data Panel. Insert STEP File does it in one step: pick the file, and it arrives as a local component in the design you are working in. That is what an ECAD workflow needs when a mechanical model has to go into a PCB package design, and what any assembly needs when a vendor sends a STEP.

## Prerequisites

- A design document must be active.
- The STEP file must be on your local file system.

## Where to find it

Both of these, in the Design workspace:

- **Assembly** tab › **Insert** panel › **Insert STEP File**
- **Solid** tab › **Insert** panel › **Insert STEP File**

## How to use

1. Select **Insert STEP File**.
2. Choose a `.stp` or `.step` file in the file dialog and select **Open**. The filter shows STEP files; *All files* is also offered.
3. Fusion imports the file as a local component of the active design.

> **Note:** The component is local to the parent document. To make it its own cloud document that can be versioned and shared separately, run [Externalize](./Externalize.md) on it afterwards.

## Limitations

- Placement is Fusion's import behavior; the component arrives at the origin of the design.
- The command needs an active design; otherwise it reports *Insert STEP File needs a design open. Open or create a design, then retry.*

> **Developers:** see the [architecture notes](./arch/Insert%20Step.md).

---

[Back to README](../README.md)

*Copyright © 2026 IMA LLC. All rights reserved.*
