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
| Activities (searchable list by name and by object type chips, per type in the unfold; double click on a node deselects it) | per type 40 % of its activities, 3 to 10 | `ActivityRow`, `deselectActivity`; search: `lib/dfgActivitySearch.ts` |
| Save to session (model / log, projected / displayed) | model, displayed | `DfgSave.tsx` |
| Download (PDF, SVG, HTML, PNG; With legend), button at the top right of the graph | with legend | `DownloadMenu` in `DfgGraph.tsx`, `lib/dfgDrawing.ts`, `lib/dfgDownload.ts` |

The graph waits 2 s after the last change (`RECALCULATION_DELAY_MS` in `routes/DirectlyFollowsGraph.tsx`); "Update now" skips the wait. Settings are kept per log in the tab (`usePageState`, key `dfg.v1.<log id>`). The whole page stays as it was left when switching pages: searches, picked chips, unfolded rows, scroll positions, the layout with dragged nodes, zoom and pan (`stateKey` of `DfgSettings` and `DfgGraph`; `docs/hosting/state-and-caching.md`, section "Page state").

## Activity search
`lib/dfgActivitySearch.ts`, used by `DfgSettings` (`components/DfgSettings.tsx`). The search box above the activity list ("Search activities or object types") does two things:
- **By name**: the list keeps the activities whose name contains the text (`activityMatches`, case-insensitive). "Select all (n)" selects every activity found for every selected object type with events of it.
- **Object type chips**: below the box, "List by:" offers the object types whose name contains the text (`matchingObjectTypes`), in the order of the type list (most objects first), at most 6 (`TYPE_HITS_SHOWN`; more: "+n more types, type more letters"). Below 4 letters (`CHIP_QUERY_MIN_LENGTH`) only a type whose full name is the text is offered, since fewer letters are not selective enough. Example (running example): "coil" offers coil, "coi" nothing, "slab" slab.
- **Picked chips**: clicking a chip clears the text and lists every activity the type is involved in, most of the type's events first (`activitiesOf`, `rankedBy`), in one list without the three parts; activities not in the graph keep their value on the right. Chips stack: a further chip keeps only the activities that all picked types are involved in. The number in brackets is then `chipCount`: the events of the activity with an object of the type; with two or more types the smallest of their numbers (the route has no number of events shared by several types, and at most that many events can involve all of them). Ties: events with an object of a selected type, then events in the log, then name. The search text narrows the list further; a chip's × removes it, the × above them goes back to all activities.
- Example (running example): coil lists crane move (4), quality check (4), load truck (2), unload truck (2), cut (1), label (1), roll (1); coil + slab lists roll (1).
- Test: `test_activity_search_chips_list_the_activities_of_all_picked_types` in `tests/test_dfg_frontend.py` runs the TypeScript functions with Node on the route's activity list and compares them with a Python sort.

## Download
`DownloadMenu` in `components/DfgGraph.tsx`, `lib/dfgDrawing.ts`, `lib/dfgDownload.ts`. A button at the top right of the graph opens a menu with **PDF (vector)**, **SVG (vector)**, **HTML (interactive)** and **PNG (image)**, and the checkbox **With legend** (on by default; kept while the page is open). The file shows the whole graph as drawn (dragged nodes included), whatever part is zoomed in on; zoom controls and the button are left out. File name: `dfg_<log name>_<date>.<ext>` (`exportFileName`; the log's name from Ocelescope's OCEL endpoint, `lib/logName.ts`), e.g. `dfg_running_example_2026-11-24.pdf`.
- **How**: the graph is not photographed from the page but drawn again from the current layout as plain shapes (`graphScene`: rounded rectangles, circles, Bézier paths, texts at their baselines), following the page's node layout (`activityGroup`, `terminalGroup`, `arcGroup`; the arc line ends under an arrow triangle, `arrowHead`). The same scene is written as SVG (`sceneSvg`), PDF (`scenePdf`, jsPDF drawing commands), PNG (`scenePng`, the SVG drawn on a canvas) and HTML (`sceneHtml`).
- **Colours**: always light (white background, dark text), whatever the page's colour scheme, with the light-scheme colours of the object types (`exportColours` from `routes/DirectlyFollowsGraph.tsx`); start and end arcs grey (`arcColour`); transparent colours (the paler object types, `FADED_ALPHA`) are blended onto white (`solid`), because PDF drawing commands have no transparency.
- **Legend** (`legendGroups`), below the graph, wrapped to the graph's width (at least 360 px): "Object types:" with every type in the drawing, selected types first (a short line with an arrow in its colour), then the unselected ones that appear as circles (a circle in its colour); then a grey key: ▶ / ■ in a circle (start / end of an object type; grey arcs from a start / to an end), "number in an activity: its events", "number on an arc: traversals" (or objects, with the Objects arc labels), "thicker arc: more traversals". Hovering a legend entry (SVG, HTML) explains it.
- **Hover texts** (`activityHover`, `arcHover`, circle and start / end texts): the same numbers as on the page, without the hints on mouse actions. SVG: `<title>` elements (a browser shows them as tooltips); HTML: `data-hover` attributes and an own tooltip (name in bold); PDF and PNG: none.
- **PDF**: one page of the drawing's size (1 px = 0.75 pt); texts in Helvetica / Helvetica Bold (standard PDF fonts, not embedded); a text more than 3 px wider in Helvetica than on the page is set slightly smaller so that it stays in its box. Characters outside Latin-1 (e.g. Greek letters, arrows) cannot be shown by these fonts; use the SVG there. Publishers that require embedded fonts: convert the SVG with Inkscape instead.
- **SVG**: plain SVG 1.1 (no HTML inside), so Inkscape, Illustrator and LaTeX (via Inkscape or `rsvg-convert`) show it as well; font: the page's font (`font-family` of the page).
- **HTML**: one file without external resources; the SVG fills the window; mouse wheel or + / − zoom (around the pointer, up to 200 ×), dragging pans, Fit shows everything.
- **PNG**: up to 4 pixels per screen pixel, at most 16,000 pixels per side and 120 million pixels (`PNG_LIMITS`, `pngScale`; browser canvas limits).
- Example (running example, default settings, with legend): a PDF page of 802.5 × 315.75 pt.
- Test: `tests/test_dfg_image.py` lays out the running example with `layoutGraph` and checks the scene's SVG (every node, arc, arrow head and label, inside the image) and that the PDF holds no embedded image.

## How to change
- Number of default object types: `DEFAULT_OBJECT_TYPES` in `dfg/graph.py` **and** `lib/dfgView.ts` (also the number of emphasised colours).
- Other default activities: constants in `dfg/projection.py`; sharing defaults between selected types: pass `shared_from=list(settings)` to `default_activities` in `graph.included_traces` and `graph.unselected_type_thresholds`.
- Other tie order of traces: the sort in `traces.object_traces`.
- Other variant filter or arc ranking: `variants.kept_variants`, `arcs.arc_order`, `arcs.arc_share_filter`; change `lib/dfgArcs.ts` along (`test_dfg_frontend.py`).
- Other defaults of the sliders: `dfg/graph.py` **and** `DEFAULT_STATE` in `DfgSettings.tsx`.
- Look: `SIZES`, `ELK_OPTIONS`, `COMPACT_OPTIONS` in `lib/dfgLayout.ts`; colours in `lib/palette.ts` (`emphasisColourMap`).
- Activity search: number of chips shown `TYPE_HITS_SHOWN` (`DfgSettings.tsx`), letters needed for a part of a name `CHIP_QUERY_MIN_LENGTH`, ranking `rankedBy`, count of stacked chips `chipCount` (`lib/dfgActivitySearch.ts`; change `test_dfg_frontend.py` along).
- Downloads: colours `EXPORT_COLOURS`, margin `MARGIN`, arrow `ARROW`, legend texts in `legendGroups` (`lib/dfgDrawing.ts`); formats and labels `IMAGE_FORMATS`, PNG size `PNG_LIMITS`, file name `exportFileName`, the interactive page's look and script in `sceneHtml` / `PAGE_SCRIPT` (`lib/dfgDownload.ts`). A change of the page's node drawing (`ActivityNode`, `TerminalNode`, `ArcEdge` in `DfgGraph.tsx`) needs the same change in `activityGroup`, `terminalGroup`, `arcGroup`. A dark export: replace `EXPORT_COLOURS` and pass the page's `colours` instead of `exportColours`. Embedded fonts in the PDF: register a TTF with jsPDF's `addFileToVFS` / `addFont` and use it in `pdfShape`.

## Alternatives considered
- **Default object types by number of events** instead of objects: an object type with few objects but many events (e.g. a single truck) would be selected before types with many objects; "top 5" means "most objects" (Nina, 2026-11-20).
- **Tie-break by e2o qualifiers** (e.g. "creates"/"consumes") instead of the activity name: needs knowledge about qualifiers that a generic log does not guarantee; open point of the concept.
- **Sharing default activities between all selected types**: with five default types the defaults of one type would spread to all others; each type keeps its own.
- **Download as a screenshot of the page** (html-to-image of React Flow's viewport, as Ocelescope's own graph viewer does): its SVG wraps the nodes as HTML in a `foreignObject`, which Inkscape and LaTeX do not show, and its PDF holds a PNG of at most 2048 px; the redrawn vector scene avoids both.
- **PDF via svg2pdf.js** (converting the SVG): one more dependency; jsPDF's own drawing commands suffice for the few shapes of the scene.
- **Stacked chips counted by shared events**: the number of events that involve objects of all picked types would be exact, but the route sends only events per (activity, type); the smallest of them is an upper bound and needs no backend change.
- **Removing arcs by hand** (double click on an arc): removed on 2026-11-20 (Nina); every shown arc follows from the settings of the view.
