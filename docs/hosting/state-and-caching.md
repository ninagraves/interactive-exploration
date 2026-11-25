# State and caching

## Where state lives
- Backend: no module state. The pages send all their settings with every request; the backend only caches answers (`docs/hosting/architecture.md`, section "Cache").
- Frontend: what each page looks like, kept in the browser tab (section "Page state" below).

## Page state
Every page opens again as it was left: switching to the other page of the module (or to another Ocelescope page) and back shows the same settings, selections, searches, picked chips, unfolded rows, graph (layout, dragged nodes, zoom and pan) and scroll position.
Ocelescope unmounts a page when another one opens, so nothing stays in the React tree; what a page needs is kept outside it, in the browser tab, per log (the log id is part of every key).

| What | Where | Survives a reload? |
|---|---|---|
| Settings, selections, searches, picked chips, table state, unfolded rows, the choices of "Save to session" | `usePageState(key, initial)` (`lib/pageState.ts`): like `useState`, shared by all components using the key, in memory and in the tab's sessionStorage (JSON) | yes |
| Values that are not JSON | `useMemoryState(key, initial)` (`lib/pageState.ts`), memory only | no |
| Layout (ELK) of the DFG, dragged node positions, zoom and pan | `keep`/`recall` (`lib/pageState.ts`) in `DfgGraph`, `useKeptViewport` (`lib/keptView.ts`), memory only (layouts hold maps) | no: the graph is laid out and fitted again |
| Scroll position of the page and of the DFG sidebar and its lists | `useKeptScroll` (in `ModulePage`), `useKeptScrollOf` (`lib/keptView.ts`), memory and sessionStorage | yes |
| Answers of the backend's requests | React Query's cache in Ocelescope's query client; the module keeps its own answers `KEEP_ANSWERS_MS` (30 min) after no page shows them instead of React Query's 5 min (`useKeptAnswers` in `ModulePage`, `lib/queries.ts`) | no |

Keys used by the pages (all with the log id, except settings that hold for every log):
- DFG: `dfg.v1.<log>` (settings), `dfg.sidebar` (width, hidden), `dfg.height`, `dfg.sidebar.<log>.*` (searches, picked chips, unfolded rows, scroll positions), `dfg.save.*.<log>`, `dfg.view.<log>.*` (layout, dragged nodes, zoom and pan).
- Instances: `instances.*.<log>` (selection, table, chart settings), `profile.search.*`.
- Both: `scroll.<log>.<page title>`.

The sessionStorage keys carry the prefix `interactiveDfg.`, so they do not collide with Ocelescope's or other modules' keys.

**No stale state.**
- A kept layout is only used for the same inputs (`sameInputs`: identical, or equal maps or JSON), i.e. the same graph and the same look settings (direction, arc labels, Compact); otherwise the graph is laid out and fitted again and the new layout is kept instead. Dragged positions and zoom and pan belong to one layout (its ELK generation) and are dropped with it.
- Answers: React Query refetches a page's requests when the page opens, so a kept answer is shown at once and replaced if the log changed since (e.g. an Ocelescope filter, i.e. a new view).
- A picked object type chip that is no longer in the log is ignored.

**Changing it.**
- Keep a new piece of a page: replace its `useState` by `usePageState` with a key containing the log id (or `useMemoryState` for values that are not JSON).
- Keep answers longer or shorter: `KEEP_ANSWERS_MS` in `lib/queries.ts` (the tab's memory grows with every distinct request kept). Which queries count as the module's: `isModuleQuery` (keys starting with `"interactiveDfg"` or URLs containing `/interactiveDfg/v1/`).
- Keep layouts across reloads: they would have to be JSON (positions only) and stored with a content hash of their inputs; not done, since ELK recomputes them in well under a second for typical graphs.
- Not kept: zoom of the Plotly charts (they reset on every redraw, also without a page switch), open menus and popovers, the save messages.
