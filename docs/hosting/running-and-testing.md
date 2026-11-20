# Running and testing

## First setup
```bash
cp .env.example .env
cp app/.env.example app/.env.local
pnpm run sync          # uv sync (Python 3.13, .venv) + pnpm install + build the module
```

## Run
```bash
pnpm run dev           # backend http://localhost:8003 (auto-reload), app http://localhost:3003
```
- Ports: backend 8003 (`dev:backend` in `package.json`, `EXTERNAL_API_BASE_URL` in `app/.env.local`), app 3003 (`dev` in `app/package.json`).
- "Address already in use": run `lsof -ti :8003 | xargs kill` and start again.
- After changing backend routes or models: `pnpm run build:modules` (regenerates the typed API client).

## Test data
`data/running_example/running_example.sqlite` (upload it in the app). Any OCEL 2.0 log works.

## Tests
```bash
uv run pytest
```
Tests live in `backend-modules/interactive-dfg/tests/`: `test_dfg.py` (all steps; `test_worked_example_of_the_module_note` and `test_defaults_of_the_module_note` check the numbers of the module note), `test_dfg_export.py` (Save to session), `test_dfg_frontend.py` (Python and TypeScript arc steps agree; skipped without Node 22.6+).

## Notebooks
`notebooks/interactive_dfg.ipynb` imports the package from the workspace `.venv` (`ipykernel` is in the `dev` group).
Browser: `uv run --with jupyter jupyter lab notebooks/interactive_dfg.ipynb` from the repository root.
Outputs are never committed: install the nbstripout filter once per clone with `uv run nbstripout --install`.
