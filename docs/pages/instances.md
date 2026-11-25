# Page "Instances"

Status: **suggestion** (2026-11-20), to be reviewed by Nina before it counts as conceptualised.
Concept: Nina's note `Instances (draft).md` in `conceptualisation/` of the project folder `interactive-exploration/` (outside this repo): notation, columns with definitions and examples, traces, object graph, open points. User-facing description with a worked example: module note `Instances Page.md` (outside this repo). `tests/test_instances.py` checks the numbers of the concept note on the pallet example.

The page shows every object of the log on the instance level: the **object profile** (one row per object), and for the objects selected in it their **object traces** and their **object graph**.
Every object is treated alike: there is no distinction between kinds of objects, so every function applies to every object (any object can be selected, in the table or by a double click in the charts).

Backend: `instances/` (content), `instance_routes.py` (routes, caches). Frontend: `routes/Instances.tsx` (page, selection bar), `components/ObjectProfileTable.tsx`, `ProfileColumnFilter.tsx`, `ObjectTracesChart.tsx`, `ObjectGraphChart.tsx`. The page opens again as it was left, scroll position included (`ModulePage`; `docs/hosting/state-and-caching.md`, section "Page state").

## Tables (`instances/frames.py`)
`instance_frames(ocel)` reads the log once per log version (cached in `instance_routes._instance_frames`): `InstanceFrames` with `e2o` (event, object; unique pairs, so an object linked to an event with two qualifiers counts once), `o2o` (source, target, qualifier), `objects` (object, object_type; also objects without events) and `events` (event, time, activity).

## Object profile (`instances/profile.py`)
**What it shows.** One row per object: id, object type and three column groups.

| Group | Column | Code column | Definition (concept section 3) | p6 |
|---|---|---|---|---|
| Lifecycle | Events | `n_events` | number of events of the object | 6 |
| Lifecycle | Timestamps | `n_timestamps` | distinct timestamps of its events | 6 |
| Lifecycle | First, Last | `first`, `last` | first and last timestamp | hour 50, 55 |
| Lifecycle | Lifespan | `lifespan` (seconds) | last − first | 5 h |
| Activities | First activity, Last activity | `first_activity`, `last_activity` | activity of the first / last event of the trace | produce, ship |
| Activities | Activities | `n_activities` | distinct activities | 6 |
| Connectedness | Shared events | `n_shared_events` | its events that involve at least one other object | 3 |
| Connectedness | Linked objects | `n_linked` | other objects that share at least one event with it | 2 |

**How it is calculated.**
1. `ordered_traces(frames, objects=None)`: one row per (object, event), sorted by object, time, activity name, event id, with `pos` (1-based). This is the trace order of the page "Interactive DFG", so first and last activity agree with its start and end arcs.
2. `lifecycle(traces)`: events, timestamps, first, last, lifespan.
3. `activity_profile(traces)`: first and last activity, distinct activities.
4. `connectedness(frames)`: per event its number of objects; shared events = events with more than one; linked objects = distinct other objects of its events.
5. `object_profile(frames)`: all objects (left join, so objects without events get 0 and no timestamps or activities).

**Example** (`test_profile_of_the_concept_note`): p9 has 4 events at 2 timestamps; "inspect" < "produce" at its first timestamp, so its first activity is inspect. t1 has 18 events, all shared, and 9 linked objects (the pallets it loaded and shipped).

**Table functions.**
- Search (`search_text`, `query_rows`): id, object type, first and last activity, case-insensitive.
- Filter per column (`ColumnFilter`, `filter_expression`; options from `column_info`): checkboxes for string columns with at most `MAX_CATEGORIES` (100) values, otherwise a text field; a range for counts, lifespan (typed in hours) and timestamps.
- Sorting by every column (`sort_rows`; nulls last, ties by object id), paging (`query_profile`).
- Hiding a column group (frontend only, chips "Columns").
- Unfolded row (`object_details`, route `GET /instances/details`): first and last event (id, activity, time), activities with their number of events, linked objects with their object type and the events they share (a click adds the object to the selection).
- Export (`export_frame`): CSV (`POST /instances/profile/csv`) or saved to the session as an Ocelescope `OCELMapping` (`POST /instances/profile/save`; one value per object). Both take the rows matching search and filters, in the current order, with the shown columns.

**How to change it.** A new column: add it in `object_profile` (or a step function), in `SORTABLE`/`FILTERABLE`, in `ProfileColumn` and `ProfileRow` (`instance_routes.py`), then rebuild the API client (`pnpm run build`) and add a `ColumnSpec` in `COLUMNS` (`ObjectProfileTable.tsx`).

**Alternatives** (concept section 5, open for Nina): linked objects could also count o2o-related objects, or be split per object type; further columns (share of shared events, o2o relations, attributes) are not added without agreement.

## Selection
Ticked rows, links in unfolded rows and double clicks in the charts change one selection per log (`usePageState("instances.selected.<ocel>")`). `SelectionBar` (`routes/Instances.tsx`) lists it as removable pills and sticks to the top of the window.

## Object traces (`instances/traces.py`, `ObjectTracesChart.tsx`)
**What it shows.** One row per selected object (at most `MAX_TRACES` = 50, the first ones of the selection), its events as chevrons in trace order with event id and activity. On every chevron one small circle per other object of the event, in the colour of its object type; the circle of a selected object has a thick border. Hovering a chevron lists the event, its timestamp, its position and its objects.

**How it is calculated.** `object_traces(frames, selected)`: `ordered_traces` of the selected objects, `involved_objects` (objects of these events with their type), joined; the row's own object is left out of its events; `selected` marks the selected objects. Route `POST /instances/traces`.

**Example** (`test_traces_of_p6_and_t1`): p6 and t1 selected. Row p6: produce, pick, inspect (circle o1), pack, load and ship (circle t1, thick border).

**Double click.** On a circle: selects its object, or unselects it if it is selected. On the name of a row: unselects it.

**Option "Align shared events"** (default off): every event gets one column, the same in every row (`alignColumns` in the frontend, `align_columns` in the backend, same algorithm): the longest chain of events before it over all rows. Example: with p6 and t1, p6's load e030 is t1's 11th event, so it moves to column 10 and ship to 11.

## Object graph (`instances/object_graph.py`, `ObjectGraphChart.tsx`)
**What it shows.** Nodes: the selected objects (thick border) and the related objects (one hop, by a shared event or an o2o relation). Solid lines: shared events, labelled with their ids (thicker = more events). Dashed arrows: o2o relations with their qualifier. Laid out with ELK (stress), drawn with React Flow; nodes can be dragged.

**How it is calculated.** `related_objects`, `graph_nodes` (with `n_events` and `n_shared`), `event_arcs` (one per pair of shown objects with shared events), `o2o_arcs`, `focal_events` (for "Events as boxes"), `object_graph(frames, selected, max_nodes=MAX_OBJECT_NODES)` (500; related objects with the most shared events first). Route `POST /instances/object-graph`. Settings act in the browser (`visibleGraph`).

**Example** (`test_object_graph_of_p6`): S = {p6}: nodes p6, t1, o1; arcs p6–o1 (e028) and p6–t1 (e030, e031); no arc t1–o1.

**Settings** (`ObjectGraphSettings`, defaults `DEFAULT_OBJECT_GRAPH`): one chip per object type of the related objects (all on), shared events (on), o2o relations (on), arcs between related objects (on), labels (on), events as boxes (off).

**Double click** on the name of any object: selects or unselects it (the rest of the box drags the node).

## Colours
Object types get the colours of the page "Interactive DFG" (`emphasisColourMap`: signature colours for the `DEFAULT_OBJECT_TYPES` types with the most objects, paler colours for the others), taken from the object type filter options of the profile, so a type has the same colour on both pages.
