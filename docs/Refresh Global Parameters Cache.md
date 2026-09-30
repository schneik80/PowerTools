# Refresh Global Parameters Cache

[Back to README](../README.md)

## Overview

Refresh Global Parameters Cache rescans the active project's `_Global Parameters` folder and rewrites the local cache that Global Parameters and Link Global Parameters use to find it.

The two parameter commands remember where the `_Global Parameters` folder is so they do not have to search the project every time. If that folder is deleted and recreated, moved, or its documents are renamed outside the add-in, the remembered location goes stale. This command finds the folder again, records it, and reports how many parameter sets it holds.

## Prerequisites

- A project must be active in the Data Panel.
- A document must be open.

## Where to find it

**Utilities** tab › **Power Tools** panel › **Refresh Global Parameters Cache**, in the Design workspace.

## How to use

1. Open any document with the target project active in the Data Panel.
2. Select **Refresh Global Parameters Cache**. There is no dialog; the scan runs immediately.
3. A message reports how many parameter sets were found. If the project has no `_Global Parameters` folder, the message says so and nothing is written.

## What it produces

Two files in the add-in's `cache` folder, `gp_folder_<project>.json` and `gp_docs_<project>.json`, holding the folder's identity and the list of set documents.

## Preferences

Shares one checkbox with Global Parameters under **File › PowerTools Preferences › Assembly**. Changes apply after a Fusion restart.

> **Developers:** see the [architecture notes](./arch/Refresh%20Global%20Parameters%20Cache.md).

---

[Back to README](../README.md)

*Copyright © 2026 IMA LLC. All rights reserved.*
