"""Object graph of the objects selected on the page "Instances".

Documented in `docs/pages/instances.md`, section "Object graph" (concept: `Instances (draft).md`, section 4.2).
Nodes are the selected objects and every object related to one of them, by a shared event or by an o2o relation
(in either direction); arcs are the shared events (one undirected arc per pair of objects, listing its events) and
the o2o relations (directed, with their qualifier). The graph is complete for these nodes: arcs between two related
objects are included as well, so the frontend only shows or hides object types and arc kinds without asking the
backend again. `focal_events` lists the events of the selected objects with the nodes involved in each, for the
option that draws these events as boxes with a line to every involved object.
"""

from collections.abc import Collection
from dataclasses import dataclass

import polars as pl

from ocelescope_module_interactive_dfg.instances.frames import InstanceFrames

#: At most this many nodes are returned (selected objects first, then the others by the number of events shared
#: with the selected objects).
MAX_OBJECT_NODES = 500

#: Roles of the nodes.
FOCAL = "focal"
RELATED = "related"


@dataclass
class ObjectGraph:
    """The object graph of some selected objects.

    Attributes:
        nodes: Columns node, object_type, role (`focal` for the selected objects, `related`), n_events (events of
            the object in the log), n_shared (events shared with a selected object; null for selected objects).
        event_arcs: Columns source, target (source < target), events (list of structs event, time, activity,
            ordered by time and event id), n_events.
        o2o_arcs: Columns source, target, qualifier.
        events: Columns event, time, activity, objects (sorted ids of the nodes involved); the events of the
            selected objects, ordered by time and event id (see `focal_events`).
        notes: Remarks, e.g. selected objects that are not part of the log, or a cut graph.
    """

    nodes: pl.DataFrame
    event_arcs: pl.DataFrame
    o2o_arcs: pl.DataFrame
    events: pl.DataFrame
    notes: list[str]


def related_objects(frames: InstanceFrames, selected: Collection[str]) -> pl.DataFrame:
    """The objects related to the selected ones, by a shared event or an o2o relation, with their shared events.

    Args:
        frames: Tables of the log.
        selected: The selected objects.

    Returns:
        pl.DataFrame: Columns object, n_shared (events shared with a selected object; 0 if only o2o-related), for
        every related object that is not selected.
    """
    selected = list(selected)
    events = frames.e2o.lazy().filter(pl.col("object").is_in(selected)).select("event").unique()
    by_event = (
        frames.e2o.lazy().join(events, on="event", how="semi")
        .filter(~pl.col("object").is_in(selected))
        .group_by("object")
        .agg(pl.len().cast(pl.Int64).alias("n_shared"))
    )
    o2o = frames.o2o.lazy().filter(pl.col("source").is_in(selected) | pl.col("target").is_in(selected))
    by_o2o = (
        pl.concat([o2o.select(pl.col("source").alias("object")), o2o.select(pl.col("target").alias("object"))])
        .filter(~pl.col("object").is_in(selected))
        .unique()
        .with_columns(pl.lit(0, pl.Int64).alias("n_shared"))
    )
    return (
        pl.concat([by_event, by_o2o])
        .group_by("object")
        .agg(pl.col("n_shared").max())
        .sort("object")
        .collect()
    )


def graph_nodes(
    frames: InstanceFrames, selected: Collection[str], related: pl.DataFrame
) -> pl.DataFrame:
    """The nodes of the object graph: the selected objects and the related ones.

    Args:
        frames: Tables of the log.
        selected: The selected objects (all part of the log).
        related: Output of `related_objects`.

    Returns:
        pl.DataFrame: Columns node, object_type, role, n_events, n_shared (null for selected nodes); selected nodes
        first (in the given order), then the related objects by n_shared (descending) and id.
    """
    focal = pl.DataFrame(
        {"object": list(selected), "n_shared": None, "order": range(len(selected))},
        schema={"object": pl.String, "n_shared": pl.Int64, "order": pl.Int64},
    )
    nodes = pl.concat([focal, related.with_columns(pl.lit(None, pl.Int64).alias("order"))])
    ids = nodes["object"].to_list()
    counts = frames.e2o.lazy().filter(pl.col("object").is_in(ids)).group_by("object").agg(pl.len().cast(pl.Int64).alias("n_events"))
    types = frames.objects.lazy().filter(pl.col("object").is_in(ids))
    return (
        nodes.lazy()
        .join(types, on="object", how="left")
        .join(counts, on="object", how="left")
        .with_columns(
            pl.when(pl.col("order").is_not_null()).then(pl.lit(FOCAL)).otherwise(pl.lit(RELATED)).alias("role"),
            pl.col("n_events").fill_null(0),
        )
        .sort(
            [pl.col("order").is_null(), "order", "n_shared", "object"],
            descending=[False, False, True, False],
            nulls_last=True,
        )
        .select(pl.col("object").alias("node"), "object_type", "role", "n_events", "n_shared")
        .collect()
    )


def event_arcs(frames: InstanceFrames, nodes: Collection[str]) -> pl.DataFrame:
    """One undirected arc per pair of nodes that share at least one event, with the shared events.

    Args:
        frames: Tables of the log.
        nodes: Ids of the nodes.

    Returns:
        pl.DataFrame: Columns source, target (source < target), events (list of structs event, time, activity,
        ordered by time and event id), n_events; ordered by source and target.
    """
    e2o = frames.e2o.lazy().filter(pl.col("object").is_in(list(nodes)))
    pairs = (
        e2o.join(e2o, on="event", suffix="_2")
        .filter(pl.col("object") < pl.col("object_2"))
        .join(frames.events.lazy(), on="event", how="left")
        .sort("time", "event")
    )
    return (
        pairs.group_by(pl.col("object").alias("source"), pl.col("object_2").alias("target"), maintain_order=True)
        .agg(pl.struct("event", "time", "activity").alias("events"))
        .with_columns(pl.col("events").list.len().cast(pl.Int64).alias("n_events"))
        .sort("source", "target")
        .collect()
    )


def o2o_arcs(frames: InstanceFrames, nodes: Collection[str]) -> pl.DataFrame:
    """The o2o relations between nodes, as directed arcs.

    Args:
        frames: Tables of the log.
        nodes: Ids of the nodes.

    Returns:
        pl.DataFrame: Columns source, target, qualifier; ordered by source, target and qualifier.
    """
    nodes = list(nodes)
    return (
        frames.o2o.lazy().filter(pl.col("source").is_in(nodes) & pl.col("target").is_in(nodes))
        .sort("source", "target", "qualifier")
        .collect()
    )


def focal_events(frames: InstanceFrames, selected: Collection[str], nodes: Collection[str]) -> pl.DataFrame:
    """The events of the selected objects, each with the nodes of the graph it involves.

    Example (running example): p6 is selected and e030 (load) involves p6 and t1; e030's objects are [p6, t1] if both
    are nodes (a node cut by `MAX_OBJECT_NODES` is left out).

    Args:
        frames: Tables of the log.
        selected: The selected objects.
        nodes: Ids of the nodes (selected ones included).

    Returns:
        pl.DataFrame: Columns event, time, activity, objects (list of node ids, sorted); ordered by time and event id.
    """
    events = frames.e2o.lazy().filter(pl.col("object").is_in(list(selected))).select("event").unique()
    return (
        frames.e2o.lazy().join(events, on="event", how="semi")
        .filter(pl.col("object").is_in(list(nodes)))
        .group_by("event")
        .agg(pl.col("object").unique().sort().alias("objects"))
        .join(frames.events.lazy(), on="event", how="left")
        .select("event", "time", "activity", "objects")
        .sort("time", "event")
        .collect()
    )


def object_graph(frames: InstanceFrames, selected: Collection[str], max_nodes: int = MAX_OBJECT_NODES) -> ObjectGraph:
    """The object graph of the selected objects: they, their related objects and all arcs between these.

    Example (running example): p6 selected; related t1 (load, ship) and o1 (inspect); arcs p6-o1 (e028) and
    p6-t1 (e030, e031); t1 and o1 share no event, so there is no arc between them.

    Args:
        frames: Tables of the log (`frames.instance_frames`).
        selected: The selected objects (order kept).
        max_nodes: Nodes returned at most; beyond it the graph is cut (order of `graph_nodes`).

    Returns:
        ObjectGraph: Nodes, event arcs, o2o arcs, events of the selected objects and notes.
    """
    known = set(frames.objects["object"].to_list())
    focal = [o for o in dict.fromkeys(selected) if o in known]
    notes = []
    unknown = [o for o in selected if o not in known]
    if unknown:
        notes.append(f"Not objects of this log: {', '.join(unknown)}.")
    nodes = graph_nodes(frames, focal, related_objects(frames, focal))
    if nodes.height > max_nodes:
        notes.append(f"{nodes.height} objects; only the first {max_nodes} are drawn.")
        nodes = nodes.head(max_nodes)
    ids = nodes["node"].to_list()
    return ObjectGraph(
        nodes=nodes,
        event_arcs=event_arcs(frames, ids),
        o2o_arcs=o2o_arcs(frames, ids),
        events=focal_events(frames, focal, ids),
        notes=notes,
    )
