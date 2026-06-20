# Power Tools — Architecture Documentation

This folder contains developer-oriented architecture documentation for the
consolidated **Power Tools** add-in for Autodesk Fusion — the single add-in
formed by merging the Assembly, Document Tools, Exports, Part Modeling, Related
Data, and Share Document add-ins into one installable unit.

---

## Documents

| Document | Description |
|---|---|
| [Architecture](architecture.md) | System context, component diagram, add-in lifecycle, the shared-access-point model, command registration and execution, the `lib/ptAddInUtils` shared library, and the merged `config.py`. |

---

## Section index

- [System context](architecture.md#system-context) — users and external systems (Fusion, APS / Fusion Team, browser, file system).
- [Component structure](architecture.md#component-structure) — entry point, command registry, bootstrap, command modules, and shared library.
- [Add-in lifecycle](architecture.md#add-in-lifecycle) — `run`/`stop` → bootstrap → command start/stop.
- [Shared UI access points](architecture.md#shared-ui-access-points) — the Power Tools panel and PTSettings flyout, and why the old detect-or-create logic was removed.
- [Command registration](architecture.md#command-registration) and [execution model](architecture.md#command-execution-model).
- [`lib/ptAddInUtils`](architecture.md#shared-utility-library--libptaddinutils) — the shared utility library.
- [`config.py`](architecture.md#configuration-module--configpy) — the merged configuration module.
- [Architecture diagrams](architecture.md#architecture-diagrams) — reference renders in `assets/`.

---

## Related documentation

- For **end-user and command documentation**, see the [`docs/`](../docs) folder.
- For **installation and getting started**, see the project [README](../README.md).

---

*Copyright © 2026 IMA LLC. All rights reserved.*
