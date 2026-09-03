# `.agent/` — tool-neutral agent guidance

Start with [`AGENTS.md`](../AGENTS.md) in the repository root. It is the entry
point for every AI coding tool and it is deliberately short.

This folder holds the guidance that is **not** path-scoped and therefore has no
natural home in `.claude/rules/`: how the guidance system itself is organised,
the per-device toolchain and path reference, a symptom-first triage index, and
the git/issue conventions. It is tool-neutral on purpose — Claude
Code reads `AGENTS.md` through `CLAUDE.md`, but Cursor, Copilot, Codex and
anything else should be able to find the same material without knowing about
`.claude/`.

| File | Read it for |
|---|---|
| [`environment.md`](environment.md) | The device roster, the commands that actually work on each, Fusion paths, API stubs, crash dumps, MCP servers |
| [`symptom-index.md`](symptom-index.md) | "Fusion did *X*" → likely cause → the rule and commit that explain it |
| [`workflow.md`](workflow.md) | Branch/commit/merge/issue conventions. **No pull requests** in this repo |

## How the guidance is layered

Read the layer that matches what you are about to touch. Each layer is the
long form of the one above it, so escalate only when you need the detail.

```
CLAUDE.md                 one line: @AGENTS.md
  AGENTS.md               entry point; 20 non-negotiables, where-to-look table
    .agent/*.md           tool-neutral: environment, symptom triage, workflow
    .claude/rules/*.md    path-scoped checklists, loaded by matching `paths:`
      docs/dev/lessons.md the mistakes ledger — long form, with commit hashes
      docs/dev/*.md       setup, codebase map, debugging, release, API recipes
      docs/arch/*.md      per-command architecture notes
```

`.claude/rules/*.md` carry a YAML `paths:` front-matter block. Claude Code loads
a rule automatically when a file matching one of its globs is in play; other
tools do not. **If your tool does not load them, read the matching rule
yourself before editing the paths it covers.** Current rules:

| Rule | Covers |
|---|---|
| `.claude/rules/fusion-api.md` | `commands/**`, `lib/**`, `config.py`, `PowerTools.py` |
| `.claude/rules/commands-registry.md` | `command_registry.py`, `settings_store.py`, `commands/*/entry.py` |
| `.claude/rules/tests-ci.md` | `tests/**`, `pyproject.toml`, `.github/**` |
| `.claude/rules/palettes-html.md` | `commands/*/resources/html/**` |
| `.claude/rules/docs-release.md` | `docs/**`, `README.md`, `README.pdf`, `tools/**` |

Skills live in `.claude/skills/` (`build-readme-pdf`, `generate-icons`) and are
invoked by name; they encode multi-step recipes that have a right order.

## Maintaining this

The rule the repo actually enforces on itself: **when the user corrects you on
something durable, write it down in the same change as the fix.** Where it goes
depends on what kind of thing it is.

| What you learned | Where it goes |
|---|---|
| A Fusion API behaves surprisingly | `docs/dev/lessons.md` + a line in `.claude/rules/fusion-api.md` |
| A rule that only applies to certain paths | the matching `.claude/rules/*.md` |
| A one-line non-negotiable worth loading every session | numbered list in `AGENTS.md` |
| A symptom you had to diagnose from scratch | a row in [`symptom-index.md`](symptom-index.md) |
| A tool/path/command fact you had to hunt for | [`environment.md`](environment.md) |
| A process or git convention | [`workflow.md`](workflow.md) |
| Where some code lives | `docs/dev/codebase-map.md` |

Three standing constraints on anything added here:

- **Cite the commit.** Every claim in `lessons.md`, `AGENTS.md` and the rules
  names the hash that paid for it, so a future reader can `git show` it instead
  of taking the note on faith. Keep that habit.
- **Name the device.** This project is developed on **three devices**
  (see the roster in [`environment.md`](environment.md#device-roster)), so
  "on this machine", "locally" and "here" are ambiguous and therefore useless.
  Tag any device-specific observation with the device — hostname and OS version
  at minimum, plus the detail that actually mattered (CPU architecture, Fusion
  channel, how a tool was installed). Run `hostname && uname -sm` first if you
  are unsure where you are. If a fact holds on all three, say so explicitly
  rather than leaving it untagged by accident.
- **Prefer a pointer to a copy.** These files are already at risk of drifting
  from the code. Cross-link into `docs/` rather than restating it; restating a
  detail in two places means one of them will be wrong later.

## This folder does not ship

`.agent/` is developer material and is excluded from the release zip in
`tools/release/build_release.py` (`EXCLUDED_DIRS`), alongside `.claude/`,
`tests/`, `tools/`, `docs/dev/` and `docs/arch/`. `tests/test_release_build.py`
pins that exclusion. It is deliberately **not** git-ignored — the guidance is
tracked so it travels with the repo; only `.claude/settings.local.json`
(per-machine permission overrides) stays local.

---
*Copyright © 2026 IMA LLC. All rights reserved.*
