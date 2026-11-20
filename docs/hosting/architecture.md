# Architecture

## Parts
- **Ocelescope instance** (this repo's root): the published `ocelescope-backend` host (Python, uv workspace) and the Next.js app in `app/` (pnpm workspace). Both come from the Ocelescope instance template.
- **Backend module** `backend-modules/interactive-dfg/`: a FastAPI app. `ocelescope-backend` discovers it through the entry point `ocelescope_backend.modules` in its `pyproject.toml` and serves it under `/modules/interactiveDfg/v1`.
  - `module.py`: module class `InteractiveDfg`.
  - `routes.py`: `GET /status` plus the routes of `dfg_routes.py` and `instance_routes.py`.
  - `dfg_routes.py`: `POST /{ocel_id}/dfg` and `POST /{ocel_id}/dfg/save`, with a small LRU cache (see below).
  - `dfg/`: the content, one module per step (documented in `docs/pages/interactive-dfg.md`).
  - `instance_routes.py`: `POST /{ocel_id}/instances/profile` (`/csv`, `/save`), `GET /{ocel_id}/instances/details`, `POST /{ocel_id}/instances/traces`, `POST /{ocel_id}/instances/object-graph`.
  - `instances/`: the content of the page "Instances" (documented in `docs/pages/instances.md`).
- **Frontend module** `frontend-modules/interactive-dfg/`: React (Mantine UI), registered in `app/ocelescope.config.ts`.
  - `src/index.ts`: module definition (two pages).
  - `src/routes/DirectlyFollowsGraph.tsx`: the page; `src/components/ModulePage.tsx` its frame (title, backend versions).
  - `src/components/DfgGraph.tsx` (drawing with React Flow), `DfgToolbar.tsx`, `DfgSettings.tsx` (sidebar), `DfgSave.tsx`.
  - `src/routes/Instances.tsx`: the page "Instances"; `src/components/ObjectProfileTable.tsx` (with `ProfileColumnFilter.tsx`, `ShortList.tsx`), `ObjectTracesChart.tsx`, `ObjectGraphChart.tsx`.
  - `src/lib/dfgLayout.ts` (ELK layout), `dfgArcs.ts` (arc steps in the browser), `dfgView.ts`, `palette.ts` (the only source of colours), `pageState.ts` (settings kept per log in the tab's sessionStorage), `useDebounced.ts`, `scheme.ts`.
  - `src/api/`: typed API client generated from the backend's OpenAPI schema by Orval (`pnpm run build:modules`); not committed.

## Data
- Ocelescope (≥ 0.13.0) keeps each OCEL as a DuckDB connection with flat tables (events, objects, e2o, …), readable as lazy polars frames (`.pl`). `dfg/graph.py`, `log_frames`, reads events, objects and e2o once per log version.
- No configuration and no module state: the page sends all its settings with every request.

## Cache
- `dfg_routes.py` keeps three LRU caches (`CACHE_SIZE` = 4 entries each): the log's frames, the traces of a set of object types, and the answers. Key: (log id, log version) (`log_version`: "original" or "view:<id>" of the active Ocelescope view, so a filter gives a fresh graph), plus the selected types or `request_key` (the request without the arc settings, which the page applies itself).
- `instance_routes.py` reuses `_cached` and `log_version` of `dfg_routes.py` for three more caches: the log's instance frames, the object profile and its filter options (key: log id, log version). Search, filters, sorting and paging run on the cached profile; traces and object graphs are computed per request.
- Thread-safe: a key is computed once at a time; a second request for it waits.
- Lost on a backend restart; nothing is written to disk.
