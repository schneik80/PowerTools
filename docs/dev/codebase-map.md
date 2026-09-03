# Codebase map

A "search less" index for people and agents: where each thing lives, which
file to open for a given task, and what is known to be stale. Narrative lives
in [`architecture.md`](../arch/architecture.md); rules in
[`lessons.md`](lessons.md) and [`AGENTS.md`](../../AGENTS.md).

Regenerate the command table with the snippet at the bottom whenever the
registry changes.

---

## Contents

- [Entry points and core files](#entry-points-and-core-files)
- [Command table](#command-table)
- [Non-registry folders under `commands/`](#non-registry-folders-under-commands)
- [`lib/ptAddInUtils` index](#libptaddinutils-index)
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
| `config.py` | 8 sections: flags (`DEBUG` = `.debug` marker, `PERF_TRACE`, debugger), shared panel IDs, Drawing/Manage/Animation IDs, QAT File dropdown helpers, legacy `cache/settings.json`, hub config (`hub.json`), palette IDs, `settings/` paths + `DOCS_BASE_URL` | Any ID, path, or flag |
| `command_registry.py` | `GROUPS` -> `_cmd(module, doc, beta, settings)`; `iter_commands()`; no `adsk` import | Adding/renaming a command |
| `settings_store.py` | `settings/preferences.json`: `_defaults()` from registry, `DEFAULT_DISABLED_COMMANDS`, `COMMAND_SETS`/`SET_LEAD` (one checkbox per command set), `COMMAND_SETTING_DEFAULTS`, `RENAMED_COMMANDS`, `load()` (memoised, deep-merge), `save()`, `validate()`, `import_from_file()` | Settings, defaults, renames, sets |
| `commands/__init__.py` | `load_command(key)` lazy import; `start()` gates by group/command/beta; `_started` teardown newest-first; `preferences` always starts first | Start order, gating |
| `commands/_ui_bootstrap.py` | Creates/removes the shared Power Tools panel once; `get_power_tools_panel()` | Shared panel |
| `commands/_command_abort.py` | `abort_before_dialog()`, `consume_abort()`, `clear_abort()`, `was_aborted()` -- the only sanctioned way to end a command from `commandCreated` (never `doExecute`) | Precondition failures before a dialog |
| `lib/ptAddInUtils/` | Shared helpers, imported as `ptutil` (see index below) | Reuse before writing |
| `tests/conftest.py` | `PowerTools` synthetic package + `adsk` MagicMock finder | Writing tests |

---

## Command table

Module = folder under `commands/` = settings key. The doc filename is used
verbatim for both `docs/<Doc>` and `docs/arch/<Doc>`. "adsk-free" modules are
the unit-testable cores.

| Group | Module | Doc filename | Arch doc | adsk-free modules | Tests | Notes |
|---|---|---|---|---|---|---|
| assembly | `assemblybuilder` | `Assembly Builder.md` | ✓ | — | — | palette |
| assembly | `insertSTEP` | `Insert Step.md` | ✓ | — | — | must start before `assemblypalette` |
| assembly | `assemblypalette` | `Assembly Palette.md` | ✓ | — | `test_assemblypalette_edit_initial_position.py`, `test_assemblypalette_fasteners.py`, `test_assemblypalette_thumbnails.py` | palette; was `assemblyintent` |
| assembly | `assemblystats` | `Assembly Statistics.md` | ✓ | — | — | |
| assembly | `getandupdate` | `Get and Update.md` | ✓ | — | — | ships disabled |
| assembly | `bottomupupdate` | `Bottom-Up Update.md` (+ `Bottom-Up Update Dependency Ordering.md`) | ✓ | `document_dag.py` | `test_bottomupupdate_*.py` (8 files) | crash mitigations live here |
| assembly | `componentwarn` | `Component Warning.md` | ✓ | — | — | settings; ships disabled |
| assembly | `changecyclecolor` | `Change Cycle Color.md` | ✓ | `colors.py`, `swatches.py`, `fusion_install.py`, `_color_picker_subprocess.py` | `test_changecyclecolor_{colors,abort,fusion_install}.py` | settings; marking-menu only; reference abort pattern |
| assembly | `externalize` | `Externalize.md` | ✓ | — | — | CustomEvent deferral, selection capture |
| assembly | `globalParameters` | `Global Parameters.md` | ✓ | — | — | lead of a `COMMAND_SETS` set with the two below (one checkbox) |
| assembly | `inferconstraints` | `Infer Constraints.md` | ✓ | — | — | beta |
| assembly | `linkGlobalParameters` | `Link Global Parameters.md` | ✓ | — | — | |
| assembly | `refmanager` | `Reference Manager.md` | ✓ | — | — | ships disabled |
| assembly | `refreshGlobalParametersCache` | `Refresh Global Parameters Cache.md` | ✓ | — | — | |
| assembly | `refrences` | `Document References.md` | ✓ | — | — | folder name is misspelled on purpose (stable key) |
| assembly | `refresh` | `Document Refresh.md` | ✓ | `logic.py` | `test_refresh_logic.py` | |
| document | `assigndrawingnumber` | `Assign Drawing Number.md` | ✓ | — | — | Drawing-tab panel |
| document | `assignpartnumbers` | `Assign Part Numbers.md` | ✓ | — | — | uses `partnumber_shared/` |
| document | `syncitempartnumber` | `Sync Item to Part Number.md` | ✓ | `logic.py` | `test_syncitempartnumber_logic.py` | Manage-tab panel; MFGDM |
| document | `autosave` | `Recovery Save.md` | ✓ | — | — | |
| document | `closealldocuments` | `Close All Documents.md` | ✓ | `logic.py` | `test_closealldocuments_logic.py` | QAT File; work in `commandCreated` |
| document | `datatoggle` | `Toggle Data Pane.md` | ✓ | — | — | QAT File launcher |
| document | `defaultfolders` | `Default Folders.md` | ✓ | — | — | settings (`DEFAULT_FOLDER_SETS`) |
| document | `dochistory` | `Document History.md` | ✓ | — | — | |
| document | `docinfo` | `Document Information.md` | ✓ | — | — | |
| document | `docopen` | `Show In Location.md` | ✓ | — | — | settings; no button (document events); ships disabled |
| document | `favorites` | `Favorites.md` | ✓ | — | — | `cache/favorites_<hub>.json` |
| document | `openrecent` | `Open Recent.md` | ✓ | — | — | QAT File flyout, self-correcting placement; items open from `commandCreated` |
| document | `versiondiff` | `Version Diff.md` | ✓ | `timeline_model.py`, `feature_icons.py`, `html_report.py` | — | ships disabled |
| exports | `exportbomcsv` | `Export BOM.md` | ✓ | — | `test_csv_injection.py` | |
| exports | `exportmermaid` | `Export Mermaid.md` | ✓ | — | — | |
| partmodeling | `sketchfix` | `SketchFix.md` | ✓ | — | — | |
| partmodeling | `roundsketchdimensions` | `Round Sketch Dimensions.md` | ✓ | `rounding.py` | `test_roundsketchdimensions_rounding.py` | `executePreview` apply |
| partmodeling | `sketchunderconstrained` | `SketchUnder.md` | ✓ | — | — | |
| partmodeling | `sketchcirclecenterpoint` | `RadialHoleCircle.md` | ✓ | — | — | beta; ships disabled (graphics issue) |
| partmodeling | `timelinecompute` | `Timeline Compute Times.md` | ✓ | — | — | |
| partmodeling | `measurepath` | `Measure Path.md` | ✓ | `pathgraph.py` | `test_measurepath_pathgraph.py` | custom graphics reference impl |
| partmodeling | `mirrorderive` | `MirrorDerive.md` | ✓ | — | — | |
| partmodeling | `hideobjects` | `HideObjects.md` | ✓ | — | — | |
| partmodeling | `flattensurface` | `Flatten Surface.md` | ✓ | `flatten.py`, `report.py` | `test_flattensurface_{flatten,segments,cracks,report,entry}.py` | beta; pure solver, see `docs/dev/Flatten Surface solver.md` |
| animation | `animationnamedview` | `Animation Named View.md` | **missing** | `logic.py` | `test_animationnamedview_logic.py` | Publisher workspace IDs |
| related | `confighub` | `Select Related Data Folder.md` | ✓ | — | — | launched from Preferences Hub Settings |
| related | `relateddata` | `Related Data.md` | ✓ | — | — | SOLID tab only |
| teamaddins | `configteamaddins` | `Set Up Shared Add-ins Folder.md` | **missing** | — | — | icon shared with `teamaddins` generator |
| teamaddins | `teamaddins` | `Team Add-ins.md` | ✓ | `catalog.py` | `test_teamaddins_catalog.py`, `_installer.py`, `_sync.py`, `_team_fs.py` | palette, settings; timer deferral |
| tools | `scriptsmanager` | `Scripts and Add-ins.md` | ✓ | — | — | QAT File, anchors before `PT_preferences` |
| share | `shareDocument` | `Get a Share Link.md` | ✓ | — | — | QATRight Share flyout |
| share | `shareSettings` | `Change Share Settings.md` | ✓ | — | — | |
| share | `OpenDesktop` | `Get Open on Desktop Link.md` | ✓ | — | — | |
| share | `OpenInTeam` | `Get Open in Team Link.md` | ✓ | — | — | |
| share | `projectInvite` | `Invite to Project.md` | ✓ | — | — | |
| share | `projectMembers` | `Document Project Members.md` | ✓ | — | — | |

Other tests not tied to one command: `test_json_utils.py`, `test_recents_utils.py`,
`test_fusion_recents.py`, `test_pump_events.py`, `test_general_utils_debug_log.py`,
`test_settings_validate.py`, `test_settings_command_sets.py`,
`test_config_animation_workspace.py`, `test_command_abort.py` (includes the AST
guard against `doExecute` in `commandCreated`), `test_command_icons.py`,
`test_release_build.py`, `test_readme_pdf_build.py` (fails locally the moment
`README.md` is edited without rebuilding the PDF).

---

## Non-registry folders under `commands/`

| Folder | What it is |
|---|---|
| `preferences/` | Infrastructure command (always started first by `commands/__init__.py`); the Preferences palette (`resources/html/app.js` holds `CMD_SECTIONS`, `groupExtras()`, `commandRow()`; command sets come from `settings_store.COMMAND_SETS`, not the page) |
| `partnumber_shared/` | Shared library for the three part/drawing-number commands: `hub_fs.py`, `pn_cache.py`, `intent.py`, `schemes.py`, `mfgdm_props.py` (GraphQL `mfgdm://v3`) |
| `assemblyintent/` | **Dead** -- only `__pycache__` remains from the rename to `assemblypalette`; safe to delete locally |

---

## `lib/ptAddInUtils` index

Import order in `__init__.py` is fixed (`general_utils` first; `# ruff: noqa: I001`).

| Module | Public names | Use it for |
|---|---|---|
| `general_utils.py` | `log()`, `debug_log_path()`, `pump_events_for()`, `clipText()`, `isSaved()`, `handle_error()`, `perf_timer()` | Logging (DEBUG-gated), event pumping, clipboard, error reporting |
| `event_utils.py` | `add_handler(event, cb, *, name, local_handlers)`, `clear_handlers()` | Every Fusion event hookup; handlers are retained against GC |
| `selection_utils.py` | `capture_selections()`, `picked()`, `picked_one()` | Reading `SelectionCommandInput` safely |
| `json_utils.py` | `read_json()`, `write_json_atomic()` | All user-authored JSON state |
| `ui_utils.py` | `get_or_create_panel()`, `remove_from_panel()`, `get_qat_file_dropdown()`, `get_or_create_qat_file_flyout()`, `remove_from_qat_file_flyout()`, `remove_from_qat_file_dropdown()`, `get_or_create_qat_right_flyout()`, `remove_from_qat_right_flyout()` | Command-owned containers |
| `cache_utils.py` | `get_active_project()`, `resolve_target_folder()`, `target_project_label()`, `safe_activate()`, Global Parameters cache read/write helpers | Active project (defensive), GP caches |
| `recents_utils.py` | `list_recent()`, `remember_recent_if_eligible()`, `touch_recent()`, thumbnail store (`cached_thumbnail_path()`, `store_thumbnail_object()`, `render_thumbnail_for_doc()`), `design_intent()` | Recents + thumbnails shared by Assembly Palette and Open Recent |
| `fusion_recents.py` | `resolve_recents_path()`, `parse_recents()`, `list_native_recents()`, `intent_from_docstruct()`, `resolution_trace()` | Fusion's own recents file (pure stdlib) |
| `intent_icons.py` | `data_uri()`, `stylesheet()`, `write_stylesheet()`, `css_var()` | Design-intent icons for palettes |
| `upload_utils.py` | `wait_for_upload(save_result, context_label, ...)` | Polling a save/upload to completion |
| `attributes_utils.py` | `attributes_for_selection()`, `get_all_attributes()`, `get_comptypes()`, `update_feedback_from_list()` | Attribute inspection (Autodesk-derived) |
| `date_utils.py` | `next_business_day()`, `compute_quick_dates()` | Date helpers |
| `log_utils.py` | `default_log_directory()`, `open_live_log_viewer()` | Live log tail (Console.app / PowerShell) |

---

## UI access points

| Location | Fusion IDs | Created by | Example command |
|---|---|---|---|
| Power Tools panel (Design > Tools tab) | `FusionSolidEnvironment` / `ToolsTab` / `PT_Power Tools` | `_ui_bootstrap` (shared) | `assemblystats` |
| QAT File dropdown | `FileSubMenuCommand` | Fusion; looked up via `ptutil.get_qat_file_dropdown()` | `preferences` (retry), `openrecent` (flyout), `scriptsmanager`, `closealldocuments` |
| QATRight Share flyout | `shareDropMenu` | `ptutil.get_or_create_qat_right_flyout()` | `shareDocument` |
| Drawing tab panel | `FusionDocTab` / `PT_DrawingPowerTools` | command | `assigndrawingnumber` |
| Manage tab panel (needs Manage Extension) | `ManageTab` / `PT_ManagePowerTools` | command | `syncitempartnumber` |
| Animation (Publisher) panel | `Publisher3DEnvironment` / `Animation` / after `PublisherViewPanel` | command via `config.resolve_animation_workspace_id()` | `animationnamedview` |
| Inspect panels, all design workspaces | discovered at runtime | command | `measurepath` |
| Marking (right-click) menu | `markingMenuDisplaying` hook | command | `changecyclecolor` |
| Assembly INSERT panel | below Insert STEP | command | `assemblypalette` launch button |
| Palettes | `IMA_LLC_PowerTools_*` (`config.py` section 7) | command | `assemblybuilder`, `assemblypalette`, `preferences`, `teamaddins` |

Built-in tabs and panels are never deleted; only our controls are.

---

## State on disk

| Path | Owner | Git |
|---|---|---|
| `settings/preferences.json` | `settings_store` | ignored; regenerated from defaults; forbidden in release |
| `cache/settings.json` | legacy `config.load_settings()` | ignored |
| `cache/hub.json` | Related Data (`config.loadHub`) -- root `hub.json` is a stale copy | ignored (root copy tracked but release-excluded) |
| `cache/recent_docs.json`, `cache/thumbs/` | `recents_utils` | ignored |
| `cache/favorites_<hub>.json` | `favorites` | ignored |
| `cache/powertools-debug.log` | `ptutil.log` when `.debug` present (5 MB cap) | ignored |
| `commands/*/resources/html/init.js`, `intent-icons.css` | palettes (generated on open) | ignored by glob |
| `.debug` | developer marker: `DEBUG` + debugpy server on 5678 | ignored; forbidden in release |
| `<options root>/<user>/<hub>_RecentsWithoutSearch_1.json` | Fusion (read-only for us) | n/a |

---

## "Where is the example of..."

| Pattern | Look at |
|---|---|
| No-input command acting from `commandCreated` | `commands/closealldocuments/entry.py`, `scriptsmanager`, `datatoggle`, `preferences` |
| Retrying a QAT control from `documentActivated` | `commands/preferences/entry.py::_ensure_control` |
| Self-correcting flyout placement, candidate control IDs | `commands/openrecent/entry.py` |
| Ending a command from `commandCreated` when a precondition fails | `commands/_command_abort.py`; `commands/changecyclecolor/entry.py`, `versiondiff`, `roundsketchdimensions`, `assigndrawingnumber` |
| `threading.Timer` -> `fireCustomEvent` deferral | `commands/assemblypalette/entry.py` (post-insert chain, thumbnail pump), `commands/teamaddins/entry.py` (launch check) |
| Polling an `adsk.core.Future` without blocking | `commands/assemblypalette/entry.py` thumbnails; inline variant behind a progress bar in `commands/refmanager` |
| Deferring heavy work to a `CustomEvent` after the dialog closes | `commands/externalize/entry.py` |
| Waiting on a save/upload | `ptutil.wait_for_upload`, used by `bottomupupdate`, `closealldocuments` |
| Suspend autosave / re-acquire handles across pumped waits | `commands/bottomupupdate/entry.py` (`_suspend_autosave`, `close_processed_document`, `sweep_stray_documents`) |
| Selection capture | `commands/externalize/entry.py`, `commands/measurepath/entry.py` |
| Custom graphics in `executePreview`, billboarded text, cones | `commands/measurepath/entry.py` |
| `executePreview` apply with revert-on-cancel | `commands/roundsketchdimensions/entry.py` |
| Palette RPC (`incomingFromHTML`, `sendInfoToHTML`, `init.js` bootstrap) | `commands/preferences/entry.py` + `resources/html/app.js`; `commands/assemblybuilder` |
| "No target project" banner / defensive active project | `commands/assemblypalette`, `commands/assemblybuilder`, `cache_utils.resolve_target_folder` |
| Marking-menu-only command with a live preference | `commands/changecyclecolor/entry.py` |
| Runtime workspace/tab discovery with pinned IDs | `config.py` section 3c, `commands/animationnamedview/entry.py` |
| GraphQL to MFGDM | `commands/partnumber_shared/mfgdm_props.py` |
| Hub folder as a catalogue, revision fingerprinting, safe install | `commands/teamaddins/{catalog,installer,team_fs}.py` |
| Pure-logic module + test pairing | `measurepath/pathgraph.py` <-> `tests/test_measurepath_pathgraph.py`; `refresh/logic.py` <-> `tests/test_refresh_logic.py`; `flattensurface/flatten.py` <-> `tests/test_flattensurface_*.py` (large solver) |
| Atomic JSON writes | `ptutil.write_json_atomic` (favorites, hub config, preferences) |
| Reading Fusion's own recents | `lib/ptAddInUtils/fusion_recents.py` |
| Generated icons | `commands/teamaddins/resources/generate_icons.py` + `tools/icons/iconkit.py` |

---

## Developer tooling

| Task | Command |
|---|---|
| Bootstrap | `python3 -m venv .venv && .venv/bin/pip install "ruff==0.15.20" "pytest>=8.0"` |
| The four CI gates | `ruff format --check .` · `ruff check .` · `python -m pytest -q` · `python tools/pandoc/build_readme_pdf.py --check` |
| Format | `ruff format .` |
| Release dry run | `python tools/release/build_release.py --version v0.0.0-test` -> `dist/` |
| README PDF | `python tools/pandoc/build_readme_pdf.py` (pandoc + xelatex), `--check` (stamp vs. README, no toolchain), `--if-stale` (what the release build runs). On a TeX Live install with a stale `xelatex.fmt` the wrapper stops on a kernel-date warning after writing the PDF -- see the `build-readme-pdf` skill |
| Icons | `python commands/<cmd>/resources/generate_icons.py` |
| Debug in Fusion | `touch .debug`, Run the add-in, attach on 5678 (Zed) or use the Debug button (VS Code, 9000) -- [debugging.md](debugging.md) |
| Blame without reformat noise | `git config blame.ignoreRevsFile .git-blame-ignore-revs` |

Fusion itself runs only on macOS and Windows; a Linux checkout can run every
tool above except Fusion.

---

## Stale, dead, or known-missing

- `commands/assemblyintent/` -- dead leftover (`__pycache__` only) from the
  rename to `assemblypalette`.
- `docs/arch/Animation Named View.md` and
  `docs/arch/Set Up Shared Add-ins Folder.md` do not exist; every other
  command has its arch note.
- `docs/arch/architecture.md` "File structure reference" still shows
  `docs_arch/` and lists ~42 commands; the folder is `docs/arch/` and the
  registry has 52.
- `docs/dev/debugging.md` is written for the macOS dev machine
  (pre-production Fusion build, `~/Library/...` paths).
- `config.get_or_create_pt_settings_dropdown()` and the PTSettings flyout are
  legacy (the flyout was consolidated into Preferences in `b6f4525`); the
  bootstrap no longer creates it.
- Root `hub.json` is a stale org copy kept tracked but release-excluded.

---

## Regenerating the command table

```python
# python3 - <<'EOF'  (from the repo root)
import importlib.util, os
spec = importlib.util.spec_from_file_location("reg", "command_registry.py")
reg = importlib.util.module_from_spec(spec); spec.loader.exec_module(reg)
for g, c in reg.iter_commands():
    m, d = c["module"], c["doc"]
    folder = f"commands/{m}"
    pure = [f for f in os.listdir(folder) if f.endswith(".py")
            and f not in ("__init__.py", "entry.py")
            and "adsk" not in open(os.path.join(folder, f)).read()]
    arch = "✓" if os.path.exists(f"docs/arch/{d}") else "**missing**"
    print(f"| {g['key']} | `{m}` | `{d}` | {arch} | {', '.join(pure) or '—'} | | |")
# EOF
```

---

*Copyright © 2026 IMA LLC. All rights reserved.*
