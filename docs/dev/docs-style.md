# User documentation style guide

How `README.md` and the 54 command guides in `docs/*.md` are written. This is
the house style inferred from the best existing guides and then applied to all
of them; where guides disagreed, the choice made is recorded here. The
developer notes in `docs/arch/` and `docs/dev/` are not covered.

## What a guide is for

A guide tells a Fusion user, in this order: what the command does and why that
matters, what has to be true before it will run, where the button is, how to
use it, what every option does, what it produces, and where it stops. It
describes the command **as it is on this branch**. It is not a changelog, a
design rationale, or an API reference.

The first sentence of the **Overview** is the command's one-line summary and
opens with the command name ("Toggle Data opens or closes..."). The
`CMD_Description` constant in `commands/<module>/entry.py` is that sentence
minus the leading name, in the imperative ("Open or close...") -- it is the
tooltip, so it must not repeat the button label (AGENTS.md rule 15). Changing
the sentence is a code change too.

## Voice

- **Second person, present tense.** "Select **Assign**. The dialog closes." Not
  "the user clicks", not "will close".
- **Imperative in steps**, one action per step. "Open the drawing." "Select
  **OK**."
- **Plain and concrete.** Short sentences. Name the exact label, the exact file,
  the exact number. Prefer "hidden until you turn on **Show beta commands**" to
  "may not be visible depending on configuration".
- **Say what happens, not what the code does.** "The number is written to the
  drawing" — not "an `adsk.core.Attribute` is set". An API or class name
  appears only when the user will see it (a Fusion command name, a file name).
- **Factual benefit, no fluff.** One or two sentences on why the capability
  matters and what it does that the built-in path does not. Other CAD systems
  may be named as a point of reference ("SolidWorks users know this as
  *Repair Sketch*") but never disparaged, and PowerTools never gets a
  capability the code does not have.

## Structure template

```
# <Command name as it appears in Fusion>

[Back to README](../README.md)

## Overview
One-line summary (CMD_Description minus the command name). Then 1–3 short paragraphs: what it does,
why it matters, what it does that the built-in path does not.

> **Beta.** ...            (only for registry beta=True commands)

## Prerequisites
- bullets: document state, selection, project, hub, workspace, entitlement

## Where to find it
Exact path in Fusion UI; position anchors ("directly after **Export**").
Optional screenshot. Commands that ship disabled or are beta say so in a
callout at the end of the Overview:
> **Off by default.** Enable it under **File › PowerTools Preferences › <Group> › <Command>** and restart Fusion.
> **Beta.** Tick **Show beta commands** under **General** in **File › PowerTools Preferences**, then enable it under **<Group>**, and restart Fusion.

## How to use
1. numbered steps

## Options                  (only when the command has a dialog / palette)
| Option | Default | Effect |

## What it produces         (or "Results" for commands that change the design)
Files (exact names, folder), properties written, what is *not* changed.

## Limitations
- bullets

## Troubleshooting          (optional)
| Message or symptom | Cause | What to do |

## Preferences              (only when registry has_settings=True)
Where the settings live and what each one does.

> **Developers:** see the [architecture notes](./arch/<Doc>.md).

---

[Back to README](../README.md)

*Copyright © 2026 IMA LLC. All rights reserved.*
```

Headings are `##` sentence case. Sections that do not apply are omitted, not
left empty. Order is fixed so a reader can find "Where to find it" in the same
place in every guide. The two guides whose command has no `docs/arch/` note
(Animation Named View, Set Up Shared Add-ins Folder) omit the Developers line.

## Terminology

| Use | Not | Notes |
|---|---|---|
| Autodesk Fusion (first mention), then Fusion | Fusion 360 | Product name today |
| PowerTools | Power Tools, Power-Tools | The add-in. One word. |
| **Power Tools** panel | PowerTools panel | The toolbar panel label Fusion shows |
| **PowerTools Preferences** | PowerTools Settings | The File-menu entry and palette. The "PowerTools Settings" flyout no longer exists. |
| document | file, model | A saved Fusion item in a hub (design, drawing …) |
| design | document | The 3D content; "a design document" when both matter |
| component | part | A component definition in the browser |
| occurrence | instance, component | One placement of a component in an assembly |
| local component / external component | inline, virtual, xref | Local lives inside the document; external is its own document |
| reference | link, xref | "external reference", "referenced document" |
| hub › project › folder | Team Hub, Fusion Team hub | "Fusion Team" only for the web client |
| Data Panel | data pane, data panel | Fusion's own casing; the Toggle Data Pane command name is the exception |
| Quick Access Toolbar (QAT) | toolbar, top bar | Spell out on first use |
| File menu | File dropdown, QAT File menu | "the **File** menu on the Quick Access Toolbar" on first use |
| **Utilities** tab › **Power Tools** panel | Tools tab | Fusion labels the Design-workspace tab with ID `ToolsTab` as **UTILITIES**; write the label the user sees. (When a build has no such tab, PowerTools creates one named "Power Tools".) |
| design intent (Part, Assembly, Hybrid) | document intent, experience | Fusion's term |
| dialog | dialogue box, form | |
| select | click, tick | "select" for buttons and menu items; "tick/untick" for checkboxes |
| turn on / turn off | enable / disable | For settings the user flips |
| version | revision | Fusion saves versions; "release" only for the Document History marker |

## Formatting rules

- UI labels in **bold**, exactly as Fusion shows them: **Tools** tab,
  **Power Tools** panel, **Assign**. Menu paths use `›`: **File › Export**.
- File names, folder names, parameter names, literal values and identifiers in
  `code`. Keyboard shortcuts in **bold**: **Ctrl+S**.
- Options are tables (`Option | Default | Effect`); prerequisites and
  limitations are bullets; steps are numbered lists.
- Callouts are block quotes with a bold lead: `> **Note:**`, `> **Tip:**`,
  `> **Beta.**`. One idea per callout.
- Screenshots use a descriptive alt text and live in `docs/assets/`. Only add
  an image that shows something the text cannot. A Mermaid diagram is
  acceptable in `docs/*.md` (GitHub renders it) for a workflow with three or
  more steps or a before/after structure; never in `README.md`, which is also
  typeset to PDF by pandoc where a Mermaid block renders as plain code.
- Links between guides use the real filename, URL-quoted:
  `[Assign Part Numbers](./Assign%20Part%20Numbers.md)`. Never rename a
  `docs/*.md` file — the name is a registry and test contract.
- British/American spelling: American (color, behavior) to match Fusion's UI.
  Existing British spellings in prose are tolerated but not introduced.
- Numbers: digits, with units (`5 minutes`, `300 seconds`, `1 micron`).
- Footer line is exactly `*Copyright © 2026 IMA LLC. All rights reserved.*`.

## What not to write

- **History.** No "new", "now supports", "previously", "was changed to", "in
  this release", "recently". The guide describes today.
- **Implementation.** No Python snippets, method names, GraphQL mutations,
  event names or thread models. Those belong in `docs/arch/`. Exceptions: a
  Fusion text command a user may type, and file/attribute names the user can
  see in Fusion or on disk.
- **Unverifiable claims.** Nothing about performance, reliability or
  competitors that cannot be checked against the code or a cited source. "Often
  more reliable than Fusion's own update" is out; "runs both steps in one
  click" is in.
- **Marketing.** No "powerful", "seamless", "robust", "easy". State the
  benefit and stop.
- **Open questions, TODOs, test status.** A guide never says "still
  unverified". If a behaviour is unknown, the guide omits it.
- **Two names for one thing.** The title, the README row label and every
  mention use the label Fusion shows on the button.

## README

- The opening paragraph tells a Fusion user in ten seconds what the add-in is
  and who it is for.
- The command tables keep three columns with identical headers (pandoc pools
  their widths) and every row keeps its `./docs/<URL-quoted filename>` link
  target; labels may improve. `---` is a page break in the PDF.
- `README.pdf` is rebuilt in the same change (`python3
  tools/pandoc/build_readme_pdf.py`, then `--check`).

## Choices made where guides disagreed

| Disagreement | Choice |
|---|---|
| `## Overview` heading vs. bare opening paragraph | `## Overview` |
| "What you can do" bullets vs. "Capabilities" table | Neither as a section; the benefits go in the Overview prose, the mechanics in Options and How to use |
| "Access" at the end vs. before "How to use" | "Where to find it", before "How to use" |
| Back link text "Back to PowerTools Assembly" vs. "Back to README" | "Back to README" |
| `›` vs `>` vs `→` vs `▸` in menu paths | `›` |
| "Utilities tab" vs "Tools tab" | **Utilities** tab: the visible label of `ToolsTab` |
| kebab-case cross-links (`get-a-share-link.md`) | Real URL-quoted filenames |
| Share guides with a bold one-liner and `---` rules between every section | The common template; no rules between sections |
