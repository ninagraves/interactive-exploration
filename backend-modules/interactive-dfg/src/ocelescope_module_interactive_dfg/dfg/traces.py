"""Step 1: the traces of the objects whose directly-follows relations are shown.

The trace of an object $o$ is $otrace(o) = seq(\\{e \\in E \\mid o \\in omap(e)\\})$: its events (via e2o; an object
linked to an event with several qualifiers counts once) ordered by time, ties broken by activity name
(alphabetically), then by event id (`seq` of the conceptualisation "Interactive DFG").
No domain knowledge is used: every object of a selected object type contributes its trace.
"""

from __future__ import annotations

from collections.abc import Iterable

import polars as pl

from . import columns as c

FrameLike = pl.DataFrame | pl.LazyFrame


def considered_objects(objects: FrameLike, object_types: Iterable[str]) -> pl.LazyFrame:
    """The objects whose traces are used for the selected object types: all objects of these types.

    Args:
        objects: All objects, columns object and object_type.
        object_types: The selected object types.

    Returns:
        pl.LazyFrame: Columns object, object_type.
    """
    return objects.lazy().filter(pl.col(c.OBJECT_TYPE).is_in(list(object_types))).select(c.OBJECT, c.OBJECT_TYPE)


def object_traces(e2o: FrameLike, events: FrameLike, objects: FrameLike) -> pl.DataFrame:
    """One row per (object, event) of the given objects, sorted by object, time, activity, event (`seq`).

    Example: events e2 (pack, 2:00) and e3 (move, 2:00) of pallet p1 share a timestamp: "move" < "pack", so the
    trace is pick, move, pack, ship.

    Args:
        e2o: Event-to-object relations, columns event and object (further columns are ignored; an object
            linked to an event with several qualifiers counts once).
        events: Events with columns event, time, activity.
        objects: The considered objects, columns object and object_type (`considered_objects`).

    Returns:
        pl.DataFrame: Columns object, object_type, event, activity, time, position (1-based position in the
        object's trace).
    """
    return (
        e2o.lazy()
        .select(c.EVENT, c.OBJECT)
        .unique()
        .join(objects.lazy(), on=c.OBJECT)
        .join(events.lazy().select(c.EVENT, c.TIME, c.ACTIVITY), on=c.EVENT)
        .sort(c.OBJECT, c.TIME, c.ACTIVITY, c.EVENT)
        .with_columns(pl.int_range(1, pl.len() + 1, dtype=pl.UInt32).over(c.OBJECT).alias(c.POSITION))
        .select(c.OBJECT, c.OBJECT_TYPE, c.EVENT, c.ACTIVITY, c.TIME, c.POSITION)
        .collect()
    )
