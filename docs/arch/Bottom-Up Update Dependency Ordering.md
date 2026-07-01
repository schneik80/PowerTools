# Bottom-Up Update — Dependency Ordering (DAG)

[← Bottom-Up Update architecture](Bottom-Up%20Update.md) · [← Bottom-Up Update guide](../Bottom-Up%20Update.md)

This note is the deep dive on the **dependency-ordering engine** behind the
Bottom-Up Update command: how the assembly is turned into a directed acyclic
graph (DAG), how that DAG is topologically sorted so that **every part is saved
before any parent that references it**, and the invariants that keep the order
correct and cheap. It documents the code in
`commands/bottomupupdate/entry.py` — `traverse_assembly()` and
`sort_dag_bottom_up()`.

---

## 1. The invariant we must guarantee

Autodesk Fusion resolves a document's external references **against whatever
version of each child is current at save time**. If a parent assembly is saved
before its children have been updated and saved, the parent locks onto stale
child versions. The command exists to prevent exactly that.

> **Ordering invariant** — For every reference edge *parent → child*, the child
> document is opened, updated, and saved **before** the parent. Equivalently:
> the processing list is a *reverse topological order* of the reference graph
> (a leaves-first / bottom-up order).

Everything below is in service of producing and preserving that order.

---

## 2. Two units of work: components vs. documents

There are two different graphs in play, and keeping them straight is what makes
the design correct:

| | **Component graph** (build/sort operates here) | **Document graph** (the actual save unit) |
|---|---|---|
| Node | `adsk.fusion.Component` (by `name`) | A saved `dataFile` (by `id`) |
| Source | `component.occurrences` | Reference relationship between documents |
| Includes | Internal sub-components too | Only externalized/referenced documents |
| Dedup key | component `name` | `dataFile.id` |

The ordering engine builds and sorts the **component graph** (it is what the
Fusion API exposes cheaply via `occurrences`). The processing loop then maps
each component to its owning document and **deduplicates by `dataFile.id`** using
the module-level `saved` set, so that a document backing several components — or
reached along several component paths — is opened and saved exactly once. The
component-level sort and the document-level `saved` set are two complementary
dedup layers; the sort keeps the *list* clean, `saved` keeps the *side effects*
clean.

---

## 3. The pipeline

```mermaid
flowchart TD
    A["rootComponent"] --> B["traverse_assembly()<br/>Phase 1 — build the DAG"]
    B --> C["assembly_dict<br/>(nested {component, children} nodes)"]
    C --> D["sort_dag_bottom_up()<br/>Phase 2 — post-order topo sort"]
    D --> E["bottom_up_order<br/>(unique names, leaves → roots)"]
    E --> F["Processing loop<br/>open · updateAllReferences · save"]
    F --> G["saved: set[dataFile.id]<br/>document-level dedup"]
    G --> H["Root assembly saved last"]
```

---

## 4. Phase 1 — build the DAG (`traverse_assembly`)

Starting at `rootComponent`, the function walks `component.occurrences`
depth-first and records each component as a node:

```python
node = {"component": <adsk.fusion.Component>, "children": {<name>: <node>, ...}}
```

A single `_memo` dict keyed by component **name** guarantees each distinct
component's subtree is walked **once**. The node is inserted into `_memo`
*before* its children are walked, which is what makes the build itself
**cycle-safe** — a component that (pathologically) contained itself would find
its own half-built node in `_memo` and stop, rather than recurse forever.

- **First time a name is seen:** build the node, cache it, recurse into its
  occurrences.
- **Every later occurrence of that name:** reuse the *same* node object under
  the new parent. Shared sub-assemblies become **shared node references**, not
  copies — this is what turns the tree into a DAG.

Complexity: **O(V + E)** over the component graph (V = distinct components,
E = occurrence edges), instead of O(number of root-to-node paths) if subtrees
were re-walked per occurrence.

---

## 5. Phase 2 — reverse-topological sort (`sort_dag_bottom_up`)

The sort is a **depth-first, post-order traversal**: a node is appended to the
output **only after all of its children have been appended**. That post-order
discipline is precisely a reverse topological sort, and it is what satisfies the
ordering invariant in §1.

Two sets harden the walk:

- **`emitted`** — names already appended. A shared component (a *diamond*
  dependency reached through more than one parent) is appended **exactly once**,
  and the walk stays **O(V + E)** instead of re-descending a shared subtree once
  per path that reaches it (worst case *exponential* for stacked diamonds).
- **`in_progress`** — the names currently on the DFS stack (the classic
  *VISITING* state of tri-color DFS). Fusion assemblies are acyclic, but if a
  malformed graph ever presented a back edge, this **breaks and logs it**
  instead of recursing until Python raises `RecursionError`.

```python
def traverse_dag(node):
    name = node["component"].name
    if name in emitted:      # diamond already placed — don't re-walk
        return
    if name in in_progress:  # back edge — impossible for Fusion, guard anyway
        ptutil.log(f"Cycle detected at component '{name}'; skipping re-entry.")
        return
    in_progress.add(name)
    for child in node["children"].values():
        traverse_dag(child)
    in_progress.discard(name)
    emitted.add(name)
    sorted_components.append(name)
```

### Tri-color states of a node during the sort

```mermaid
stateDiagram-v2
    [*] --> UNVISITED
    UNVISITED --> VISITING: enter traverse_dag (in_progress.add)
    VISITING --> VISITED: children done (emitted.add, append)
    VISITED --> VISITED: revisited via another parent (dedup, return)
    VISITING --> VISITING: back edge detected (log, return)
    VISITED --> [*]
```

---

## 6. Worked example — a diamond

Assembly: a `Chassis` root references `GearboxAssy` and `WheelAssy`; **both**
reference the same `Fastener` part. That shared child is the diamond.

```mermaid
graph TD
    Chassis --> GearboxAssy
    Chassis --> WheelAssy
    GearboxAssy --> Fastener
    WheelAssy --> Fastener
```
*Edges point parent → child (dependency direction). `Fastener` has two parents.*

Post-order walk from the roots (`GearboxAssy`, `WheelAssy` are the top-level
entries under the root's occurrences):

```
traverse(GearboxAssy)
  traverse(Fastener)      → append "Fastener"          emitted={Fastener}
  append "GearboxAssy"                                 emitted={Fastener,GearboxAssy}
traverse(WheelAssy)
  traverse(Fastener)      → already emitted, return    (no duplicate, no re-walk)
  append "WheelAssy"
```

Result: `["Fastener", "GearboxAssy", "WheelAssy"]`.

- `Fastener` appears **once** and **before both** parents — invariant holds.
- Before hardening, the same walk produced
  `["Fastener", "GearboxAssy", "Fastener", "WheelAssy"]` — a duplicate that
  inflated `docCount`, muddied the resume index math (`list.index()` returns the
  *first* occurrence), and, for deeper stacked diamonds, re-walked shared
  subtrees super-linearly.

The `Chassis` root is intentionally **excluded** from `bottom_up_order` and saved
separately at the very end, after all children are current.

---

## 7. Why post-order DFS here (rather than Kahn's algorithm)

Both DFS post-order and Kahn's algorithm (repeatedly emit in-degree-zero nodes)
are valid topological sorts. This command uses **DFS post-order** because:

1. The graph is already materialized as a **nested parent→children structure**
   from `occurrences`; recursion over it is the natural fit and needs no
   in-degree bookkeeping or reverse-edge index.
2. It yields the leaves-first order **directly** (a Kahn's emit-order over
   parent→child edges would need reversing).
3. `emitted` gives O(V + E) and diamond-dedup for free; `in_progress` gives
   cycle detection for free — the same tri-color scheme a from-scratch DFS topo
   sort uses.

Kahn's algorithm would be the better choice if we needed **explicit cycle
reporting** (leftover nodes = the cycle) or **deterministic tie-breaking**
across independent branches. Neither is required here: Fusion guarantees
acyclicity, and branch order simply follows `occurrences` order.

---

## 8. Complexity summary

| Stage | Metric | Before | After hardening |
|---|---|---|---|
| Build (`traverse_assembly`) | time | O(V + E) (memoized) | O(V + E) |
| Sort (`sort_dag_bottom_up`) | time | O(paths) — worst case exponential | **O(V + E)** |
| Sort output | length | V + duplicates | **V (unique)** |
| Malformed cycle | behavior | `RecursionError` / hang | **logged + skipped** |
| Progress `docCount` | accuracy | inflated by duplicates | **exact** |

*V = distinct components, E = occurrence edges.*

---

## 9. Resume interaction

The bottom-up order is written into the checkpoint log as `doc_id|name` lines,
and each per-document checkpoint records `doc_id=…`. On the next run,
`_analyze_resume_state()` compares the freshly computed **document-id** order
with the logged one (`dag_matches`) and resumes from the document after the last
`SAVE_UPLOAD_COMPLETE` checkpoint via `list.index()` on the id list. Keying on
`doc_id` makes resume **rename-robust** (renaming a component no longer
invalidates the run) and unambiguous (ids are unique). A log produced by an
older name-keyed build simply fails the `dag_matches` equality and triggers a
safe full run — never an incorrect resume.

---

## 10. Hardening status

**Implemented — the document-id migration (`document_dag.py`).** Items 1 and 2
below have landed: the live path (`command_created` / `command_execute`) now
builds a **document-level DAG keyed by `dataFile.id`** via
`document_bottom_up_order()` and iterates real save units. Internal
sub-components fold into their owning document, multi-component documents
collapse to one node, `docCount` counts real save operations, and the graph is
collision-safe by construction (distinct documents sharing a component name stay
distinct). The resume log/checkpoints moved to `doc_id` in lockstep (§9). The
component-name functions (`traverse_assembly` / `sort_dag_bottom_up`) are
retained as the tested reference implementation and are removable once the id
path is verified inside Fusion.

> The migration was validated by `py_compile` and pure-logic tests only; the
> Fusion-entangled processing loop still needs an in-Fusion runtime pass. In
> particular, confirm `resolve_document`'s ownership resolution for
> referenced-but-not-open child documents on a real multi-level assembly.

1. **Key the graph by a stable identity, not `name`.** *(Done, as `dataFile.id`.)*
   Component names are not guaranteed unique across referenced external
   documents; the id-keyed graph removes the latent silent-skip. The one boundary
   to watch: any code path that still maps a name back to a component reintroduces
   the collision, so keep the loop on ids.
2. **Build a document-level DAG directly.** *(Done.)* Nodes keyed by
   `dataFile.id`, internal components folded into their owner, the runtime
   `saved` dedup now subsumed by the graph.

**Still open.**

3. **Iterative traversal for very deep assemblies.** Both sorts recurse to a
   depth equal to the assembly nesting depth. Real Fusion assemblies nest far
   below Python's ~1000-frame default limit, so this is low priority; an
   explicit-stack post-order removes the ceiling entirely if it ever matters.
4. **Explicit cycle *reporting*.** The guard prevents runaway recursion but only
   logs. If diagnosing a malformed reference graph ever becomes a need, switch
   this phase to Kahn's algorithm so the leftover (never-emitted) set *is* the
   cycle, and surface it to the user.
5. **Cache the order between `command_created` and `command_execute`.** The order
   is now computed twice per invocation (dialog preview, then execution), and the
   id-based build resolves `dataFile` per component — heavier than the old
   name-only walk. Memoizing the records for the active design across the two
   phases would remove the duplicate build.

---

## 11. Testing

Pure-logic coverage runs outside Fusion (fake component/occurrence objects; the
`PowerTools.*` scaffolding in `tests/conftest.py` where a module import is
needed):

- `tests/test_bottomupupdate_dag.py` — the component-name reference sort:
  children-before-parents, diamond-once, nested diamonds, cyclic-graph
  termination.
- `tests/test_bottomupupdate_document_dag.py` — the document-level DAG:
  multi-component collapse, doc-less internal fold, document diamond, same-named
  distinct documents stay distinct, cyclic-graph termination.
- `tests/test_bottomupupdate_resume.py` — the id-based resume/log parsing: order
  extraction on the `doc_id` column, checkpoint extraction, and the
  resume / full-run / version-mismatch / completed decisions.

The Fusion-entangled processing loop is not unit-testable outside Fusion and
requires a manual in-app verification pass (see §10).

---

## Sources

Background on the DAG / topological-sort patterns this engine implements:

- [Topological sorting — Wikipedia](https://en.wikipedia.org/wiki/Topological_sorting)
- [Kahn's Algorithm vs DFS Approach: A Comparative Analysis — GeeksforGeeks](https://www.geeksforgeeks.org/dsa/kahns-algorithm-vs-dfs-approach-a-comparative-analysis/)
- [Graph Topological Sort Patterns: Kahn's, DFS Post-Order, and Cycle Detection — techinterview](https://www.techinterview.org/post/3233465614/graph-topological-sort-patterns/)
- [Graph Topological Sorting — Build System Order Example — GyanBlog](https://www.gyanblog.com/coding-interview/graph-topological-sort-build-system-example/)
- [Resolving dependencies in a DAG with a topological sort — IPython Cookbook](https://ipython-books.github.io/143-resolving-dependencies-in-a-directed-acyclic-graph-with-a-topological-sort/)

---

*Copyright © 2026 IMA LLC. All rights reserved.*
