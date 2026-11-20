"""Tests of the page "Instances": object profile, object traces and object graph.

The numbers are those of the concept note "Instances (draft)" (running example: ten pallets, a truck, an operator).
"""

import polars as pl
from test_dfg import _pallet_example

from ocelescope_module_interactive_dfg.instances.frames import InstanceFrames
from ocelescope_module_interactive_dfg.instances.object_graph import object_graph
from ocelescope_module_interactive_dfg.instances.profile import (
    ColumnFilter,
    column_info,
    object_details,
    object_profile,
    query_profile,
)
from ocelescope_module_interactive_dfg.instances.traces import align_columns, object_traces


def _frames() -> InstanceFrames:
    """The running example as instance frames (no o2o relations), plus an object without events (x1)."""
    log = _pallet_example()
    return InstanceFrames(
        e2o=log.e2o.select("event", "object"),
        o2o=pl.DataFrame(
            {"source": ["p1"], "target": ["t1"], "qualifier": ["carried by"]},
        ),
        objects=pl.concat([log.objects, pl.DataFrame({"object": ["x1"], "object_type": ["pallet"]})]),
        events=log.events,
    )


def test_profile_of_the_concept_note():
    """The table "More examples" and the p6 column of the concept note."""
    profile = object_profile(_frames())
    rows = {r["object"]: r for r in profile.to_dicts()}
    expected = {
        # object: events, timestamps, lifespan (h), first activity, last activity, activities, shared, linked
        "p1": (5, 5, 4, "produce", "ship", 5, 2, 1),
        "p6": (6, 6, 5, "produce", "ship", 6, 3, 2),
        "p9": (4, 2, 1, "inspect", "scrap", 3, 2, 1),
        "p10": (7, 7, 6, "produce", "ship", 6, 3, 2),
        "t1": (18, 18, 93, "load", "ship", 2, 18, 9),
        "o1": (6, 6, 41, "inspect", "inspect", 1, 6, 5),
    }
    for obj, values in expected.items():
        r = rows[obj]
        got = (
            r["n_events"],
            r["n_timestamps"],
            r["lifespan"] / 3600,
            r["first_activity"],
            r["last_activity"],
            r["n_activities"],
            r["n_shared_events"],
            r["n_linked"],
        )
        assert got == values, obj
    empty = rows["x1"]
    assert (empty["n_events"], empty["n_activities"], empty["n_shared_events"], empty["n_linked"]) == (0, 0, 0, 0)
    assert empty["first"] is None and empty["first_activity"] is None and empty["lifespan"] is None


def test_query_sorts_filters_and_pages():
    """Sorting by events descending, a range filter on linked objects and paging."""
    profile = object_profile(_frames())
    page, total = query_profile(profile, sort_by="n_events", descending=True, limit=2)
    assert total == 13 and page["object"].to_list() == ["t1", "p10"]
    page, total = query_profile(profile, filters=[ColumnFilter(column="n_linked", min=2)])
    assert sorted(page["object"].to_list()) == ["o1", "p10", "p6", "p7", "p8", "t1"] and total == 6
    page, total = query_profile(profile, search="operator")
    assert page["object"].to_list() == ["o1"]
    kinds = {i["column"]: i["kind"] for i in column_info(profile)}
    assert kinds["object"] == "text" and kinds["object_type"] == "category" and kinds["first"] == "time"


def test_details_of_p6():
    """The unfolded row of p6."""
    details = object_details(_frames(), "p6")
    assert details["first_event"]["event"] == "e026" and details["last_event"]["event"] == "e031"
    assert [(a["activity"], a["count"]) for a in details["activities"]][:2] == [("inspect", 1), ("load", 1)]
    assert [(lnk["object"], lnk["events"]) for lnk in details["linked"]] == [("t1", ["e030", "e031"]), ("o1", ["e028"])]


def test_traces_of_p6_and_t1():
    """Section 4.1: p6's chevrons with their circles, wide border for t1; aligned columns."""
    traces = object_traces(_frames(), ["p6", "t1"])
    assert traces.totals["n_events"].to_list() == [6, 18]
    p6 = traces.events.filter(pl.col("object") == "p6")
    assert p6["activity"].to_list() == ["produce", "pick", "inspect", "pack", "load", "ship"]
    circles = {r["event"]: [(o["object"], o["selected"]) for o in r["objects"]] for r in p6.to_dicts()}
    assert circles["e028"] == [("o1", False)] and circles["e030"] == [("t1", True)] and circles["e026"] == []
    columns = align_columns(traces.events)
    assert [columns[e] for e in p6["event"].to_list()] == [0, 1, 2, 3, 10, 11]


def test_traces_note_unknown_objects():
    """An unknown id is reported, not drawn."""
    traces = object_traces(_frames(), ["p6", "nope"])
    assert traces.totals["object"].to_list() == ["p6"] and "nope" in traces.notes[0]


def test_object_graph_of_p6():
    """Section 4.2: S = {p6}, R = {t1, o1}; no arc between t1 and o1."""
    graph = object_graph(_frames(), ["p6"])
    assert sorted(graph.nodes["node"].to_list()) == ["o1", "p6", "t1"]
    arcs = {(r["source"], r["target"]): [e["event"] for e in r["events"]] for r in graph.event_arcs.to_dicts()}
    assert arcs == {("o1", "p6"): ["e028"], ("p6", "t1"): ["e030", "e031"]}


def test_object_graph_adds_o2o_neighbours():
    """An o2o relation makes its target a related object and draws a dashed arc."""
    graph = object_graph(_frames(), ["p1"])
    assert sorted(graph.nodes["node"].to_list()) == ["p1", "t1"]
    assert graph.o2o_arcs.to_dicts() == [{"source": "p1", "target": "t1", "qualifier": "carried by"}]
