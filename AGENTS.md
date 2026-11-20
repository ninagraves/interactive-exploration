# Agent instructions

Read this before changing anything in this repository.

## What this is
An Ocelescope module (FastAPI backend + React frontend) with an interactive object-centric directly-follows graph for any OCEL.
It is the domain-free generalisation of the directly-follows graph page of the location-based OCPM module (repository location-based-ocpm).
The concept is defined by Nina Graves outside this repo (conceptualisation notes of the subproject "interactive_DFG"); the implementation follows it.

## Working rules
- Conceptualisation is Nina's: never add, change or reinterpret a content element (anything shown to the user: nodes, arcs, numbers, settings and their defaults) without her agreement. Propose first, build after approval.
- No domain knowledge: no handling units, movements, locations or other roles of object types or activities. Whatever needs such knowledge belongs in a domain module that reuses this one.
- Every content element is documented in `docs/pages/interactive-dfg.md` (see `docs/README.md` for what each entry must contain). Code and docs change together.
- The demo notebook `notebooks/interactive_dfg.ipynb` only imports and calls the package functions (never copies their code) and runs on the running example. Notebooks are committed without outputs (nbstripout, cell ids kept).
- General tool functionality (caching, storage, plumbing, build) is documented more briefly in `docs/hosting/`.
- Every Python function and every exported TypeScript function/component has a docstring.
- Code style: modular and generic; content logic in polars on the DuckDB-backed OCEL, never pandas. British English in code, comments and docs.
- The arc steps exist twice (Python `dfg/arcs.py`, `dfg/connectivity.py`; TypeScript `lib/dfgArcs.ts`); change both together (`tests/test_dfg_frontend.py` checks that they agree).
- Commits are made as Nina Graves <graves@pads.rwth-aachen.de>. Commits and pull requests contain no co-author or tool attribution lines.

## Where to look
- `docs/README.md`: documentation map and rules.
- `docs/pages/interactive-dfg.md`: the page, step by step, with code locations.
- `docs/hosting/architecture.md`, `docs/hosting/running-and-testing.md`, `docs/hosting/dependencies.md`.
