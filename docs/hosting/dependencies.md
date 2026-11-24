# Dependencies

- Python 3.13 (`.python-version`), managed with uv; Node 24 (`.nvmrc`), pnpm 11 (pinned in `package.json`).
- `ocelescope-backend` and `ocelescope-module-ocel` ≥ 0.13.0 (`pyproject.toml`). The `ocelescope` library brings DuckDB and polars; `networkx` (Stay connected) is listed in the module's `pyproject.toml`.
- Frontend packages use `catalog:` versions from `@ocelescope/pnpm-plugin-catalog`, so they follow the Ocelescope release; `@xyflow/react` (drawing), `elkjs` (layout) and `mantine-datatable` (object profile table) are in that catalog.
- `jspdf` (vector PDF of the DFG download, `lib/dfgDownload.ts`) is not in that catalog: a direct dependency of `frontend-modules/interactive-dfg` (`^4.2.1`, the version Ocelescope's own packages use).
- `pnpm-workspace.yaml` waits a day before installing newly published npm packages, except `@ocelescope/*`.
