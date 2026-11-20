"""Tests of "Save to session" of the page (`dfg/export.py`)."""

import pytest

from ocelescope_module_interactive_dfg.dfg.export import dfg_resource, filtered_log, kept_event_ids
from ocelescope_module_interactive_dfg.dfg.graph import (
    default_selection,
    directly_follows_graph,
    included_traces,
    log_frames,
)


@pytest.fixture(scope="module")
def frames(ocel):
    """The running example's frames."""
    return log_frames(ocel)


def test_model_has_the_arcs_as_edges(frames):
    """The model is Ocelescope's DFG resource with one edge per arc (traversals and objects)."""
    graph = directly_follows_graph(frames)
    resource = dfg_resource(graph.arcs)
    assert len(resource.edges) == len(graph.arcs)
    assert set(resource.activity_names) == {a.activity for a in graph.activities}
    assert {(e.object_type, e.source, e.target, e.count, e.object_count) for e in resource.edges} == {
        (a.object_type, a.source, a.target, a.count, a.objects) for a in graph.arcs
    }


def test_log_keeps_the_events_of_the_included_traces(ocel, frames):
    """Projected: the events of the included traces; displayed: only those of the drawn activities."""
    selection = default_selection(frames.objects)
    steps = included_traces(frames, selection)
    projected = kept_event_ids(steps.kept)
    assert set(projected) == set(steps.kept["event"])
    log = filtered_log(ocel, projected)
    events = log.events.pl.collect()
    assert set(events["ocel:eid"]) == set(projected)
    assert set(events["ocel:activity"]) <= {"crane move", "quality check", "load truck", "cast slab", "inspect slab", "roll"}
    displayed = kept_event_ids(steps.kept, ["crane move", "cast slab"])
    assert set(filtered_log(ocel, displayed).events.pl.collect()["ocel:activity"]) == {"crane move", "cast slab"}
