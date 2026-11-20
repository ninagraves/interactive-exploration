# Documentation

## Map
- `pages/interactive-dfg.md`: the page "Interactive DFG", one section per step and per setting.
- `hosting/`: general tool functionality (architecture, caching, running, testing, dependencies).

## Content documentation (detailed)
Goal: you can find, understand and edit the code of every content element from its doc.
For every content element (node, arc, number, setting) the doc states:
1. **What it shows.**
2. **How it is calculated**, referring to the concept definitions instead of restating them.
3. **Example** on the running example or the pallet example of the tests.
4. **Settings and defaults**, if any.
5. **Where it lives in the code**: file and function names.
6. **How to change it**: which function or parameter to edit, and what else then has to adapt.
7. **Alternatives** that were considered, and why they were not chosen.

## Hosting documentation (lighter)
Goal: another developer or coding agent can take over without further context.
Covers what exists, where it is, how to run and change it; no per-function detail beyond docstrings.

## Example logs
- `data/running_example/running_example.sqlite`: the running example of the location-based OCPM project (one slab, five coils, 17 events), a copy.
- The pallet example (ten pallets, a truck, an operator) is built in `tests/test_dfg.py` (`_pallet_example`); the module note's worked example uses it.
