# Codebase map

A "search less" index for people and agents: where each thing lives, which
file to open for a given task, and what is known to be stale. Narrative and
the shared-module reference live in
[`architecture.md`](../arch/architecture.md); rules in
[`lessons.md`](lessons.md) and [`AGENTS.md`](../../AGENTS.md).

Regenerate the command table with the snippet at the bottom whenever the
registry changes.

---

## Contents

- [Entry points and core files](#entry-points-and-core-files)
- [Command table](#command-table)
- [Non-registry folders under `commands/`](#non-registry-folders-under-commands)
- [Shared helpers](#shared-helpers)
- [UI access points](#ui-access-points)
- [State on disk](#state-on-disk)
- ["Where is the example of..."](#where-is-the-example-of)
- [Developer tooling](#developer-tooling)
- [Stale, dead, or known-missing](#stale-dead-or-known-missing)
- [Regenerating the command table](#regenerating-the-command-table)

---

## Entry points and core files

| File | Role | Open it when |
|---|---|---|
| `PowerTools.py` | Fusion entry: `run()` -> `_maybe_start_debug_server()` -> `commands.start()`; `stop()` -> `ptutil.clear_handlers()` -> `commands.stop()` | Startup/shutdown, debugpy |
| `PowerTools.manifest` | Add-in manifest; version/`editEnabled` are stamped at release time, never edited here | Release questions |
| `config.py` | Sections 1-8: flags (`DEBUG` = `.debug` marker, `PERF_TRACE`, debugger), shared panel ids, Drawing/Manage/Animation/Manufacture ids and probes, the dead PTSettings helpers, legacy `cache/settings.json`, hub config (`cache/hub.json`), `fusion_addins_dir()`, palette ids, `settings/` paths + `DOCS_BASE_URL` | Any id, path, or flag — [reference](../arch/architecture.md#config) |
| `command_registry.py` | `GROUPS` -> `_cmd(module, doc, beta, settings)`; `iter_commands()`; no `adsk` import | Adding/renaming a command — [reference](../arch/architecture.md#command_registry) |
| `settings_store.py` | `settings/preferences.json`: `_defaults()` from the registry, `DEFAULT_DISABLED_COMMANDS`, `COMMAND_SETS`/`SET_LEAD`, `COMMAND_SETTING_DEFAULTS`, `RENAMED_COMMANDS`, `load()` (memoised, deep-merge, read-only-install safe), `save()`, `validate()`, `import_from_file()` | Settings, defaults, renames, sets — [reference](../arch/architecture.md#settings_store) |
| `commands/__init__.py` | `load_command(key)` lazy import; `start()` gates by group/command/beta/set lead; `_started` teardown newest-first; `preferences` always starts first | Start order, gating — [reference](../arch/architecture.md#commands__init__) |
| `commands/_ui_bootstrap.py` | Creates/removes the shared Power Tools panel once; `get_power_tools_panel()` | Shared panel — [reference](../arch/architecture.md#_ui_bootstrap) |
| `commands/_command_abort.py` | `abort_before_dialog()`, `consume_abort()`, `clear_abort()`, `was_aborted()` — the only sanctioned way to end a command from `commandCreated` (never `doExecute`) | Precondition failures before a dialog — [reference](../arch/architecture.md#_command_abort) |
| `commands/_menu_plan.py` | `MenuSlots(prefix, limit, empty_id).plan_menu(count) -> (keep, remove)`, `all_ids()`, `item_text()`, `menu_signature()` — adsk-free positional keep/remove rule for flyouts that list a changing set (never delete-then-add a per-item definition) | A dynamic flyout rebuild — [reference](../arch/architecture.md#_menu_plan) |
| `commands/_inspect_panels.py` | `design_inspect_panels()`, `add_to_inspect_panels()`, `remove_from_inspect_panels()` — runtime discovery of Fusion's Inspect panels | Placing a control on Inspect — [reference](../arch/architecture.md#_inspect_panels) |
| `commands/_drawing_panel.py` | `add_to_drawing_panel()`, `remove_from_drawing_panel()` — the Drawing workspace's shared Power Tools panel, created on first use and deleted when empty | Placing a control in a drawing — [reference](../arch/architecture.md#_drawing_panel) |
| `lib/ptAddInUtils/` | Shared helpers, imported as `ptutil` | Reuse before writing — [reference](../arch/architecture.md#libptaddinutils-ptutil) |
| `tests/conftest.py` | `PowerTools` synthetic package + `adsk` MagicMock finder | Writing tests — [Testing](index.md#testing) |

---

## Command table

Module = folder under `commands/` = settings key. The doc filename is used
verbatim for both `docs/<Doc>` and `docs/arch/<Doc>` (the per-command
architecture notes; every registered command has one, asserted by
`tests/test_command_contract.py`). "adsk-free" modules are the unit-testable
cores ([the pure-logic split](../arch/architecture.md#the-pure-logic-split)).
Registry-wide tests (`test_command_contract.py`, `test_command_abort.py`,
`test_command_icons.py`, `test_release_build.py`, `test_settings_command_sets.py`)
are not repeated per row.

| Group | Module | Doc filename | adsk-free modules | Tests | Notes |
|---|---|---|---|---|---|
| assembly | `assemblybuilder` | `Assembly Builder.md` | `sysml_import.py` | `test_assemblybuilder_sysml_import.py` | palette; imports a SysML v2 physical view (inverse of `exportsysml`) |
| assembly | `insertSTEP` | `Insert Step.md` | — | — | Assembly INSERT panel; must start before `assemblypalette` |
| assembly | `assemblypalette` | `Assembly Palette.md` | — | `test_assemblypalette_{builder_gate,edit_initial_position,fasteners,open_docs,thumbnails}.py` | palette; launch button `PTAT_assemblyPalette`; Timer -> custom event twice; renamed from `assemblyintent` (`RENAMED_COMMANDS`) |
| assembly | `assemblystats` | `Assembly Statistics.md` | — | — | |
| assembly | `getandupdate` | `Get and Update.md` | — | — | ships disabled |
| assembly | `bottomupupdate` | `Bottom-Up Update.md` (+ `Bottom-Up Update Dependency Ordering.md`) | `document_dag.py` | `test_bottomupupdate_*.py` (9 files) | pumped waits, handle re-acquisition, autosave suspend |
| assembly | `componentwarn` | `Component Warning.md` | — | — | settings; ships disabled |
| assembly | `changecyclecolor` | `Change Cycle Color.md` | `colors.py`, `swatches.py`, `fusion_install.py`, `_color_picker_subprocess.py` | `test_changecyclecolor_{abort,colors,fusion_install}.py` | settings; marking-menu only; module-local abort flag (not `_command_abort`); one deliberate `doExecute` |
| assembly | `externalize` | `Externalize.md` | — | `test_externalize_upload.py` | custom-event runner fired from `execute`; selection capture; bounded upload spin |
| assembly | `globalParameters` | `Global Parameters.md` | — | — | lead of the `COMMAND_SETS` set with the two below (one checkbox) |
| assembly | `inferconstraints` | `Infer Constraints.md` | — | — | beta |
| assembly | `linkGlobalParameters` | `Link Global Parameters.md` | — | — | set member |
| assembly | `refreshGlobalParametersCache` | `Refresh Global Parameters Cache.md` | — | — | set member |
| assembly | `refrences` | `Document References.md` | — | — | folder name is misspelled on purpose (stable key); one deliberate `doExecute`; one recorded `time.sleep` |
| assembly | `refresh` | `Document Refresh.md` | `logic.py` | `test_refresh_logic.py` | QAT File; closes from `commandCreated` |
| document | `assigndrawingnumber` | `Assign Drawing Number.md` | — | — | Drawing-tab panel; `partnumber_shared`; abort pattern |
| document | `assignpartnumbers` | `Assign Part Numbers.md` | — | — | `partnumber_shared`; abort pattern |
| document | `syncitempartnumber` | `Sync Item to Part Number.md` | `logic.py` | `test_syncitempartnumber_logic.py` | Manage-tab panel; MFGDM |
| document | `autosave` | `Recovery Save.md` | — | — | |
| document | `closealldocuments` | `Close All Documents.md` | `logic.py` | `test_closealldocuments_logic.py` | QAT File; work in `commandCreated` |
| document | `datatoggle` | `Toggle Data Pane.md` | — | — | `NavToolbar` button; work in `commandCreated` |
| document | `defaultfolders` | `Default Folders.md` | — | — | settings (`DEFAULT_FOLDER_SETS`) |
| document | `dochistory` | `Document History.md` | `history_model.py`, `mfgdm_history.py` | `test_dochistory_{doc_switch,history_model}.py` | QAT button; HTML palette; custom events `PTND_history_*` |
| document | `docinfo` | `Document Information.md` | `mfgdm_status.py` | `test_docinfo_mfgdm_status.py` | Design and Drawing Power Tools panels; MFGDM `model` / `item` queries |
| document | `docopen` | `Show In Location.md` | — | — | settings; no control (document events); ships disabled |
| document | `favorites` | `Favorites.md` | shares `../_menu_plan.py` | `test_favorites_menu.py` | QAT top-level dropdown; `cache/favorites_<hub>.json`; positional, reused item definitions; three `commandCreated` handlers |
| document | `matchunits` | `Match Units.md` | `logic.py`, `mfg.py` | `test_matchunits_{logic,mfg_logic}.py` | settings (2 prompts); Inspect panels; two independent Timer -> custom event deferrals; `resourceFolder` swap |
| document | `openrecent` | `Open Recent.md` | shares `../_menu_plan.py` | `test_openrecent_menu.py` | QAT File flyout, probed placement; positional, reused item definitions; items open from `commandCreated` |
| document | `versiondiff` | `Version Diff.md` | `timeline_model.py`, `feature_icons.py`, `html_report.py` | — | ships disabled; abort pattern |
| exports | `exportbomcsv` | `Export BOM.md` | — | `test_csv_injection.py` | |
| exports | `exportmermaid` | `Export Mermaid.md` | — | — | |
| exports | `exportsysml` | `Export SysML.md` | `model.py`, `render.py` | `test_exportsysml_{model,render,entry}.py` | QAT File (before `ExportCommand`); work in `commandCreated`; keys on `Component.id` + name |
| partmodeling | `roundsketchdimensions` | `Round Sketch Dimensions.md` | `rounding.py` | `test_roundsketchdimensions_rounding.py` | `executePreview` apply; abort pattern |
| partmodeling | `sketchunderconstrained` | `SketchUnder.md` | — | — | |
| partmodeling | `sketchcirclecenterpoint` | `RadialHoleCircle.md` | — | — | beta; ships disabled (graphics); one deliberate `doExecute` via custom event; abort pattern |
| partmodeling | `timelinecompute` | `Timeline Compute Times.md` | — | — | |
| partmodeling | `measurepath` | `Measure Path.md` | `pathgraph.py` | `test_measurepath_pathgraph.py` | Inspect panels; custom graphics reference impl; abort pattern |
| partmodeling | `mirrorderive` | `MirrorDerive.md` | — | — | |
| partmodeling | `hideobjects` | `HideObjects.md` | — | — | |
| partmodeling | `flattensurface` | `Flatten Surface.md` | `flatten.py`, `report.py`, `backdrop.py` | `test_flattensurface_{flatten,segments,cracks,report,backdrop,entry}.py` | beta; pure solver — [`Flatten Surface solver.md`](Flatten%20Surface%20solver.md) |
| animation | `animationnamedview` | `Animation Named View.md` | `logic.py` | `test_animationnamedview_logic.py` | Publisher workspace ids via `config` |
| related | `confighub` | `Select Related Data Folder.md` | — | — | f-string `CMD_ID` (allowlisted); writes `cache/hub.json`; launched from Preferences |
| related | `relateddata` | `Related Data.md` | — | `test_relateddata_cache.py` | f-string `CMD_ID` (allowlisted); `cache/<hub_id>.json` |
| teamaddins | `configteamaddins` | `Set Up Shared Add-ins Folder.md` | — | — | f-string `CMD_ID` (allowlisted); icon shared with `teamaddins` |
| teamaddins | `teamaddins` | `Team Add-ins.md` | `catalog.py` | `test_teamaddins_{catalog,installer,sync,team_fs}.py` | palette, settings; Timer -> custom event; one recorded `time.sleep` in `installer.py` |
| tools | `scriptsmanager` | `Scripts and Add-ins.md` | — | — | QAT File, before `PT_preferences`; work in `commandCreated` |
| share | `shareDocument` | `Get a Share Link.md` | — | — | creates the QATRight `shareDropMenu` flyout |
| share | `shareSettings` | `Change Share Settings.md` | — | — | |
| share | `OpenDesktop` | `Get Open on Desktop Link.md` | — | — | |
| share | `OpenInTeam` | `Get Open in Team Link.md` | — | — | |
| share | `projectInvite` | `Invite to Project.md` | — | — | |
| share | `projectMembers` | `Document Project Members.md` | — | — | |

Tests not tied to one command are listed in [Testing](index.md#testing).

---

## Non-registry folders under `commands/`

| Folder | What it is |
|---|---|
| `preferences/` | Infrastructure command, always started first by `commands/__init__.py`; the Preferences palette (`resources/html/app.js` holds `CMD_SECTIONS`, `groupExtras()`, `commandRow()`; command sets come from `settings_store.COMMAND_SETS`, not the page). `CMD_ID` `PT_preferences` is an anchor for `scriptsmanager` |
| `partnumber_shared/` | Shared library for the part/drawing-number commands: `hub_fs.py`, `pn_cache.py`, `intent.py`, `schemes.py`, `mfgdm_props.py` — [reference](../arch/architecture.md#partnumber_shared) |
| `assemblyintent/` | **Dead** — an empty, untracked directory left from the rename to `assemblypalette`; safe to delete locally |

---

## Shared helpers

The reference for every shared module — purpose, public names with one-line
semantics, the rule each exists to enforce, its tests and its callers — is
[Shared modules](../arch/architecture.md#shared-modules) in the architecture
document. Quick routing:

| Need | Use | Reference |
|---|---|---|
| Log, wait, clipboard, document precondition, error trace, perf line | `ptutil.log`, `pump_events_for`, `clipText`, `require_document`, `handle_error`, `perf_timer` | [`general_utils`](../arch/architecture.md#general_utils) |
| Connect any Fusion event | `ptutil.add_handler(event, cb, *, name, local_handlers)` | [`event_utils`](../arch/architecture.md#event_utils) |
| Read a `SelectionCommandInput` | `ptutil.capture_selections` in `inputChanged`, then `picked` / `picked_one` | [`selection_utils`](../arch/architecture.md#selection_utils) |
| Read/write JSON state | `ptutil.read_json`, `write_json_atomic` | [`json_utils`](../arch/architecture.md#json_utils) |
| QAT File dropdown, QATRight flyout, own panel teardown | `ptutil.get_qat_file_dropdown`, `remove_from_qat_file_dropdown`, `remove_from_qat_right_flyout`, `remove_from_panel` | [`ui_utils`](../arch/architecture.md#ui_utils) |
| Active project / target folder / re-activate a document; Global Parameters caches | `cache_utils.get_active_project`, `resolve_target_folder`, `target_project_label`, `safe_activate` | [`cache_utils`](../arch/architecture.md#cache_utils) |
| Wait for a save/upload | `ptutil.wait_for_upload` | [`upload_utils`](../arch/architecture.md#upload_utils) |
| Recent documents and thumbnails | `recents_utils.list_recent`, `remember_recent_if_eligible`, `store_thumbnail_object` | [`recents_utils`](../arch/architecture.md#recents_utils), [`fusion_recents`](../arch/architecture.md#fusion_recents) |
| Design-intent icons in a palette | `intent_icons.write_stylesheet` | [`intent_icons`](../arch/architecture.md#intent_icons) |
| Open a run log in a live viewer | `log_utils.default_log_directory`, `open_live_log_viewer` | [`log_utils`](../arch/architecture.md#log_utils) |
| Give up before the dialog | `_command_abort.abort_before_dialog` / `consume_abort` / `clear_abort` | [`_command_abort`](../arch/architecture.md#_command_abort) |
| Rebuild a flyout of changing entries | `_menu_plan.MenuSlots(...).plan_menu` / `all_ids`, then `_ensure_definition` / `_ensure_control` / `_remove_item` / `_clear_items` as in `openrecent` and `favorites` | [`_menu_plan`](../arch/architecture.md#_menu_plan) |
| Place a control on Inspect | `_inspect_panels.add_to_inspect_panels` / `remove_from_inspect_panels` | [`_inspect_panels`](../arch/architecture.md#_inspect_panels) |
| The shared panel | `_ui_bootstrap.get_power_tools_panel` | [`_ui_bootstrap`](../arch/architecture.md#_ui_bootstrap) |
| Part numbers, MFGDM properties | `partnumber_shared.{hub_fs,pn_cache,intent,schemes,mfgdm_props}` | [`partnumber_shared`](../arch/architecture.md#partnumber_shared) |

---

## UI access points

The authoritative table is
[UI access points](../arch/architecture.md#ui-access-points) in the
architecture document. One line each:

| Location | Example command |
|---|---|
| Power Tools panel (Design > Tools tab), created by `_ui_bootstrap` | `assemblystats` |
| QAT File dropdown (`FileSubMenuCommand`) | `preferences` (retry), `openrecent` (flyout), `scriptsmanager`, `closealldocuments`, `refresh`, `exportsysml` |
| QAT top-level dropdown | `favorites` |
| QATRight Share flyout (`shareDropMenu`) | `shareDocument` and the other Share commands |
| `NavToolbar` | `datatoggle` |
| Drawing tab panel `PT_DrawingPowerTools` (`_drawing_panel`) | `assigndrawingnumber`, `docinfo` |
| Manage tab panel `PT_ManagePowerTools` (needs the Manage Extension) | `syncitempartnumber` |
| Animation (Publisher) panel `PT_AnimationPowerTools` | `animationnamedview` |
| Inspect panels, discovered (`_inspect_panels`) | `measurepath`, `matchunits` |
| Marking (right-click) menu | `changecyclecolor` |
| Assembly INSERT panel | `insertSTEP`, `assemblypalette` launch button |
| Palettes (`config.*_palette_id`) | `assemblybuilder`, `assemblypalette`, `dochistory`, `preferences`, `teamaddins` |

Built-in tabs and panels are never deleted; only our controls and our own
panels are.

---

## State on disk

The full table with owners is
[State on disk](../arch/architecture.md#state-on-disk). The short form:

| Path | Owner | Git |
|---|---|---|
| `settings/preferences.json` | `settings_store` | ignored; regenerated from defaults; forbidden in the release |
| `cache/settings.json` | legacy; read once by `settings_store._migrate_legacy` | ignored |
| `cache/hub.json` | `confighub` writes, `config.loadHub` reads — root `hub.json` is a stale copy | ignored (root copy tracked, release-excluded) |
| `cache/<hub_id>.json` | `relateddata` template cache | ignored |
| `cache/recent_docs.json`, `cache/thumbs/` | `recents_utils` | ignored |
| `cache/favorites_<hub>.json` | `favorites` | ignored |
| `cache/gp_*.json` | `cache_utils` (Global Parameters) | ignored |
| `cache/team-addins-installed.json`, `cache/team-addins/` | `teamaddins` | ignored |
| `cache/powertools-debug.log` | `ptutil.log` when `.debug` is present (5 MB cap) | ignored |
| `commands/*/resources/html/init.js`, `intent-icons.css` | palettes (generated on open) | ignored by glob |
| `.debug` | developer marker: `DEBUG` + debugpy server on 5678 | ignored; forbidden in the release |
| `<options root>/<user>/<hub>_RecentsWithoutSearch_1.json` | Fusion (read-only for us) | n/a |

---

## "Where is the example of..."

| Pattern | Look at |
|---|---|
| No-input command acting from `commandCreated` | `commands/closealldocuments/entry.py`, `scriptsmanager`, `datatoggle`, `preferences`, `exportsysml` |
| Retrying a QAT control from `documentActivated` | `commands/preferences/entry.py::_ensure_control` / `_retry_placement` |
| Self-correcting flyout placement, candidate control ids | `commands/openrecent/entry.py` |
| Positional, reused per-item definitions in a dynamic flyout | `commands/_menu_plan.py`; `commands/openrecent/entry.py`, `commands/favorites/entry.py` (`_rebuild_menu`) |
| Ending a command from `commandCreated` when a precondition fails | `commands/_command_abort.py`; `versiondiff`, `roundsketchdimensions`, `assigndrawingnumber`, `assignpartnumbers`, `measurepath`, `sketchcirclecenterpoint`; `changecyclecolor` carries a local variant of the same flag |
| `threading.Timer` -> `fireCustomEvent` deferral | `commands/teamaddins/entry.py` (`_schedule_check` / `_fire_check`), `commands/assemblypalette/entry.py` (post-insert chain, thumbnail pump), `commands/dochistory/entry.py`, `commands/matchunits/entry.py` |
| Polling an `adsk.core.Future` without blocking | `commands/assemblypalette/entry.py` and `commands/dochistory/entry.py` thumbnails |
| Deferring heavy work to a `CustomEvent` fired from `execute` | `commands/externalize/entry.py` (`PTAT_externalize_runner`) |
| Escaping the mouse-event stack through a custom event | `commands/sketchcirclecenterpoint/entry.py::custom_event_commit` |
| Waiting on a save/upload | `ptutil.wait_for_upload`; `bottomupupdate`, `closealldocuments`, `externalize` (bounded fork `_save_to_cloud`) |
| Suspend autosave / re-acquire handles across pumped waits | `commands/bottomupupdate/entry.py` (`_suspend_autosave`, `close_processed_document`, `sweep_stray_documents`) |
| Selection capture | `commands/externalize/entry.py`, `commands/measurepath/entry.py`, `commands/flattensurface/entry.py` |
| State-dependent command icon (`resourceFolder` swap + dynamic tooltip) | `commands/matchunits/entry.py` |
| Enum-name-keyed tables resolved against the live `adsk` enums | `commands/matchunits/logic.py` |
| Reading/writing a product Fusion gives no API for, via `executeTextCommand` + a parsed diagnostic | `commands/matchunits/mfg.py` |
| Resolving a design from a non-Design workspace (`products.itemByProductType`) | `commands/animationnamedview/entry.py`, `commands/matchunits/entry.py` |
| Custom graphics in `executePreview`, billboarded text, cones | `commands/measurepath/entry.py` |
| `executePreview` apply with revert-on-cancel | `commands/roundsketchdimensions/entry.py` |
| Palette RPC (`init.js`, `incomingFromHTML`, `sendInfoToHTML`) | `commands/preferences/entry.py` + `resources/html/app.js`; `commands/assemblybuilder` |
| "No target project" banner / defensive active project | `commands/assemblypalette`, `commands/assemblybuilder`, `cache_utils.resolve_target_folder` |
| Marking-menu-only command with a live preference | `commands/changecyclecolor/entry.py` |
| Runtime workspace/tab discovery with pinned ids | `config.py` sections 3c/3d, `commands/animationnamedview/entry.py` |
| GraphQL to MFGDM | `commands/partnumber_shared/mfgdm_props.py`, `commands/dochistory/mfgdm_history.py` |
| Hub folder as a catalogue, revision fingerprinting, safe install | `commands/teamaddins/{catalog,installer,team_fs,sync}.py` |
| Pure-logic module + test pairing | `matchunits/logic.py` <-> `tests/test_matchunits_logic.py`; `measurepath/pathgraph.py` <-> `tests/test_measurepath_pathgraph.py`; `refresh/logic.py` <-> `tests/test_refresh_logic.py`; `flattensurface/flatten.py` <-> `tests/test_flattensurface_*.py` |
| Atomic JSON writes | `ptutil.write_json_atomic` (favorites, hub config, preferences, relateddata cache, teamaddins) |
| Reading Fusion's own recents | `lib/ptAddInUtils/fusion_recents.py` |
| Generated icons | `commands/<cmd>/resources/generate_icons.py` + `tools/icons/iconkit.py` |
| Registry-driven contract tests and AST guards | `tests/test_command_contract.py`, `tests/test_command_abort.py` |

---

## Developer tooling

| Task | Command |
|---|---|
| Bootstrap | `python3 -m venv .venv && .venv/bin/pip install "ruff==0.15.20" "pytest>=8.0"` |
| The four CI gates | `ruff format --check .` · `ruff check .` · `.venv/bin/python -m pytest -q` · `python3 tools/pandoc/build_readme_pdf.py --check` |
| Format | `ruff format .` |
| Release dry run | `python3 tools/release/build_release.py --version v0.0.0-test` -> `dist/` (`git add` new files first) |
| README PDF | `python3 tools/pandoc/build_readme_pdf.py` (pandoc + xelatex), `--check` (stamp vs. README, no toolchain), `--if-stale` (what the release build runs). Skill: `build-readme-pdf` |
| Icons | `python3 commands/<cmd>/resources/generate_icons.py`. Skill: `generate-icons` |
| Debug in Fusion | `touch .debug`, Run the add-in, attach on 5678 (Zed) or use the Debug button (VS Code, 9000) — [debugging.md](debugging.md) |
| Repoint the debug paths after a Fusion update | `python3 tools/debug/update_debug_path.py <channel>` (`--list`, `--dry-run`) — [debugging.md](debugging.md#pointing-the-config-at-a-build-update_debug_pathpy) |
| Blame without reformat noise | `git config blame.ignoreRevsFile .git-blame-ignore-revs` |

Fusion runs only on macOS and Windows; a Linux checkout can run every tool
above except Fusion. Per-device invocations:
[`.agent/environment.md`](../../.agent/environment.md).

---

## Stale, dead, or known-missing

- `commands/assemblyintent/` — an empty, untracked directory left from the
  rename to `assemblypalette`; never ships. `settings_store.RENAMED_COMMANDS`
  carries the migration and must stay.
- `config.get_or_create_pt_settings_dropdown()`,
  `config.remove_from_pt_settings_dropdown()`,
  `_ui_bootstrap.get_pt_settings_flyout()` and `config.PT_SETTINGS_DROPDOWN_*`
  — no callers; the bootstrap creates no PTSettings flyout.
- `config.save_settings()` — no caller; `config.load_settings()` is read once
  by `settings_store._migrate_legacy`.
- `ptutil.ui_utils.get_or_create_panel`, `get_or_create_qat_file_flyout`,
  `remove_from_qat_file_flyout`, `get_or_create_qat_right_flyout` — no
  callers.
- `lib/ptAddInUtils/attributes_utils.py` and `date_utils.py` — no caller in
  `commands/` (`date_utils` has a test; `attributes_utils` has none).
- `general_utils.debug_log_path()` — no caller outside the package.
- Three `CMD_ID`s (`confighub`, `relateddata`, `configteamaddins`) are
  f-strings containing a space; allowlisted in
  `tests/test_command_contract.py::KNOWN_NONLITERAL_CMD_IDS` because renaming
  orphans QAT pins.
- Three `time.sleep` sites remain under `commands/` and are recorded in
  `tests/test_command_contract.py::KNOWN_TIME_SLEEP_SITES`
  (`partnumber_shared/pn_cache.py` ×2, `refrences/entry.py`,
  `teamaddins/installer.py`).
- Gallery auto-refresh for the Assembly Palette is not implemented; the
  constraints for anyone attempting it are in the Learnings section of
  [`docs/arch/Assembly Palette.md`](../arch/Assembly%20Palette.md).
- `docs/arch/assets/000-CDD.png` … `005-CDD.png` are tracked static renders
  from the consolidation and are referenced by no document.
- `docs/dev/debugging.md` is written against `ADSKMVG91G2F5W` (the macOS dev
  box, `~/Library/...` paths); `g16win.local` differs. Device roster:
  `.agent/environment.md`.
- Root `hub.json` is a stale org copy kept tracked but release-excluded.

---

## Regenerating the command table

```python
# python3 - <<'EOF'  (from the repo root)
import importlib.util, os, glob, re
spec = importlib.util.spec_from_file_location("reg", "command_registry.py")
reg = importlib.util.module_from_spec(spec); spec.loader.exec_module(reg)
for g, c in reg.iter_commands():
    m, d = c["module"], c["doc"]
    folder = f"commands/{m}"
    pure = sorted(f for f in os.listdir(folder) if f.endswith(".py")
                  and f not in ("__init__.py", "entry.py")
                  and not re.search(r"^(from|import) adsk", open(os.path.join(folder, f)).read(), re.M))
    tests = sorted(os.path.basename(t) for t in glob.glob("tests/test_*.py")
                   if re.search(r"\b" + re.escape(m) + r"\b", open(t).read()))
    print(f"| {g['key']} | `{m}` | `{d}` | {', '.join(pure) or '—'} | {', '.join(tests) or '—'} | |")
# EOF
```

Check the `tests` column by hand: a module name that is also an English word
(`refresh`) matches unrelated files.

---

*Copyright © 2026 IMA LLC. All rights reserved.*
