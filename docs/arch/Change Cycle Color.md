# Change Cycle Color — Architecture

[← Change Cycle Color guide](../Change%20Cycle%20Color.md)

## Architecture

Change Cycle Color is a selection-driven command surfaced only through Fusion's right-click marking menu. It subscribes to the `markingMenuDisplaying` event and, when at least one Component or Occurrence is selected and its preference is enabled, injects its entry into the linear marking menu immediately after Fusion's built-in **Cycle Component Color** command. On invocation it opens a dialog containing rows of rainbow swatch buttons plus a **Custom color…** button. The palette is read live from the `ColorCycleTable` of the lighting environment Fusion is currently rendering with — resolved from `Application.lightingEnvironment` — and rendered as cached PNG icons built with only the Python standard library. Applying a color writes `Component.componentColor` (never **Appearance**) through the Fusion Python API for every selected component. The custom-color path opens the OS-native picker, applies the color directly, and dismisses the dialog through Fusion's normal execute path — guarded by a `_skip_normal_execute` flag so the color is not applied twice.

```mermaid
C4Context
  title Change Cycle Color – System Context

  Person(user, "Design Engineer", "Autodesk Fusion user working with a component assembly")
  System(addin, "PowerTools / Change Cycle Color", "Autodesk Fusion add-in command")
  System_Ext(fusion, "Autodesk Fusion", "Host application — adsk.core / adsk.fusion; fires markingMenuDisplaying")
  System_Ext(riverrubicon, "Environment XMLs", "One shipped XML per lighting environment, each with its own built-in ColorCycleTable (palette source)")
  System_Ext(ospicker, "OS Color Picker", "macOS: AppleScript 'choose color' via /usr/bin/osascript; Windows: bundled pythonw.exe running tkinter.colorchooser")

  Rel(user, addin, "Right-clicks component, selects Change Cycle Color, picks swatch or custom color, clicks Apply")
  Rel(addin, fusion, "Hooks markingMenuDisplaying; reads selection + lightingEnvironment; writes Component.componentColor")
  Rel(addin, riverrubicon, "Reads the active environment's ColorCycleTable RGB values")
  Rel(addin, ospicker, "Opens native picker when user clicks Custom color…")
```

```mermaid
C4Container
  title Change Cycle Color – Container View

  Person(user, "Design Engineer")

  Container_Boundary(cmd, "Change Cycle Color command") {
    Container(entry, "Command + Dialog", "commands/changecyclecolor/entry.py", "Lifecycle, marking-menu hook, swatch dialog, custom-color flow, applies componentColor")
    Container(palette, "Palette Loader", "colors.py", "Loads + sorts the ColorCycleTable; hex<->rgb helpers")
    Container(icons, "Swatch Icons", "swatches.py", "Stdlib PNG swatch + custom-button icons")
    ContainerDb(cache, "Icon Cache", "cache/changecyclecolor/", "Generated PNG icon folders (swatches/, custom_btn/)")
  }

  System_Ext(fusion, "Fusion API", "adsk.core, adsk.fusion")
  System_Ext(riverrubicon, "Environment XMLs")
  System_Ext(ospicker, "OS Color Picker")

  Rel(user, entry, "Right-click → dialog → swatch / Custom color… → Apply")
  Rel(entry, palette, "load_color_cycle / sort_rainbow")
  Rel(entry, icons, "ensure_all / ensure_quadrant_icon")
  Rel(icons, cache, "Writes 16/32/64 px PNGs")
  Rel(palette, riverrubicon, "Parses the active environment's ColorCycleTable")
  Rel(entry, fusion, "markingMenuDisplaying; addCommand; lightingEnvironment; componentColor")
  Rel(entry, ospicker, "Custom color… → native picker")
```

```mermaid
C4Component
  title Change Cycle Color – Module View

  Container_Boundary(cmd, "commands/changecyclecolor") {
    Component(entry, "entry.py", "Command entry point", "start/stop lifecycle; markingMenuDisplaying hook (settings-gated); _active_environment_name / _load_palette pick the palette source; command_created builds the dialog; input_changed; execute writes componentColor; destroy surfaces deferred errors; _enter_custom_color_flow / _pick_color_native")
    Component(colors, "colors.py", "Palette loader", "load_color_cycle parses ColorCycleTable; sort_rainbow orders by hue; hex_to_rgb / rgb_to_hex; missing-decimal-point repair for shipped XML typos")
    Component(swatches, "swatches.py", "Icon generator", "Stdlib-only PNG generation (struct + zlib, no PIL); per-color swatch folders + 4-quadrant Custom-color button icon; cached under cache/changecyclecolor/")
    Component(install, "fusion_install.py", "Fusion path resolver", "find_environments_dir / find_environment_xml locate a named environment's XML by walking up from adsk.__file__; lighting_environment_dirs maps the LightingEnvironments enum onto folder names; find_bundled_python locates the interpreter for the picker subprocess. Platform-dependent shapes live in pure, per-platform helpers")
    Component(picker, "_color_picker_subprocess.py", "Out-of-process Tk", "Runs tkinter.colorchooser in a fresh Python process; emits chosen hex on stdout (non-macOS path)")
  }

  System_Ext(fusion, "Fusion API")
  System_Ext(riverrubicon, "Environment XMLs")
  System_Ext(ospicker, "OS Color Picker")

  Rel(entry, colors, "Loads + sorts the active environment's palette on command_created")
  Rel(entry, install, "_active_environment_name → find_environment_xml")
  Rel(colors, riverrubicon, "Parses the ColorCycleTable of the given XML")
  Rel(entry, swatches, "ensure_all (swatch icons); ensure_quadrant_icon (Custom button)")
  Rel(entry, picker, "Spawns bundled Python for the picker (non-macOS)")
  Rel(picker, ospicker, "tkinter.colorchooser")
  Rel(entry, ospicker, "osascript 'choose color' (macOS)")
  Rel(entry, fusion, "markingMenuDisplaying; addCommand; reads selection; writes componentColor")
```

### Main flow — swatch selection

```mermaid
sequenceDiagram
    participant User
    participant Fusion as Fusion API
    participant Entry as entry.py
    participant Colors as colors.py
    participant Install as fusion_install.py
    participant Swatches as swatches.py

    User->>Fusion: Right-click Component or Occurrence
    Fusion->>Entry: markingMenuDisplaying event
    Entry->>Entry: Read "Show in the right-click context menu" setting
    alt setting is ON and a Component/Occurrence is selected
        Entry->>Fusion: linearMarkingMenu.addCommand(CMD_ID) after Cycle Component Color
    end

    User->>Fusion: Click Change Cycle Color
    Fusion->>Entry: command_created event
    Entry->>Entry: _collect_selected_components() (dedupe instances)
    Entry->>Entry: Reuse cached palette only if the environment is unchanged

    Entry->>Fusion: app.lightingEnvironment
    Fusion-->>Entry: LightingEnvironments value
    Entry->>Install: lighting_environment_dirs() → find_environment_xml(name)
    Install-->>Entry: Path to <Env>/<Env>.xml (or None)
    alt environment resolved
        Entry->>Colors: load_color_cycle(path) → sort_rainbow()
    else unknown environment / no table
        Entry->>Install: find_river_rubicon_xml()  // logged fallback
        Entry->>Colors: load_color_cycle(fallback) → sort_rainbow()
    end
    Colors-->>Entry: Sorted [(name, rgb)] swatches (empty if not found)

    Entry->>Swatches: ensure_all() + ensure_quadrant_icon()
    Swatches-->>Entry: Cached PNG icon folders

    Entry->>Fusion: Build swatch rows + Custom color… button; okButtonText = "Apply"
    Fusion-->>User: Dialog displayed

    User->>Fusion: Click a swatch, then Apply
    Fusion->>Entry: command_execute event
    loop For each captured target (deduplicated)
        Entry->>Fusion: component.componentColor = Color.create(r, g, b, 255)
    end
    Fusion->>Entry: command_destroy event
    Entry->>User: Surface any deferred error (messageBox)
```

### Custom color flow

```mermaid
sequenceDiagram
    participant User
    participant Fusion as Fusion API
    participant Entry as entry.py
    participant Picker as OS picker (osascript / subprocess)

    User->>Fusion: Click "Custom color…" button
    Fusion->>Entry: command_input_changed (custom button)
    Entry->>Entry: _enter_custom_color_flow()
    Entry->>Picker: _pick_color_native(initial)

    alt macOS
        Picker->>Picker: /usr/bin/osascript -e 'choose color' (0–65535 channels)
    else Windows / other
        Picker->>Picker: bundled pythonw.exe _color_picker_subprocess.py (tkinter.colorchooser → hex on stdout)
    end
    Picker-->>Entry: (r, g, b) tuple, or None on cancel / failure (failure also raises a messageBox)

    opt color chosen
        loop For each captured target (deduplicated)
            Entry->>Fusion: component.componentColor = Color.create(r, g, b, 255)
        end
        Entry->>Entry: _skip_normal_execute = True
        Entry->>Fusion: cmd.doExecute(True)  // dismiss the dialog
        Fusion->>Entry: command_execute event
        Entry->>Entry: _skip_normal_execute is True → return without re-applying
        Fusion->>Entry: command_destroy event
        Entry->>User: Surface any deferred error (messageBox)
    end
```

## Module breakdown

- **`entry.py`** — command lifecycle (`start` / `stop`), palette sourcing (`_active_environment_name` reads `app.lightingEnvironment`; `_load_palette` resolves that environment's XML and falls back to RiverRubicon with a log line), the swatch dialog (`command_created`, `command_input_changed`, `command_execute`, `command_destroy`), the `markingMenuDisplaying` hook (`_on_marking_menu_displaying`, gated by the show-in-context-menu setting), selection collection (`_collect_selected_components`, instance dedupe), the custom-color flow (`_enter_custom_color_flow`, `_pick_color_native`, `_pick_color_macos`, `_pick_color_subprocess_python`), and the apply step (`_set_component_color`, which writes `componentColor` only).
- **`colors.py`** — `load_color_cycle` parses the `ColorCycleTable` from whichever environment XML it is handed; `sort_rainbow` orders swatches by hue (pushing pale neutrals to the end); `hex_to_rgb` / `rgb_to_hex` convert between formats. The RGB tokens are 0.0–1.0 floats, and the parser repairs shipped-XML typos where the leading decimal point is missing (e.g. `"5412"` → `0.5412`).
- **`swatches.py`** — stdlib-only PNG generation (no PIL): `ensure_swatch_folder` / `ensure_all` write per-color 16/32/64 px solid swatch PNGs, and `ensure_quadrant_icon` writes the 4-quadrant rainbow icon for the **Custom color…** button. Icons are cached under `cache/changecyclecolor/` (`swatches/` and `custom_btn/`) and regenerated only when missing.
- **`fusion_install.py`** — resolves every install-relative path the command needs. `find_river_rubicon_xml` walks up from `adsk.__file__` (falling back to `sys.executable`) trying each candidate prefix in `RIVER_RUBICON_RELS`, so paths track Fusion `webdeploy` hash changes automatically; `find_environments_dir` takes that file's grandparent as the shipped `Environments` directory, and `find_environment_xml` resolves a named environment's self-titled XML beneath it (`GreyRoom/GreyRoom.xml`), with `is_safe_environment_name` refusing anything that is not a single path component. `lighting_environment_dirs` maps `adsk.core.LightingEnvironments` values onto those folder names by introspecting the enum rather than hardcoding its integers. `find_bundled_python` locates the interpreter that runs the picker subprocess, and `is_python_binary` filters the `sys.executable` fallback so the Fusion host binary is never mistaken for an interpreter. The shape-encoding helpers (`_python_candidates`, `RIVER_RUBICON_RELS`, `lighting_environment_dirs`) are pure and take the platform or enum as an argument, so `tests/test_changecyclecolor_fusion_install.py` covers the Windows layouts from a macOS run — and, when a Fusion install is present, checks the derived folder names against what actually ships.
- **`_color_picker_subprocess.py`** — a tiny standalone script that runs `tkinter.colorchooser` in a fresh Python process (used on non-macOS platforms), emitting the chosen hex on stdout. Running out-of-process avoids the in-process Tk run-loop conflict inside Fusion.

## Integration into PowerTools

- Registered in `command_registry.py` under the **Assembly** group with `settings=True`, so it gets a PowerTools Preferences card.
- Started and stopped with the rest of the add-in by `commands/__init__.py` (`start()` / `stop()`).
- Uses the shared `lib/ptAddInUtils` helpers (`add_handler`, `log`, `handle_error`) for handler registration and logging.
- Reads its **Show in the right-click context menu** toggle through `settings_store.command_setting`; the `markingMenuDisplaying` handler re-reads it live, so the preference takes effect on the next right-click with no restart.

## Design decisions

- **Stdlib-only PNG swatches.** Swatch and custom-button icons are built from raw bytes using only `struct` and `zlib`, producing valid 8-bit RGB PNGs. This avoids bundling PIL/Pillow into Fusion's embedded Python, which cannot reliably `pip install` extra dependencies.
- **Dynamic install-path discovery.** The environment XMLs live under a `webdeploy`-hash directory that changes with every Fusion update. Walking up from `adsk.__file__` (rather than hard-coding a path) keeps the palette pointed at the currently installed version and survives updates silently.
- **The palette follows the active lighting environment.** Every shipped environment carries its own `ColorCycleTable`, and they genuinely differ: the twelve shipped environments hold three distinct tables, and `RiverRubicon` — the file this command originally hardcoded — is the outlier, with 34 colors under its own naming scheme (Tangelo, Blueberry, Pistachio…) where the other five selectable environments share the same 32 (Light Pink, Dark Yellow, Turquoise Blue…). Reading a fixed file therefore showed colors that were not in the active cycle table for any user not on River Rubicon. The palette is now read from `Application.lightingEnvironment`.
- **The enum is introspected, not transcribed.** `lighting_environment_dirs` derives folder names from the `adsk.core.LightingEnvironments` member names (`GreyRoomLightingEnvironment` → `GreyRoom`) instead of hardcoding the integers `0`–`5`. Hardcoding would silently load the wrong environment's palette if Autodesk ever reordered or extended the enum — a failure that produces plausible-looking wrong colors rather than an error.
- **Palette cache keyed on the environment.** The loaded swatches are memoized in a module global, so the key includes the environment they came from; switching environments mid-session reloads on the next invocation rather than serving a stale palette. Swatch PNGs are cached by hex color, so that cache stays shared across environments and is unaffected.
- **osascript on macOS (Gatekeeper workaround).** macOS Sequoia blocks Fusion from re-spawning its bundled `Python.app` GUI helper. `/usr/bin/osascript` is a system-signed binary at a fixed path that Gatekeeper always allows, and AppleScript's `choose color` uses `NSColorPanel` underneath — so macOS uses osascript while other platforms run `tkinter.colorchooser` in a subprocess.
- **Settings-gated, live context-menu entry.** The command surfaces only through the marking menu, gated by a preference the `markingMenuDisplaying` handler re-reads on every right-click. Turning the toggle off suppresses the entry immediately, with no handler re-registration and no Fusion restart.
- **Never `doExecute` from `command_created`.** Running the command with nothing selected crashed Fusion outright (2026-09-02). The early return called `args.command.doExecute(True)` to dismiss itself, but `command_created` runs inside Fusion's `CommandDefinition::createCommand`, so doExecute re-entered the command manager on a half-constructed command; the crash stack faulted inside `Xl::APICommandDefinitionImpl::doOnCreateCommand`. `_abort_before_dialog` instead builds no inputs and lets `Command.isAutoExecute` (default true) end the command, and defers the explanation to `command_destroy` so no modal dialog runs inside the create callback either. The remaining `doExecute` call, in the custom-color flow, is fired from `command_input_changed` — outside `createCommand` — which is the use the API documents.
- **The abort has to scrub module state.** Because Fusion auto-executes a command that built no inputs, `command_execute` still fires after an abort — and `_pending_targets` / `_selected_hex` are module globals that outlive an invocation. Left alone, that auto-execute silently re-applied the *previous* run's color to the *previous* run's components. The abort clears the targets and sets `_skip_normal_execute`, either of which is enough on its own; both are set because the failure is silent data modification rather than an error.
- **`_skip_normal_execute` to prevent double-apply.** The custom-color flow applies the picked color directly, then calls `cmd.doExecute(True)` to close the dialog through Fusion's normal execute path. The flag tells `command_execute` that the work is already done so it returns without re-applying the (now stale) swatch selection.
- **Per-platform path shapes, tested from either host.** The two install-relative paths this command needs sit at different depths on macOS and Windows: the macOS install wraps everything in an `Autodesk Fusion.app` bundle, and its interpreter is `<exec_prefix>/bin/python3.x`, while Windows has no bundle wrapper and puts `python.exe` directly in `<exec_prefix>`. Encoding only the macOS shape left both lookups failing on Windows — silently, because a missing palette degrades to a Custom-color-only dialog and a missed interpreter fell through to `sys.executable`, which inside Fusion is the host binary (`Fusion360.exe`), not Python. The helpers that encode these shapes are now pure and take the platform as an argument, following `lib/ptAddInUtils/fusion_recents.py`, so the Windows branches are verified from a macOS test run rather than only on Windows.
- **`sys.executable` is filtered, not trusted.** `is_python_binary` requires an interpreter-looking basename before `sys.executable` is accepted as a fallback. Without it, handing the Fusion host executable to `subprocess` produces the worst failure mode available: no picker, no exception, and nothing in the log to distinguish it from the user pressing Cancel.
- **A dead picker reports itself.** The helper script exits non-zero when it cannot show a dialog at all (for example if `tkinter` is absent from a Fusion build's Python). That is now surfaced in a message box, because returning `None` is indistinguishable from a cancel and would leave the **Custom color…** button looking simply inert.
- **Writes `componentColor` only.** The command sets `Component.componentColor` — the value the Color Cycling Toggle reads — and never touches **Appearance** or material, so it has no effect on rendering or physical properties.

---

[← Change Cycle Color guide](../Change%20Cycle%20Color.md)

---

*Copyright © 2026 IMA LLC. All rights reserved.*
