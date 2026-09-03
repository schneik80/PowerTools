---
paths:
  - "commands/*/resources/html/**"
---

# HTML palettes (assemblybuilder, assemblypalette, preferences, teamaddins)

- **`init.js` and `intent-icons.css` are generated** when a palette opens
  (git-ignored by glob). Never hand-edit or commit them; the Python side
  writes `window.__ptInit` (20efeea, 270047d).
- **Page -> Python** goes through `palette.incomingFromHTML` with a JSON
  action. **A raise inside that handler is swallowed** by DEBUG-gated
  `handle_error`, so the user sees "nothing happens". Guard every Fusion call
  (`cache_utils.resolve_target_folder`) and send an explicit error/banner back
  to the page (7535954).
- **Starting a Fusion command from a page event needs a later main-loop
  turn**: `threading.Timer` -> `app.fireCustomEvent` -> handler. Inline it and
  the command is torn down when the HTML event finishes (c440ad3).
- **Galleries ship metadata, not images.** Thumbnails are requested lazily
  (IntersectionObserver + batched requests) and resolved by a timer-fired
  polling event on the Python side (14f42ca).
- **Docs links** are built as `config.DOCS_BASE_URL + urlencode(doc)` from the
  registry's doc filename -- keep filenames in sync.
- **Preferences palette layout rules** (`preferences/resources/html/app.js`):
  - Nav = General + exactly one entry per registry group; anything a group or
    command owns renders **inside** that group's section via `groupExtras()`
    / `CMD_SECTIONS` inline flags, never as a second nav entry (00302fd,
    d5bfc76).
  - Subsections are `<div>`s, not nested `<section>`s -- the scroll-spy
    tracks every `<section>` (00302fd).
  - Commands that are only usable together are one checkbox via
    `settings_store.COMMAND_SETS`; the payload drops member rows and
    annotates the lead. Do not reintroduce per-row nesting in the page
    (6c554d5 replaced 039bcc2). The palette must never create a soft-lockout
    (2afdbe1).
  - No `title` tooltips on summaries (unthemed, unbounded) (d5bfc76).
  - Scrollbars: `-webkit-` pseudo-elements only; adding `scrollbar-width` or
    `scrollbar-color` makes Chromium ignore them (f104dcc).
  - Verify structural changes headlessly against the real registry (count
    nav entries == top-level sections, no duplicate labels) (00302fd).
- **Refresh a palette by pushing to the palette looked up by id**, never by
  calling the show/create path again -- that rebuilds the page and loses the
  active tab, scroll, filter and per-session state. Signature-compare first so
  a tab switch does not repaint identically.
- **`assemblypalette._diag` only reaches the Text Commands window.** Nothing it
  writes reaches `cache/powertools-debug.log`, so a crash takes the reasoning
  with it. Use `ptutil.log` for anything that must outlive the session.
- Command descriptions and doc text come from `docs/`, not invented; ASCII
  only (aa6802e).
