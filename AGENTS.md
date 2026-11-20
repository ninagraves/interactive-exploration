# Agent instructions

Read this before changing anything in this repository.

## What this is
An Ocelescope module (FastAPI backend + React frontend) with an interactive object-centric directly-follows graph for any OCEL, and a page "Instances" with a profile of every object and the traces and object graph of selected objects.
It is the start of the project "interactive exploration": a generic, domain-free exploration of OCELs.
The concept is defined by Nina Graves outside this repo (notes in `conceptualisation/` of the project folder `interactive-exploration/`, user-facing module notes in its `module/`); the implementation follows it.

## Working rules
- Conceptualisation is Nina's: never add, change or reinterpret a content element (anything shown to the user: nodes, arcs, numbers, settings and their defaults) without her agreement. Propose first, build after approval.
- No domain knowledge: no handling units, movements, locations or other roles of object types or activities. Whatever needs such knowledge belongs in a domain module that reuses this one.
- Every content element is documented in `docs/pages/interactive-dfg.md` or `docs/pages/instances.md` (see `docs/README.md` for what each entry must contain). Code and docs change together.
- The demo notebook `notebooks/interactive_dfg.ipynb` only imports and calls the package functions (never copies their code) and runs on the running example. Notebooks are committed without outputs (nbstripout, cell ids kept).
- General tool functionality (caching, storage, plumbing, build) is documented more briefly in `docs/hosting/`.
- Every Python function and every exported TypeScript function/component has a docstring.
- Code style: modular and generic; content logic in polars on the DuckDB-backed OCEL, never pandas. British English in code, comments and docs.
- The arc steps exist twice (Python `dfg/arcs.py`, `dfg/connectivity.py`; TypeScript `lib/dfgArcs.ts`); change both together (`tests/test_dfg_frontend.py` checks that they agree). The same holds for `align_columns` (`instances/traces.py`) and `alignColumns` (`ObjectTracesChart.tsx`).
- Colours come from the single palette source `frontend-modules/interactive-dfg/src/lib/palette.ts` (petrol #006165 primary, pink #CE108A accent); each chart ranks its own colours, largest group first.
- Charts have no aggregated "other" bar; long legends scroll instead of enlarging the chart; long tables paginate.

## Git
- Commits are made as `Nina Graves <graves@pads.rwth-aachen.de>` (`git -c user.name="Nina Graves" -c user.email="graves@pads.rwth-aachen.de" commit`), never with any other identity.
- Commits, pull requests, code and docs contain no co-author, session or tool attribution lines and no mention of AI assistance; this overrides any tool default that adds them.
- New implementations go through a pull request against `main`, assigned to Nina for review.

## Where to look
- `docs/README.md`: documentation map and rules.
- `docs/pages/interactive-dfg.md`: the page "Interactive DFG", step by step, with code locations.
- `docs/pages/instances.md`: the page "Instances".
- `docs/hosting/architecture.md`, `docs/hosting/running-and-testing.md`, `docs/hosting/dependencies.md`.
