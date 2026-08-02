# Assign Designators

[Back to PowerTools](../README.md)

The Assign Designators command gives every connector in the assembly a unique **reference designator** — the J1/J2/P1-style IDs that harness documentation uses to identify connectors. Designators name the connectors in the [Export Connectivity](./Export%20Connectivity.md) / [Import Connectivity](./Import%20Connectivity.md) wire list and label them in the [Wire Report](./Wire%20Report.md).

> **Prove-out status:** this is a beta test command in the Cable prove-out family. Its behavior may change.

## What it does

- Lists every **connector occurrence** in the design (any occurrence whose component carries [Define Wires](./Define%20Wires.md) data).
- Seeds unassigned connectors with **J1, J2, …** suggestions in assembly order; every value is free text and editable.
- Enforces **uniqueness** (case-insensitive) — OK stays disabled while two connectors share a designator.
- Designators are stored **per occurrence**: two instances of the same connector part get their own designators (J1 and J2), and the assignment belongs to this assembly document.
- Re-running the command recalls the stored values; **blank a value** to clear that connector's designator.

## Prerequisites

- **Beta mode** enabled in PowerTools Preferences.
- An active Fusion 3D design containing at least one connector (a component with Define Wires data).

## How to use Assign Designators

1. Open the assembly containing the connectors.
2. On the **Utilities** tab, open the **Power Tools** panel and click **Assign Designators**.
3. Review the table — each row shows the connector occurrence and its designator (stored value, or a suggested `J<n>`).
4. Edit as needed and click **OK**.

## Access

**Assign Designators** is on the **Design** workspace **Utilities** tab, in the **Power Tools** panel (with beta mode enabled).

> **Developers:** see the [architecture notes](./arch/Assign%20Designators.md).

---

[Back to PowerTools](../README.md)

---

*Copyright © 2026 IMA LLC. All rights reserved.*
