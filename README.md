# Interactive DFG

An [Ocelescope](https://www.ocelescope.org) module with an interactive object-centric directly-follows graph (DFG) for any object-centric event log (OCEL 2.0).
It needs no domain knowledge and no configuration: every object type and activity of the log is treated alike.
A second page, "Instances", lists every object with its lifecycle, activities and connectedness, and shows the traces and the object graph of selected objects.

- Backend module: `backend-modules/interactive-dfg` (Python package `ocelescope_module_interactive_dfg`, key `interactiveDfg`)
- Frontend module: `frontend-modules/interactive-dfg` (`@instance/interactive-dfg`)
- Documentation: `docs/` (start with `docs/README.md`); demo notebook `notebooks/interactive_dfg.ipynb`

## Run it locally

Requires [uv](https://docs.astral.sh/uv/), Node ≥ 20 and pnpm ≥ 11 (pnpm switches to the version pinned in `package.json`).

```bash
cp .env.example .env                 # once; backend config
cp app/.env.example app/.env.local   # once; frontend config (points to the backend on port 8003)
pnpm run sync                        # install backend + frontend, build the module
pnpm run dev                         # backend on http://localhost:8003, app on http://localhost:3003
```

Upload a log (e.g. `data/running_example/running_example.sqlite`) and open "Interactive DFG" or "Instances" in the sidebar.
Ports 8003/3003 are chosen so that other Ocelescope instances (e.g. on 8000/3000) can run alongside.
After changing backend routes, run `pnpm run build:modules` to regenerate the typed API client.
More in `docs/hosting/running-and-testing.md`.

This repo started from the Ocelescope instance template; its general documentation is in `docs/hosting/ocelescope-template.md`.
