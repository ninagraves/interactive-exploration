"""Interactive DFG (docs/pages/interactive-dfg.md): traces, projection, variants, arcs, nodes."""

from dataclasses import replace
from datetime import datetime, timedelta

import polars as pl
import pytest

from ocelescope_module_interactive_dfg.dfg.projection import default_activity_count
from ocelescope_module_interactive_dfg.dfg.variants import activity_variant_thresholds, object_variants, variant_ranking
from ocelescope_module_interactive_dfg.dfg.graph import (
    DfgRequest,
    default_selection,
    LogFrames,
    TypeSetting,
    directly_follows_graph,
    TypeThresholds,
    log_frames,
    resolve_selection,
    selected_traces,
)


@pytest.fixture(scope="module")
def frames(ocel) -> LogFrames:
    """The running example's frames."""
    return log_frames(ocel)


def arcs_of(graph, object_type):
    """The arcs of one object type as {(source, target): (count, objects)}."""
    return {(a.source, a.target): (a.count, a.objects) for a in graph.arcs if a.object_type == object_type}


ALL = {"variant_threshold": 100, "arc_threshold": 100}


def full(*types):
    """Selection of the given types with all variants and all arcs."""
    return [TypeSetting(object_type=t, **ALL) for t in types]


def every_activity(frames, *types):
    """Activity selection that keeps every activity of the log for the given types (no projection)."""
    activities = frames.events["activity"].unique().to_list()
    return {t: activities for t in types}


def test_default_selects_the_five_types_with_the_most_objects(frames):
    # The running example has two object types only: both are selected, most objects first.
    graph = directly_follows_graph(frames)
    assert [(t.object_type, t.selected, t.objects) for t in graph.object_types] == [
        ("coil", True, 5),
        ("slab", True, 1),
    ]


def test_default_thresholds(frames):
    graph = directly_follows_graph(frames)
    coil = next(t for t in graph.object_types if t.object_type == "coil")
    # Defaults: variants 80 % for all types: the 5 coils have a variant each, the first four cover
    # 60 % < 80 %, the fifth starts at 80 %: 4 variants. Arcs (projection) 50 %, no arc count.
    assert graph.variant_default == 80.0
    assert (coil.variant_threshold, coil.arc_threshold, coil.arc_count, coil.kept_variants, coil.kept_objects) == (80.0, 50, None, 4, 4)
    slab = next(t for t in graph.object_types if t.object_type == "slab")
    assert (slab.variant_threshold, slab.kept_variants) == (80.0, 1)


def test_equally_frequent_paths_are_ranked_by_first_occurrence(frames):
    # All coils have their own path: ranked by the first event of the coil (c1 and c2 both start at 3:00, then
    # alphabetically by the path: "roll, label, crane move, load truck" < "roll, label, crane move, quality check").
    ranking = variant_ranking(object_variants(selected_traces(frames, ["coil"])))
    first = {v: o for o, v in object_variants(selected_traces(frames, ["coil"])).select("object", "variant").iter_rows()}
    assert [first[v] for v in ranking["variant"]] == ["c2", "c1", "c3", "c4", "c5"]


def test_running_example_arcs(frames):
    graph = directly_follows_graph(frames, full("coil", "slab"), activities=every_activity(frames, "coil", "slab"))
    assert arcs_of(graph, "slab") == {
        (None, "cast slab"): (1, 1),
        ("cast slab", "inspect slab"): (1, 1),
        ("inspect slab", "roll"): (1, 1),
        ("roll", None): (1, 1),
    }
    coil = arcs_of(graph, "coil")
    assert len(coil) == 18
    assert coil[("load truck", "unload truck")] == (3, 3)
    assert coil[(None, "roll")] == (2, 2)
    assert coil[("quality check", None)] == (4, 4)
    # Every coil has exactly one start and one end arc.
    assert sum(n for (s, _), (n, _) in coil.items() if s is None) == 5
    assert sum(n for (_, t), (n, _) in coil.items() if t is None) == 5


def test_activity_frequencies(frames):
    graph = directly_follows_graph(frames, full("coil", "slab"), activities=every_activity(frames, "coil", "slab"))
    events = {a.activity: a.events for a in graph.activities}
    assert events == {
        "cast slab": 1, "crane move": 4, "cut": 1, "inspect slab": 1, "label": 1,
        "load truck": 2, "quality check": 4, "roll": 1, "unload truck": 2,
    }
    roll = next(a for a in graph.activities if a.activity == "roll")
    assert [(t.object_type, t.events, t.objects) for t in roll.object_types] == [("coil", 1, 2), ("slab", 1, 1)]


def test_unselected_type_is_only_involved(frames):
    graph = directly_follows_graph(frames, full("coil"), activities=every_activity(frames, "coil"))
    assert arcs_of(graph, "slab") == {}
    assert "cast slab" not in {a.activity for a in graph.activities}
    roll = next(a for a in graph.activities if a.activity == "roll")
    assert {t.object_type for t in roll.object_types} == {"coil", "slab"}


def test_variant_threshold_keeps_most_frequent_variants(frames):
    # All five coils have different variants; 50 % of 5 coils keeps variants until 2.5 coils are covered: 3.
    graph = directly_follows_graph(frames, [TypeSetting(object_type="coil", variant_threshold=50, arc_threshold=100)])
    coil = next(t for t in graph.object_types if t.object_type == "coil")
    assert (coil.variants, coil.kept_variants, coil.kept_objects) == (5, 3, 3)
    none = directly_follows_graph(frames, [TypeSetting(object_type="coil", variant_threshold=0, arc_threshold=100)])
    assert none.arcs == [] and none.activities == []


def test_arc_threshold_ranks_all_arcs_by_objects_and_keeps_ties(frames):
    # coil has 18 arcs (start and end arcs included); 20 % of 18 = 3.6 -> 4, and the fourth, (2, 2), is tied with
    # four more: 8 arcs (as Ocelescope's DFG filter).
    every = every_activity(frames, "coil")
    setting = [TypeSetting(object_type="coil", variant_threshold=100, arc_threshold=20)]
    coil = arcs_of(directly_follows_graph(frames, setting, activities=every, stay=False), "coil")
    assert coil == {
        ("quality check", None): (4, 4),
        ("load truck", "unload truck"): (3, 3),
        ("unload truck", "crane move"): (3, 3),
        (None, "roll"): (2, 2),
        ("roll", "label"): (2, 2),
        ("label", "crane move"): (2, 2),
        ("crane move", "quality check"): (2, 2),
        ("crane move", "load truck"): (2, 2),
    }
    none = directly_follows_graph(frames, [TypeSetting(object_type="coil", variant_threshold=100, arc_threshold=0)], activities=every)
    assert arcs_of(none, "coil") == {}


def test_arc_count_keeps_exactly_n_arcs_per_type_by_the_tie_break(frames):
    every = every_activity(frames, "coil", "slab")
    selection = [TypeSetting(object_type=t, variant_threshold=100, arc_count=2) for t in ("coil", "slab")]
    graph = directly_follows_graph(frames, selection, activities=every, stay=False)
    assert set(arcs_of(graph, "coil")) == {("quality check", None), ("load truck", "unload truck")}
    # The slab's arcs are all (1, 1): first occurrence decides (start arc, then cast slab -> inspect slab).
    assert set(arcs_of(graph, "slab")) == {(None, "cast slab"), ("cast slab", "inspect slab")}
    assert graph.arc_count_max == 18


def test_stay_connected_adds_back_the_arcs_needed_for_start_to_end_paths(frames):
    every = every_activity(frames, "slab")
    selection = [TypeSetting(object_type="slab", variant_threshold=100, arc_count=1)]
    graph = directly_follows_graph(frames, selection, activities=every)
    assert [(a.source, a.target, a.connecting) for a in graph.arcs] == [
        (None, "cast slab", False),
        ("cast slab", "inspect slab", True),
        ("inspect slab", "roll", True),
        ("roll", None, True),
    ]
    assert [(a.source, a.target) for a in directly_follows_graph(frames, selection, activities=every, stay=False).arcs] == [(None, "cast slab")]


def test_arcs_removed_by_hand_stay_removed(frames):
    # Removing inspect slab -> roll cuts the slab's only path: with "Stay connected" no arc is left (no arc lies on a
    # start-to-end path), without it the other three arcs stay.
    every = every_activity(frames, "slab")
    selection = full("slab")
    removed = [("slab", "inspect slab", "roll")]
    assert directly_follows_graph(frames, selection, activities=every, removed=removed).arcs == []
    graph = directly_follows_graph(frames, selection, activities=every, stay=False, removed=removed)
    assert len(graph.arcs) == 3
    assert [(a.source, a.target, a.count) for a in graph.removed_arcs] == [("inspect slab", "roll", 1)]


def test_deselected_activity_is_projected_out_first(frames):
    # Projection (Nina, 2026-11-15): without label, the coils' traces roll, label, crane move become roll, crane move.
    activities = every_activity(frames, "coil", "slab")
    activities["coil"] = [a for a in activities["coil"] if a != "label"]
    graph = directly_follows_graph(frames, full("coil", "slab"), activities=activities)
    coil = arcs_of(graph, "coil")
    assert ("roll", "label") not in coil and ("label", "crane move") not in coil
    assert coil[("roll", "crane move")] == (2, 2)
    assert "label" not in {a.activity for a in graph.activities}
    options = {o.activity: o for o in graph.activity_options}
    assert [(t.object_type, t.events, t.included) for t in options["label"].object_types] == [("coil", 1, False)]


def test_default_activities_are_the_most_frequent_40_percent_between_3_and_10(frames):
    assert [default_activity_count(n) for n in (2, 4, 7, 12, 30)] == [2, 3, 3, 5, 10]
    # coil has 7 activities -> 3: crane move 4, quality check 4, load truck 2 (before unload truck 2 by first occurrence).
    # No sharing between the types: coil does not get slab's roll.
    graph = directly_follows_graph(frames)
    options = {o.activity: o for o in graph.activity_options}
    coil = {a for a, o in options.items() for t in o.object_types if t.object_type == "coil" and t.included}
    assert coil == {"crane move", "quality check", "load truck"}
    slab = {a for a, o in options.items() for t in o.object_types if t.object_type == "slab" and t.included}
    assert slab == {"cast slab", "inspect slab", "roll"}
    # The list is ordered by events with an object of a selected type.
    assert [o.activity for o in graph.activity_options][:2] == ["crane move", "quality check"]
    assert options["crane move"].selected_events == 4


def _synthetic_frames() -> LogFrames:
    """Two pallets and a truck; e2 (pack) and e3 (move) share a timestamp; e1 is linked to p1 twice."""
    t = [datetime(2026, 1, 1, h) for h in (1, 2, 2, 3)]
    events = pl.DataFrame({"event": ["e1", "e2", "e3", "e4"], "time": t, "activity": ["pick", "pack", "move", "ship"]})
    objects = pl.DataFrame({"object": ["p1", "p2", "t1"], "object_type": ["pallet", "pallet", "truck"]})
    e2o = pl.DataFrame(
        {"event": ["e1", "e2", "e3", "e4", "e4", "e4", "e1"], "object": ["p1", "p1", "p1", "p1", "p2", "t1", "p1"]}
    ).join(objects, on="object")
    return LogFrames(e2o=e2o, events=events, objects=objects)


def test_ties_follow_the_activity_name_and_duplicate_links_count_once():
    # seq: time, then activity name ("move" < "pack"), then event id.
    traces = selected_traces(_synthetic_frames(), ["pallet"])
    assert traces.filter(pl.col("object") == "p1")["activity"].to_list() == ["pick", "move", "pack", "ship"]


def test_unselected_types_are_circles_on_the_nodes():
    frames = _synthetic_frames()
    graph = directly_follows_graph(frames, full("pallet"), activities=every_activity(frames, "pallet"))
    assert [t.object_type for t in graph.object_types if t.selected] == ["pallet"]
    ship = next(a for a in graph.activities if a.activity == "ship")
    assert [(t.object_type, t.events, t.objects) for t in ship.object_types] == [("pallet", 1, 2), ("truck", 1, 1)]


def test_every_object_of_a_selected_type_is_used():
    frames = _synthetic_frames()
    graph = directly_follows_graph(frames, full("pallet", "truck"), activities=every_activity(frames, "pallet", "truck"))
    pallet = next(t for t in graph.object_types if t.object_type == "pallet")
    assert (pallet.objects, pallet.kept_objects) == (2, 2)
    assert arcs_of(graph, "truck") == {(None, "ship"): (1, 1), ("ship", None): (1, 1)}


def test_default_selection_takes_the_five_types_with_the_most_objects():
    sizes = {"item": 8, "order": 5, "package": 4, "customer": 3, "product": 2, "employee": 2, "invoice": 1}
    objects = pl.DataFrame(
        [(f"{t}{i}", t) for t, n in sizes.items() for i in range(n)], schema=["object", "object_type"], orient="row"
    )
    # product and employee both have 2 objects: ties by name, so employee is the fifth.
    assert [s.object_type for s in default_selection(objects)] == ["item", "order", "package", "customer", "employee"]
    assert [s.object_type for s in default_selection(objects, 2)] == ["item", "order"]


def test_request_resolves_general_and_own_thresholds(frames):
    request = DfgRequest(
        variant_threshold=50,
        arc_count=4,
        type_thresholds=[TypeThresholds(object_type="slab", arc_threshold=30, arc_count=2), TypeThresholds(object_type="truck", variant_threshold=1)],
    )
    settings = resolve_selection(request, frames.objects)
    assert [(s.object_type, s.variant_threshold, s.arc_threshold, s.arc_count) for s in settings] == [
        ("coil", 50, 50, 4),
        ("slab", 50, 30, 2),
    ]


def _pallet_example() -> LogFrames:
    """The worked example of the module note "Interactive DFG Module" (the one of the location module's DFG page):
    ten pallets, a truck and an operator."""
    paths = {
        **{f"p{i}": ["produce", "pick", "pack", "load", "ship"] for i in range(1, 6)},
        **{f"p{i}": ["produce", "pick", "inspect", "pack", "load", "ship"] for i in range(6, 9)},
        "p9": ["produce", "inspect", "inspect", "scrap"],
        "p10": ["produce", "pick", "pack", "inspect", "pack", "load", "ship"],
    }
    rows, links, n = [], [], 0
    for i, (pallet, activities) in enumerate(paths.items()):
        for k, activity in enumerate(activities):
            n += 1
            hour = 10 * i + (0 if k < 2 else 1) if pallet == "p9" else 10 * i + k
            # p9: produce and inspect share the first timestamp, inspect and scrap the last.
            event = ["e902", "e901", "e904", "e903"][k] if pallet == "p9" else f"e{n:03d}"
            rows.append((event, datetime(2026, 1, 1) + timedelta(hours=hour), activity))
            links.append((event, pallet))
            if activity in ("load", "ship"):
                links.append((event, "t1"))
            if activity == "inspect":
                links.append((event, "o1"))
    events = pl.DataFrame(rows, schema=["event", "time", "activity"], orient="row")
    objects = pl.DataFrame({"object": [*paths, "t1", "o1"], "object_type": ["pallet"] * 10 + ["truck", "operator"]})
    return LogFrames(
        e2o=pl.DataFrame(links, schema=["event", "object"], orient="row").join(objects, on="object"),
        events=events,
        objects=objects,
    )


def test_worked_example_of_the_module_note():
    frames = _pallet_example()
    p9 = selected_traces(frames, ["pallet"]).filter(pl.col("object") == "p9")
    # Ties by activity name: "inspect" < "produce" at the first timestamp, "inspect" < "scrap" at the last.
    assert p9["activity"].to_list() == ["inspect", "produce", "inspect", "scrap"]
    every = every_activity(frames, "pallet", "truck")

    def pallet(**settings):
        return [TypeSetting(object_type="pallet", variant_threshold=60, **settings)]

    # Variants 60 %: 2 of 4 variants, p1-p8.
    graph = directly_follows_graph(frames, pallet(), activities=every)
    t = next(t for t in graph.object_types if t.object_type == "pallet")
    assert (t.kept_variants, t.kept_objects, t.arcs) == (2, 8, 8)
    assert graph.variant_default == 80.0
    # Arcs 70 %: ceil(5.6) = 6 arcs; PI -> IN and IN -> PA are dropped, so IN disappears.
    graph = directly_follows_graph(frames, pallet(arc_threshold=70), activities=every)
    assert ("pick", "pack") in arcs_of(graph, "pallet") and "inspect" not in {a.activity for a in graph.activities}
    assert len(graph.arcs) == 6
    # Arcs 50 %: the five arcs with 8 pallets (tied); Stay connected adds PI -> PA back.
    loose = directly_follows_graph(frames, pallet(arc_threshold=50), activities=every, stay=False)
    assert ("pick", "pack") not in arcs_of(loose, "pallet") and len(loose.arcs) == 5
    graph = directly_follows_graph(frames, pallet(arc_threshold=50), activities=every)
    assert [(a.source, a.target) for a in graph.arcs if a.connecting] == [("pick", "pack")]
    # Arc count 3: start -> PR, PR -> PI, PA -> LO (first occurrence); Stay connected adds PI -> PA, LO -> SH, SH -> end.
    graph = directly_follows_graph(frames, pallet(arc_count=3), activities=every, stay=False)
    assert set(arcs_of(graph, "pallet")) == {(None, "produce"), ("produce", "pick"), ("pack", "load")}
    graph = directly_follows_graph(frames, pallet(arc_count=3), activities=every)
    assert {(a.source, a.target) for a in graph.arcs if a.connecting} == {("pick", "pack"), ("load", "ship"), ("ship", None)}
    # Arcs 70 % and PI -> PA removed by hand: Stay connected adds PI -> IN and IN -> PA back instead.
    removed = [("pallet", "pick", "pack")]
    graph = directly_follows_graph(frames, pallet(arc_threshold=70), activities=every, removed=removed)
    assert {(a.source, a.target) for a in graph.arcs if a.connecting} == {("pick", "inspect"), ("inspect", "pack")}
    assert ("pick", "pack") not in arcs_of(graph, "pallet")
    # IN deselected: projected out before the variants, so p6-p8 have the variant of p1-p5 (8 pallets).
    no_inspect = {"pallet": [a for a in every["pallet"] if a != "inspect"]}
    graph = directly_follows_graph(frames, pallet(), activities=no_inspect)
    t = next(t for t in graph.object_types if t.object_type == "pallet")
    assert (t.variants, t.kept_variants, t.kept_objects) == (3, 1, 8)
    assert arcs_of(graph, "pallet")[("pick", "pack")] == (8, 8)
    # truck selected as well: LO and SH count p10's events with t1 too.
    truck = directly_follows_graph(frames, [*pallet(), TypeSetting(object_type="truck", variant_threshold=100)], activities=every)
    assert {a.activity: a.events for a in truck.activities}["load"] == 9
    # Defaults: activities PR, PA, PI (40 % of 7 -> 3); variants 80 %: of the 3 variants (8, 1, 1 pallets) only the
    # first (8 pallets before the second = 80 %); Arcs (projection) 50 %: ceil(2) = 2 of 4 arcs, all tied: 4 arcs.
    default = directly_follows_graph(frames)
    t = next(t for t in default.object_types if t.object_type == "pallet")
    assert default.variant_default == 80.0
    assert (t.variants, t.kept_variants, t.kept_objects, t.threshold_arcs, t.shown_arcs) == (3, 1, 8, 4, 4)


def test_thresholds_with_decimals(frames):
    # 33.3 % of 5 coils = 1.665 coils: two variants.
    graph = directly_follows_graph(frames, [TypeSetting(object_type="coil", variant_threshold=33.3)], activities=every_activity(frames, "coil"))
    assert next(t for t in graph.object_types if t.object_type == "coil").kept_variants == 2
    # 18 arcs: 5.5 % -> ceil(0.99) = 1 arc; 5.6 % -> ceil(1.008) = 2, and the second, (3, 3), is tied with a third.
    every = every_activity(frames, "coil")
    counts = [
        len(directly_follows_graph(frames, [TypeSetting(object_type="coil", variant_threshold=100, arc_threshold=x)], activities=every, stay=False).arcs)
        for x in (5.5, 5.6)
    ]
    assert counts == [1, 3]


def test_variant_threshold_needed_per_activity():
    """Activities on no included trace name the smallest variant threshold that includes them (pallets, all activities)."""
    frames = _pallet_example()
    graph = directly_follows_graph(frames, [TypeSetting(object_type="pallet", variant_threshold=50)], activities=every_activity(frames, "pallet"))
    options = {o.activity: o for o in graph.activity_options}
    # Variants: 5 x main (0 % before), 3 x with inspect (50 % before), p9 with scrap (80 % before), p10 (90 % before).
    assert options["pick"].on_included_trace and options["pick"].variant_threshold_needed == 1
    assert not options["inspect"].on_included_trace and options["inspect"].variant_threshold_needed == 51
    assert not options["scrap"].on_included_trace and options["scrap"].variant_threshold_needed == 81
    graph = directly_follows_graph(frames, [TypeSetting(object_type="pallet", variant_threshold=81)], activities=every_activity(frames, "pallet"))
    assert {o.activity: o for o in graph.activity_options}["scrap"].on_included_trace


def test_deselected_activities_name_the_variant_threshold_they_would_need():
    """A deselected activity names the variant threshold it would need if it alone were selected as well."""
    frames = _pallet_example()
    no_inspect_scrap = {"pallet": [a for a in every_activity(frames, "pallet")["pallet"] if a not in ("inspect", "scrap")]}
    graph = directly_follows_graph(frames, [TypeSetting(object_type="pallet", variant_threshold=50)], activities=no_inspect_scrap)
    options = {o.activity: o for o in graph.activity_options}
    # With inspect selected: 5 x main, 3 x with inspect (50 % before); with scrap: p9 has a variant of its own (80 %).
    assert options["inspect"].variant_threshold_needed == 51
    assert options["scrap"].variant_threshold_needed == 81
    assert options["inspect"].variant_threshold_needed_exact == 50.001
    assert options["scrap"].variant_threshold_needed_exact == 80.001


def _pallet_example_with_activities_without_pallets() -> LogFrames:
    """The worked example plus activities without pallets: truck t2 refuels; operators o2
    and o3 train, o2 has tea, o1 a break; t1 and o3 share a handover (all of 2025 except the handover in 2027)."""
    frames = _pallet_example()
    extra = [
        ("x1", datetime(2025, 1, 1, 0), "tea", ["o2"]),
        ("x2", datetime(2025, 1, 1, 1), "train", ["o3"]),
        ("x3", datetime(2025, 1, 1, 2), "train", ["o2"]),
        ("x4", datetime(2025, 1, 1, 3), "refuel", ["t2"]),
        ("x5", datetime(2025, 6, 1, 0), "break", ["o1"]),
        ("x6", datetime(2027, 1, 1, 0), "handover", ["t1", "o3"]),
    ]
    objects = pl.concat([frames.objects, pl.DataFrame({"object": ["t2", "o2", "o3"], "object_type": ["truck", "operator", "operator"]})])
    events = pl.concat(
        [
            frames.events,
            pl.DataFrame(
                [(e, t, a) for e, t, a, _ in extra],
                schema=frames.events.columns,
                orient="row",
            ),
        ]
    )
    links = pl.DataFrame([(e, o) for e, _, _, objs in extra for o in objs], schema=["event", "object"], orient="row")
    e2o = pl.concat([frames.e2o, links.join(objects, on="object")])
    return replace(frames, e2o=e2o, events=events, objects=objects)


def test_activities_without_selected_events_name_the_easiest_type():
    """With only pallets selected, an activity without pallets names, per type, the variant threshold it would need if
    the type were selected with its default activities, and the type with the smallest one."""
    frames = _pallet_example_with_activities_without_pallets()
    graph = directly_follows_graph(frames, [TypeSetting(object_type="pallet")])
    options = {o.activity: o for o in graph.activity_options}
    assert {a for a, o in options.items() if o.selected_events == 0} == {"tea", "train", "refuel", "break", "handover"}
    # Operators (defaults inspect, train, tea): variants o2 (tea, train), o3 (train), o1 (inspect ...), one object
    # each, ranked by first time; break only for o1: 2 of 3 operators before -> 66.667 %.
    assert (options["break"].easiest_type, options["break"].variant_threshold_needed_exact) == ("operator", 66.667)
    assert (options["refuel"].easiest_type, options["refuel"].variant_threshold_needed) == ("truck", 1)
    # handover: truck 50.001 % (t1 second of 2), operator 33.334 % (o3 second of 3) -> operator.
    per_type = {t.object_type: t.variant_threshold_needed_exact for t in options["handover"].object_types}
    assert per_type == {"truck": 50.001, "operator": 33.334}
    assert options["handover"].easiest_type == "operator"
    # Activities with pallets are unchanged: unselected types get no value.
    assert all(t.variant_threshold_needed is None for t in options["load"].object_types if not t.selected_type)


def test_exact_variant_thresholds_have_three_decimals():
    """`needed_exact` is the share before rounded down to 3 decimals plus 0.001 (2 of 3 before -> 66.667 %)."""
    ranking = pl.DataFrame(
        {"object_type": ["pallet"] * 2, "variant": ["a", "b"], "objects": [2, 1], "covered_before": [0, 2]}
    )
    rows = {r["activity"]: r for r in activity_variant_thresholds(ranking).iter_rows(named=True)}
    assert (rows["a"]["needed"], rows["a"]["needed_exact"]) == (1, 0.001)
    assert (rows["b"]["needed"], rows["b"]["needed_exact"]) == (67, 66.667)


@pytest.mark.parametrize("object_type", ["coil"])
def test_deselected_variant_thresholds_match_selecting_the_activity(frames, object_type):
    """Brute force: select each deselected activity in turn and compare with the value of the default graph."""
    setting = [TypeSetting(object_type=object_type)]
    graph = directly_follows_graph(frames, setting)
    compared = 0
    for option in graph.activity_options:
        own = next((t for t in option.object_types if t.object_type == object_type), None)
        if own is None or own.included:
            continue
        compared += 1
        selected = [a.activity for a in graph.activity_options if any(t.object_type == object_type and t.included for t in a.object_types)]
        alone = directly_follows_graph(frames, setting, activities={object_type: [*selected, option.activity]})
        expected = next(t for t in {o.activity: o for o in alone.activity_options}[option.activity].object_types if t.object_type == object_type)
        assert own.variant_threshold_needed == expected.variant_threshold_needed, option.activity
    assert compared > 0


def test_defaults_of_the_module_note():
    """The defaults on the pallet example (module note "Interactive DFG Module", section "The defaults"): all three
    object types are among the five with the most objects, so all are selected."""
    frames = _pallet_example()
    assert [s.object_type for s in default_selection(frames.objects)] == ["pallet", "operator", "truck"]
    graph = directly_follows_graph(frames)
    options = {o.activity: o for o in graph.activity_options}
    included = {t: {a for a, o in options.items() for x in o.object_types if x.object_type == t and x.included} for t in ("pallet", "operator", "truck")}
    assert included == {"pallet": {"produce", "pack", "pick"}, "operator": {"inspect"}, "truck": {"load", "ship"}}
    types = {t.object_type: t for t in graph.object_types}
    assert (types["pallet"].variants, types["pallet"].kept_objects, types["pallet"].shown_arcs) == (3, 8, 4)
    # Truck: 4 arcs, all with 1 object; Arcs (projection) 50 % keeps load -> ship (9) and ship -> load (8); Stay
    # connected adds the start and end arcs back.
    assert (types["truck"].arcs, types["truck"].threshold_arcs) == (4, 2)
    assert {(a.source, a.target) for a in graph.arcs if a.connecting} == {(None, "load"), ("ship", None)}
    assert arcs_of(graph, "operator") == {(None, "inspect"): (1, 1), ("inspect", "inspect"): (5, 1), ("inspect", None): (1, 1)}
    events = {a.activity: a.events for a in graph.activities}
    assert events == {"produce": 8, "pick": 8, "pack": 8, "inspect": 6, "load": 9, "ship": 9}
    assert (options["scrap"].on_included_trace, options["scrap"].variant_threshold_needed) == (False, 81)
