"""Object traces of the objects selected on the page "Instances".

Documented in `docs/pages/instances.md`, section "Object traces" (concept: `Instances (draft).md`, section 4.1).
One row per selected object: its events in `seq` order (time, activity name, event id; as in the object profile),
each with its activity, timestamp and the other objects it involves, marked if they are selected themselves.

Steps (each a function of its own):
1. `profile.ordered_traces`: the events of the selected objects in `seq` order.
2. `involved_objects`: per event the objects it involves, with their object type.
3. `object_traces`: both joined, the object itself left out of its events' objects.
`align_columns` gives the columns of the option "Align shared events" (the page has its own TypeScript copy,
`alignColumns` in `ObjectTracesChart.tsx`).
"""

from collections.abc import Collection
from dataclasses import dataclass

import polars as pl

from ocelescope_module_interactive_dfg.dfg import columns as c
from ocelescope_module_interactive_dfg.instances.frames import InstanceFrames
from ocelescope_module_interactive_dfg.instances.profile import POS, ordered_traces

#: At most this many objects get a row (the first ones of the selection).
MAX_TRACES = 50


@dataclass
class ObjectTraces:
    """The traces of the selected objects.

    Attributes:
        events: One row per (object, event): object, object_type (of the row's object), pos (1-based), event, time,
            activity and objects (list of structs object, object_type, selected: the other objects of the event,
            sorted by object type and id; `selected` = one of the selected objects); sorted by the order of the
            selection, then pos.
        totals: Per shown object (in the order of the selection): object, object_type, n_events.
        notes: Remarks, e.g. selected objects that are not part of the log, or a cut selection.
    """

    events: pl.DataFrame
    totals: pl.DataFrame
    notes: list[str]


def involved_objects(frames: InstanceFrames, events: Collection[str]) -> pl.DataFrame:
    """The objects of the given events with their object type.

    Args:
        frames: Tables of the log.
        events: Event ids.

    Returns:
        pl.DataFrame: Columns event, object, object_type; sorted by event, object type and object.
    """
    return (
        frames.e2o.filter(pl.col(c.EVENT).is_in(list(events)))
        .join(frames.objects.unique(c.OBJECT, keep="first"), on=c.OBJECT, how="left")
        .sort(c.EVENT, c.OBJECT_TYPE, c.OBJECT, nulls_last=True)
    )


def object_traces(frames: InstanceFrames, selected: Collection[str], max_traces: int = MAX_TRACES) -> ObjectTraces:
    """The traces of the selected objects with the other objects of every event.

    Example (running example, p6 and t1 selected): p6's trace is e026 produce, e027 pick, e028 inspect (other
    object o1), e029 pack, e030 load and e031 ship (other object t1, marked selected); t1's trace has 18 events,
    e030 and e031 with p6 marked selected.

    Args:
        frames: Tables of the log (`frames.instance_frames`).
        selected: The selected objects (order kept).
        max_traces: Rows at most.

    Returns:
        ObjectTraces: Events, totals and notes.
    """
    known = set(frames.objects[c.OBJECT].to_list())
    notes = []
    unknown = [o for o in selected if o not in known]
    if unknown:
        notes.append(f"Not objects of this log: {', '.join(unknown)}.")
    shown = [o for o in dict.fromkeys(selected) if o in known]
    if len(shown) > max_traces:
        notes.append(f"{len(shown)} objects selected; only the first {max_traces} are drawn.")
        shown = shown[:max_traces]
    chosen = set(selected)
    order = pl.DataFrame({c.OBJECT: shown, "_order": range(len(shown))}, schema={c.OBJECT: pl.String, "_order": pl.Int64})
    events = ordered_traces(frames, shown)
    objects = involved_objects(frames, events[c.EVENT].unique().to_list()).with_columns(
        pl.col(c.OBJECT).is_in(list(chosen)).alias("selected")
    )
    struct = pl.Struct({c.OBJECT: pl.String, c.OBJECT_TYPE: pl.String, "selected": pl.Boolean})
    others = (
        events.select(pl.col(c.OBJECT).alias("_row"), c.EVENT)
        .join(objects, on=c.EVENT, how="inner")
        .filter(pl.col(c.OBJECT) != pl.col("_row"))
        .group_by("_row", c.EVENT, maintain_order=True)
        .agg(pl.struct(c.OBJECT, c.OBJECT_TYPE, "selected").alias("objects"))
        .rename({"_row": c.OBJECT})
    )
    rows = (
        events.join(others, on=[c.OBJECT, c.EVENT], how="left")
        .join(order, on=c.OBJECT, how="left")
        .sort("_order", POS)
        .with_columns(pl.col("objects").fill_null(pl.lit([], dtype=pl.List(struct))))
        .drop("_order")
    )
    totals = (
        order.join(frames.objects.unique(c.OBJECT, keep="first"), on=c.OBJECT, how="left")
        .join(events.group_by(c.OBJECT).agg(pl.len().cast(pl.Int64).alias("n_events")), on=c.OBJECT, how="left")
        .with_columns(pl.col("n_events").fill_null(0))
        .sort("_order")
        .drop("_order")
    )
    return ObjectTraces(events=rows, totals=totals, notes=notes)


def align_columns(events: pl.DataFrame) -> dict[str, int] | None:
    """One column per event, the same in every row it appears in, each row keeping its order ("Align shared events").

    The column of an event is the length of the longest chain of events before it over all rows: longest path in the
    graph with an arc from each event to the next one of the same row (Kahn's algorithm by rounds).

    Example (running example, p6 and t1): p6's first four events keep columns 0 to 3; its load e030 is t1's 11th
    event, so it moves to column 10 and ship e031 to column 11.

    Args:
        events: `ObjectTraces.events` (columns object, pos, event).

    Returns:
        dict[str, int] | None: Event -> column, or None if two rows order shared events differently (a cycle).
    """
    rows = events.sort(c.OBJECT, POS).group_by(c.OBJECT, maintain_order=True).agg(pl.col(c.EVENT))
    following: dict[str, set[str]] = {}
    indegree: dict[str, int] = {}
    for sequence in rows[c.EVENT].to_list():
        for i, event in enumerate(sequence):
            indegree.setdefault(event, 0)
            if i + 1 < len(sequence) and sequence[i + 1] not in following.setdefault(event, set()):
                following[event].add(sequence[i + 1])
                indegree[sequence[i + 1]] = indegree.get(sequence[i + 1], 0) + 1
    column: dict[str, int] = {}
    current = [e for e, d in indegree.items() if d == 0]
    depth = 0
    while current:
        upcoming = []
        for event in current:
            column[event] = depth
            for nxt in following.get(event, ()):
                indegree[nxt] -= 1
                if indegree[nxt] == 0:
                    upcoming.append(nxt)
        current = upcoming
        depth += 1
    return column if len(column) == len(indegree) else None
