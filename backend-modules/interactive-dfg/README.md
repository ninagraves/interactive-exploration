# Interactive DFG

Interactive object-centric directly-follows graph for Ocelescope, without domain knowledge.

An [Ocelescope](https://www.ocelescope.org) backend module. It is a FastAPI app
that `ocelescope-backend` discovers through the `ocelescope_backend.modules`
entry point in `pyproject.toml` and serves under `/modules/interactiveDfg/v1`.

- `src/ocelescope_module_interactive_dfg/module.py`: module class `InteractiveDfg` (key `interactiveDfg`)
- `src/ocelescope_module_interactive_dfg/routes.py`: API routes
- `src/ocelescope_module_interactive_dfg/dfg/`: the graph, one module per step (see `docs/pages/interactive-dfg.md`)

Install it next to `ocelescope-backend` (e.g. as a uv workspace member of an
Ocelescope module project) and run `ocelescope-backend serve`.
