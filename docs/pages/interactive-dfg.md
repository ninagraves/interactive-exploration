# Page "Interactive DFG"

Status: **suggestion** (2026-11-20), to be reviewed by Nina before it counts as conceptualised.
Concept: Nina's note `Interactive DFG.md` in `conceptualisation/` of the project folder `interactive-exploration/` (outside this repo): notation, running example, the eight steps, object-type-specific settings, defaults. User-facing description with worked examples: module note `Interactive DFG Module.md` (outside this repo). The tests `test_general_example_of_the_concept_note`, `test_type_specific_example_of_the_concept_note` and `test_defaults_of_the_module_note` check the numbers of both notes.

The page needs no configuration and no domain knowledge: every object type and every activity of the log is treated alike. It computes the graph on the first request for a log (then cached, `dfg_routes.py`).

## Steps
1. **Traces** (`dfg/traces.py`): `considered_objects(objects, object_types)` (all objects of the types), `object_traces(e2o, events, objects)`: one row per (object, event), sorted by object, time, activity, event id; an object linked to an event twice counts once. Example (`test_ties_follow_the_activity_name_and_duplicate_links_count_once`): pack and move of p1 share 2:00, so the trace is pick, move, pack, ship.
2. **Activity projection** (`dfg/projection.py`): `type_activity_counts` (events per type and activity, most first, ties by first occurrence, then name), `default_activity_count` (40 % rounded up, at least 3, at most 10, all if fewer), `default_activities`, `project_traces` (events of deselected activities are removed, positions renumbered). `selected_type_event_counts`: the number in brackets in the activity list.
3. **Variants** (`dfg/variants.py`): `object_variants`, `variant_ranking` (objects, first occurrence, variant), `kept_variants` / `variant_filter` (kept while the variants before cover less than π % of the objects), `activity_variant_thresholds` and `added_activity_thresholds` (values of the activity list).
4. **Arcs** (`dfg/arcs.py`): `directly_follows_arcs` (with start and end arcs, traversals, objects, first occurrence), `arc_order`, `arc_share_filter` (Arcs (projection)), `arc_count_filter` (Arcs (display), per type or with `total` in general mode).
5. **Stay connected** (`dfg/connectivity.py`): `on_start_end_paths`, `stay_connected` (networkx).
6. **Nodes** (`dfg/nodes.py`): `shown_activities`, `activity_frequencies`, `involved_object_types` (the circles).
7. **Graph** (`dfg/graph.py`): `log_frames(ocel)`, `type_overview`, `default_selection(objects, n=5)`, `resolve_selection(request, objects)`, `selected_traces`, `included_traces` (steps 1 to 3), `unselected_type_thresholds` (third part of the activity list), `directly_follows_graph(frames, selection, traces, activities, stay, arc_total)`; defaults `DEFAULT_OBJECT_TYPES` (5), `DEFAULT_VARIANT_THRESHOLD` (80), `DEFAULT_ARC_THRESHOLD` (50), `DEFAULT_STAY_CONNECTED` (True).
8. **Save to session** (`dfg/export.py`): `dfg_resource(arcs)` (Ocelescope's DFG resource), `kept_event_ids`, `filtered_log`.

The route (`dfg_routes.py`, `POST /{ocel_id}/dfg`, body `DfgRequest`) runs steps 1 to 3 and answers with **all** arcs of the included traces; the page applies steps 4 and 5 in the browser (`lib/dfgArcs.ts`, `filterArcs`), so that the arc sliders react without a request.

## Settings (toolbar, then the sidebar "Discovery Settings")
| Setting | Default | Code |
|---|---|---|
| Arc labels (traversals / objects), direction, Compact, Reset, settings button | traversals, left to right, off | `DfgToolbar.tsx`, `DfgState` in `DfgSettings.tsx` |
| Arcs (display): general (all types together) or per type, − / +, slider | all, general | `DisplayArcs` in `DfgToolbar.tsx`, `arcCountFilter` in `lib/dfgArcs.ts` |
| Variants (general, own per type) | 80 % | `PercentSlider`, `toRequest` |
| Arcs (projection) (general, own per type) | 50 % | `arcSettings`, `arcShareFilter` |
| Stay connected | on | `stayConnected` in `lib/dfgArcs.ts` |
| Object types (searchable list, own values in the unfold) | the 5 types with the most objects | `TypeRow`; `pendingSelection` (`lib/dfgView.ts`, `DEFAULT_OBJECT_TYPES`) |
| Activities (searchable list, per type in the unfold; double click on a node deselects it) | per type 40 % of its activities, 3 to 10 | `ActivityRow`, `deselectActivity` |
| Save to session (model / log, projected / displayed) | model, displayed | `DfgSave.tsx` |

The graph waits 2 s after the last change (`RECALCULATION_DELAY_MS` in `routes/DirectlyFollowsGraph.tsx`); "Update now" skips the wait. Settings are kept per log in the tab (`usePageState`, key `dfg.v1.<log id>`).

## How to change
- Number of default object types: `DEFAULT_OBJECT_TYPES` in `dfg/graph.py` **and** `lib/dfgView.ts` (also the number of emphasised colours).
- Other default activities: constants in `dfg/projection.py`; sharing defaults between selected types: pass `shared_from=list(settings)` to `default_activities` in `graph.included_traces` and `graph.unselected_type_thresholds`.
- Other tie order of traces: the sort in `traces.object_traces`.
- Other variant filter or arc ranking: `variants.kept_variants`, `arcs.arc_order`, `arcs.arc_share_filter`; change `lib/dfgArcs.ts` along (`test_dfg_frontend.py`).
- Other defaults of the sliders: `dfg/graph.py` **and** `DEFAULT_STATE` in `DfgSettings.tsx`.
- Look: `SIZES`, `ELK_OPTIONS`, `COMPACT_OPTIONS` in `lib/dfgLayout.ts`; colours in `lib/palette.ts` (`emphasisColourMap`).

## Alternatives considered
- **Default object types by number of events** instead of objects: an object type with few objects but many events (e.g. a single truck) would be selected before types with many objects; "top 5" means "most objects" (Nina, 2026-11-20).
- **Tie-break by e2o qualifiers** (e.g. "creates"/"consumes") instead of the activity name: needs knowledge about qualifiers that a generic log does not guarantee; open point of the concept.
- **Sharing default activities between all selected types**: with five default types the defaults of one type would spread to all others; each type keeps its own.
- **Removing arcs by hand** (double click on an arc): removed on 2026-11-20 (Nina); every shown arc follows from the settings of the view.
