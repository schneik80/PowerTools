# Working conventions

## This repo does not use pull requests

The user has corrected this more than once, so treat direct-to-`main` as the
standing default rather than something to confirm each time. **Do not offer or
create a PR, and do not leave the feature branch behind.**

When asked to commit — or to "commit and sync", or "commit and push":

```bash
git switch -c <type>/<short-slug>     # still branch first: keeps work isolated
# ... change, then run the four gates (.agent/environment.md) ...
git add -A && git commit              # message conventions below
git switch main
git merge --ff-only <branch>          # prefer ff-only; main is mostly linear
git push
git branch -d <branch>
git push origin --delete <branch>     # only if it was ever pushed
```

Why branch at all if it merges straight in: it keeps the work isolated while
the gates run, and it makes the merge a single reviewable unit. Prefer
`--ff-only`; the handful of merge commits in the history (`3a7d906`,
`6761b86`) exist because those branches genuinely diverged, not as policy. If
`--ff-only` refuses, rebase or make a real merge commit deliberately and say
which you did.

Branch prefixes in use: `feat/`, `fix/`, `chore/`, `docs/`.

**Do not commit or push unless asked.** The one exception to "ask first" is
scope, not permission: once the user says commit, finish the whole sequence
above — merge, push, delete — without stopping to confirm each step.

## Issues

The user often asks for an issue alongside the work ("create an issue too and
close it on merge to main"). Use `gh`:

```bash
gh issue create --title "..." --body "..."
```

Then put `Closes #N` in the commit body so the merge closes it — see `c8c0382`,
`2afdbe1`, `00302fd` for the shape. Do not create issues unprompted.

## Commit messages

`Area: imperative summary`, or a plain imperative line:

```
Change Cycle Color: stop crashing Fusion when nothing is selected
Keep README.pdf current before the release zip
```

The body explains **why**, cites the commits it corrects or builds on, and ends
with `Closes #N` when applicable. Agent-written commits carry a
`Co-Authored-By:` trailer (both `Claude Opus 5 (1M context)` and
`Claude Fable 5` appear in the history).

Three things the body must be honest about:

- **"Not yet exercised in Fusion"** — say it when true. The test suite stubs
  `adsk`, so it proves pure logic only; a green suite is not evidence the
  add-in works. It is always true of work done on `ryzen-nobara.local`, since
  there is no native Linux Fusion client for it to run.
- **Which device *and which channel* it was tested on.** Work is split across
  three devices ([roster](environment.md#device-roster)), and the two that run
  Fusion each carry **production and pre-production side by side** — so a
  device name alone does not identify the build. This codebase has already
  shipped a macOS-only path bug that only Windows found (`25d5f48`,
  `93c6b36`), so "tested and working" without a device says nothing about
  platform coverage, and without a channel it says nothing about build
  coverage. Name both, and say plainly when a platform- or build-sensitive
  change was exercised on only one.
- **Which API properties were verified**, and against what. Verify against the
  stubs in Fusion's `API/Python/defs` or the official reference, never memory.

Mechanical reformat commits are isolated and added to `.git-blame-ignore-revs`
(`0de55c8`, `89f298d`, `ef424c6`).

## Docs are part of the change

Not a follow-up. A command change is not done until the contract holds:
registry entry, `CMD_Description`, `docs/<Doc>.md` + `docs/arch/<Doc>.md` +
a row in `docs/arch/index.md` + a README row, generated icons pinned in
`tests/test_command_icons.py`, and `README.pdf` rebuilt if `README.md` moved.
Full checklist: `.claude/rules/commands-registry.md`.

User-facing text — descriptions, tooltips, palette copy — comes from `docs/`,
not invented, and stays ASCII (`aa6802e`).

## When corrected, write it down

In the same change as the fix, not later. Routing table:
[`README.md`](README.md#maintaining-this). At minimum, a durable Fusion lesson
goes in `docs/dev/lessons.md` with the commit hash that paid for it.

---
*Copyright © 2026 IMA LLC. All rights reserved.*
