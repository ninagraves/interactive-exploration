"""Step 2: the activity selection per object type, applied to the traces first (projection).

For every selected object type the user selects the activities to keep. Default: the `DEFAULT_ACTIVITY_SHARE`
= 40 % most frequent activities of the type (by events of its objects; the number of activities
rounded up), but at least `MIN_ACTIVITIES` = 3 and at most `MAX_ACTIVITIES` = 10 (all if the type has fewer).
Before anything else, the events of
deselected activities are removed from the traces of that type: a trace <a, b, c> with b deselected becomes
<a, c>. Paths, arcs and frequencies are then computed on the projected traces, as in Ocelescope's DFG discovery
(`ocelescope.discovery.algorithms.dfg_miner`, which removes the events of excluded activities before the
directly-follows relations). An object whose projected trace is empty has no path and is left out.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping

import polars as pl

from . import columns as c
from .traces import FrameLike, considered_objects

#: Share (percent) of a type's activities that is preselected, most frequent first (Nina, 2026-11-15).
DEFAULT_ACTIVITY_SHARE = 40
#: Minimum number of preselected activities per object type.
MIN_ACTIVITIES = 3
#: Maximum number of preselected activities per object type.
MAX_ACTIVITIES = 10
#: Column: time of the first event of an activity (for the order of equally frequent activities).
FIRST_TIME = "first_time"


def type_activity_counts(e2o: FrameLike, events: FrameLike, objects: FrameLike) -> pl.DataFrame:
    """Events per object type and activity: the events with at least one object of the type.

    Args:
        e2o: Event-to-object relations, columns event and object.
        events: Events, columns event, time and activity.
        objects: All objects, columns object and object_type.

    Returns:
        pl.DataFrame: Columns object_type, activity, events (distinct events with at least one object of the type),
        first_time; sorted by object type, most events first, then first occurrence, then activity.
    """
    return (
        e2o.lazy()
        .select(c.EVENT, c.OBJECT)
        .unique()
        .join(objects.lazy().select(c.OBJECT, c.OBJECT_TYPE), on=c.OBJECT)
        .join(events.lazy().select(c.EVENT, c.TIME, c.ACTIVITY), on=c.EVENT)
        .group_by(c.OBJECT_TYPE, c.ACTIVITY)
        .agg(pl.col(c.EVENT).n_unique().alias(c.EVENTS), pl.col(c.TIME).min().alias(FIRST_TIME))
        .sort([c.OBJECT_TYPE, c.EVENTS, FIRST_TIME, c.ACTIVITY], descending=[False, True, False, False])
        .collect()
    )


def selected_type_event_counts(e2o: FrameLike, events: FrameLike, objects: FrameLike, object_types: Collection[str]) -> dict[str, int]:
    """Events per activity that involve at least one object of the selected object types.

    Shown in brackets in the activity list.
    Example: pallets selected, "refuel" only involves trucks: 0.

    Args:
        e2o: Event-to-object relations, columns event and object.
        events: Events, columns event and activity.
        objects: All objects, columns object and object_type.
        object_types: The selected object types.

    Returns:
        dict[str, int]: Activity -> number of its events with at least one object of a selected type (activities
        with none are missing).
    """
    counts = (
        e2o.lazy()
        .select(c.EVENT, c.OBJECT)
        .join(considered_objects(objects, object_types), on=c.OBJECT)
        .select(c.EVENT)
        .unique()
        .join(events.lazy().select(c.EVENT, c.ACTIVITY), on=c.EVENT)
        .group_by(c.ACTIVITY)
        .agg(pl.len().alias(c.EVENTS))
        .collect()
    )
    return dict(zip(counts[c.ACTIVITY], counts[c.EVENTS], strict=True))


def default_activity_count(n_activities: int) -> int:
    """Number of preselected activities of a type with `n_activities` activities.

    Args:
        n_activities: Number of activities with events of the type's considered objects.

    Returns:
        int: ceil(40 % of them), but at least 3 and at most 10, and never more than there are.
        Example: 4 activities -> ceil(1.6) = 2 -> 3; 12 -> ceil(4.8) = 5; 30 -> 12 -> 10; 2 -> 2.
    """
    n = -(-n_activities * DEFAULT_ACTIVITY_SHARE // 100)
    return min(n_activities, max(MIN_ACTIVITIES, min(MAX_ACTIVITIES, n)))


def default_activities(
    counts: pl.DataFrame, object_types: Collection[str], shared_from: Collection[str] = ()
) -> dict[str, list[str]]:
    """The preselected activities of each object type: its most frequent ones (`default_activity_count`), plus every
    activity preselected for a type of `shared_from` that the type has events of (this may exceed `MAX_ACTIVITIES`).
    The page passes no `shared_from` (draft decision, see the conceptualisation): every type gets its own defaults.
    Example: coil's own default PR, PI, PA, slab's LO, SH, PA: with both in `shared_from`, coil also gets LO and SH if
    coils take part in them.

    Args:
        counts: `type_activity_counts` (sorted: most events first, ties by first occurrence, then name).
        object_types: The object types to preselect for.
        shared_from: The types whose own defaults are shared with all (e.g. types that should share their defaults).

    Returns:
        dict[str, list[str]]: Object type -> preselected activities, in the type's frequency order.
    """
    wanted = set(object_types) | set(shared_from)
    ranked: dict[str, list[str]] = {t: [] for t in wanted}
    for object_type, activity in (
        counts.filter(pl.col(c.OBJECT_TYPE).is_in(list(wanted))).select(c.OBJECT_TYPE, c.ACTIVITY).iter_rows()
    ):
        ranked[object_type].append(activity)
    own = {t: a[: default_activity_count(len(a))] for t, a in ranked.items()}
    shared = {a for t in shared_from for a in own[t]}
    return {t: [a for a in ranked[t] if a in set(own[t]) or a in shared] for t in object_types}


def project_traces(traces: pl.DataFrame, included: Mapping[str, Collection[str]]) -> pl.DataFrame:
    """Remove the events of deselected activities from the traces (projection), per object type.

    Args:
        traces: Object traces (`traces.object_traces`), sorted by object and position.
        included: Object type -> activities to keep; a type that is missing keeps all its activities.

    Returns:
        pl.DataFrame: The kept rows, same columns and order, with `position` renumbered from 1 per object.
    """
    if not included:
        return traces
    pairs = pl.DataFrame(
        [(t, a) for t, activities in included.items() for a in activities],
        schema={c.OBJECT_TYPE: pl.String, c.ACTIVITY: pl.String},
        orient="row",
    )
    restricted = pl.col(c.OBJECT_TYPE).is_in(list(included))
    kept = pl.concat(
        [
            traces.filter(~restricted),
            traces.filter(restricted).join(pairs, on=[c.OBJECT_TYPE, c.ACTIVITY], how="semi"),
        ]
    )
    return (
        kept.sort(c.OBJECT, c.POSITION)
        .with_columns(pl.int_range(1, pl.len() + 1, dtype=pl.UInt32).over(c.OBJECT).alias(c.POSITION))
        .select(traces.columns)
    )
