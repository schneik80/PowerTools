---
name: generate-icons
description: Create or regenerate a command's icon set (16/32/64 px, light/dark/disabled) with the stdlib SDF renderer in tools/icons/iconkit.py, and pin it in tests/test_command_icons.py.
---

# Generate command icons

Fusion reads a command's `resources/` folder directly and picks
`16x16.png`, `32x32.png`, `64x64.png` plus the `-dark` and `-disabled` variants
by filename. Nothing validates them at runtime, so the repo draws them with a
deterministic generator and pins the result in a test.

Machinery: `tools/icons/iconkit.py` (signed-distance-field shapes on a 64-unit
grid, supersampled, written as 8-bit RGBA PNG with `zlib`/`struct` -- no Pillow,
because Fusion's embedded Python has none and the add-in carries no third-party
dependencies). Each command family keeps only its geometry in
`commands/<cmd>/resources/generate_icons.py` and loads the kit by path.

Existing generators to copy from:

| Generator | What it shows |
|---|---|
| `commands/teamaddins/resources/generate_icons.py` | Two commands from one script, a badge overlay with a knock-out ring, a separate 16 px redraw |
| `commands/assignpartnumbers/resources/generate_icons.py` | Number-sign family shared by three commands |
| `commands/measurepath/resources/generate_icons.py` | Single command, stroke geometry |
| `commands/versiondiff/resources/generate_icons.py` | Single command |

## Steps

1. Copy the closest generator into `commands/<cmd>/resources/generate_icons.py`
   and keep only the glyph geometry; leave the two-line `importlib` loader for
   `iconkit.py` as is (`Path(__file__).resolve().parents[3] / "tools" / "icons" / "iconkit.py"`).
2. Design on the 64-unit grid. **Redraw the 16 px variant instead of scaling**:
   at 16 px one pixel is four grid units, so leaning strokes and diagonal
   arrowheads smear across pixel boundaries (e263d4e). Use heavier bars, no
   lean, and edges on whole pixels for the small size.
3. Write all nine files per command: sizes `16x16`, `32x32`, `64x64` x variants
   `""`, `-dark`, `-disabled` (`iconkit.SIZES`, `iconkit.ALL_VARIANTS`). The
   disabled grey has to read on both themes -- Fusion has one disabled slot
   per size, no dark counterpart.
4. Run it from the repo root with any Python 3.10+:

   ```bash
   python commands/<cmd>/resources/generate_icons.py
   ```

5. Pin the set in `tests/test_command_icons.py`: add an `IconSet(command=...,
   variants=ALL_VARIANTS, placeholder=<command it used to copy, or None>)`. The
   suite also asserts that no two commands ship byte-identical art -- the
   regression that motivated the generators (five commands wore another
   command's icon).
6. Run `python -m pytest -q tests/test_command_icons.py`, then `ruff format .`
   and `ruff check .` (the generator is a tracked `.py` and is linted; it is
   excluded from the release zip by the `commands/*/resources/generate_icons.py`
   glob in `tools/release/build_release.py`).
7. If the command is new to the Preferences palette, check the icon also reads
   at 16 px next to its neighbours there.

## Notes

- Design sources (`*.idraw`, `*.pxd`, `fusion_icon_resources*`) sitting next to
  older hand-drawn icons are excluded from the release by glob; leave them.
- Do not "fix" an icon by copying another command's PNGs -- that is the exact
  bug the test guards against.
