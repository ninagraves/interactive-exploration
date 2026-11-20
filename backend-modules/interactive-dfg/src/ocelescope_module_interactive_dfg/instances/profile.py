"""Object profile: one row per object of the log with general information on its instance.

Documented in `docs/pages/instances.md`, section "Object profile" (concept: `Instances (draft).md`, section 3).
Every object is treated alike; there is no distinction between kinds of objects.

The profile is built in small steps, each a function of its own:
1. `ordered_traces`: the events of every object in `seq` order (time, activity name, event id) with their position.
2. `lifecycle`: events, distinct timestamps, first and last timestamp, lifespan.
3. `activity_profile`: first and last activity, number of distinct activities.
4. `connectedness`: shared events (events with more than one object) and linked objects (other objects sharing an
   event with the object).
`object_profile` joins them (also objects without events); `query_profile` searches, filters by column, sorts and
pages it (`ColumnFilter`, `column_info`); `export_frame` gives the folded table with the shown columns.
`object_details` gives what an unfolded row of the table shows for one object.
"""

from collections.abc import Collection, Sequence
from dataclasses import dataclass

import polars as pl

from ocelescope_module_interactive_dfg.dfg import columns as c
from ocelescope_module_interactive_dfg.instances.frames import InstanceFrames

#: Position of an event in the trace of its object (1-based).
POS = "pos"
#: Columns of the profile that `query_profile` can sort by (all scalar columns), in table order.
SORTABLE = (
    c.OBJECT,
    c.OBJECT_TYPE,
    "n_events",
    "n_timestamps",
    "first",
    "last",
    "lifespan",
    "first_activity",
    "last_activity",
    "n_activities",
    "n_shared_events",
    "n_linked",
)
#: Columns of the profile that can be filtered and exported (the sortable ones).
FILTERABLE = SORTABLE
#: A string column with at most this many distinct values is filtered by checkboxes (categories), otherwise by text.
MAX_CATEGORIES = 100


def ordered_traces(frames: InstanceFrames, objects: Collection[str] | None = None) -> pl.DataFrame:
    """The events of every object in `seq` order: time, then activity name, then event id.

    Example (running example): p9 has produce and inspect at hour 80, inspect and scrap at hour 81; its trace is
    inspect, produce, inspect, scrap ("inspect" < "produce", "inspect" < "scrap").

    Args:
        frames: Tables of the log.
        objects: Only these objects; None = all.

    Returns:
        pl.DataFrame: Columns object, object_type, pos, event, time, activity; sorted by object and pos.
    """
    e2o = frames.e2o if objects is None else frames.e2o.filter(pl.col(c.OBJECT).is_in(list(objects)))
    return (
        e2o.join(frames.events, on=c.EVENT, how="inner")
        .join(frames.objects, on=c.OBJECT, how="left")
        .sort(c.OBJECT, c.TIME, c.ACTIVITY, c.EVENT, nulls_last=True)
        .with_columns((pl.int_range(pl.len()).over(c.OBJECT) + 1).cast(pl.UInt32).alias(POS))
        .select(c.OBJECT, c.OBJECT_TYPE, POS, c.EVENT, c.TIME, c.ACTIVITY)
    )


def lifecycle(traces: pl.DataFrame) -> pl.DataFrame:
    """Lifecycle columns per object: events, distinct timestamps, first and last timestamp, lifespan.

    Example (running example): p9 has 4 events at 2 timestamps (hours 80 and 81), lifespan 1 h = 3600 s.

    Args:
        traces: Output of `ordered_traces`.

    Returns:
        pl.DataFrame: Columns object, n_events, n_timestamps, first, last, lifespan (seconds, float).
    """
    return traces.group_by(c.OBJECT).agg(
        pl.len().cast(pl.Int64).alias("n_events"),
        pl.col(c.TIME).n_unique().cast(pl.Int64).alias("n_timestamps"),
        pl.col(c.TIME).min().alias("first"),
        pl.col(c.TIME).max().alias("last"),
        ((pl.col(c.TIME).max() - pl.col(c.TIME).min()).dt.total_milliseconds() / 1000).alias("lifespan"),
    )


def activity_profile(traces: pl.DataFrame) -> pl.DataFrame:
    """Activity columns per object: first and last activity of its trace, number of distinct activities.

    Example (running example): p10 starts with produce, ends with ship and has 6 distinct activities (pack twice).

    Args:
        traces: Output of `ordered_traces` (sorted by object and pos).

    Returns:
        pl.DataFrame: Columns object, first_activity, last_activity, n_activities.
    """
    return traces.group_by(c.OBJECT).agg(
        pl.col(c.ACTIVITY).sort_by(POS).first().alias("first_activity"),
        pl.col(c.ACTIVITY).sort_by(POS).last().alias("last_activity"),
        pl.col(c.ACTIVITY).n_unique().cast(pl.Int64).alias("n_activities"),
    )


def connectedness(frames: InstanceFrames) -> pl.DataFrame:
    """Connectedness columns per object: shared events and linked objects.

    A shared event is an event of the object with more than one object; the linked objects are the other objects
    sharing at least one event with it.
    Example (running example): p6 shares inspect with o1 and load and ship with t1: 3 shared events, 2 linked objects.

    Args:
        frames: Tables of the log.

    Returns:
        pl.DataFrame: Columns object, n_shared_events, n_linked (objects with events only).
    """
    sizes = frames.e2o.group_by(c.EVENT).agg(pl.len().alias("_size"))
    shared = (
        frames.e2o.join(sizes, on=c.EVENT)
        .group_by(c.OBJECT)
        .agg((pl.col("_size") > 1).sum().cast(pl.Int64).alias("n_shared_events"))
    )
    linked = (
        frames.e2o.join(frames.e2o, on=c.EVENT, suffix="_other")
        .filter(pl.col(c.OBJECT) != pl.col(f"{c.OBJECT}_other"))
        .group_by(c.OBJECT)
        .agg(pl.col(f"{c.OBJECT}_other").n_unique().cast(pl.Int64).alias("n_linked"))
    )
    return shared.join(linked, on=c.OBJECT, how="left").with_columns(pl.col("n_linked").fill_null(0))


def object_profile(frames: InstanceFrames) -> pl.DataFrame:
    """The object profile: one row per object of the log, objects without events included.

    Args:
        frames: Tables of the log (`frames.instance_frames`).

    Returns:
        pl.DataFrame: Columns of `SORTABLE`; counts of objects without events are 0, their timestamps and
        activities null; sorted by object.
    """
    traces = ordered_traces(frames)
    counts = ["n_events", "n_timestamps", "n_activities", "n_shared_events", "n_linked"]
    return (
        frames.objects.unique(c.OBJECT, keep="first")
        .join(lifecycle(traces), on=c.OBJECT, how="left")
        .join(activity_profile(traces), on=c.OBJECT, how="left")
        .join(connectedness(frames), on=c.OBJECT, how="left")
        .with_columns(pl.col(counts).fill_null(0))
        .select(SORTABLE)
        .sort(c.OBJECT)
    )


def search_text() -> pl.Expr:
    """Expression for the text a search matches: id, object type, first and last activity, lower case.

    Returns:
        pl.Expr: String named `_search`.
    """
    return (
        pl.concat_str(
            [pl.col(name).cast(pl.String).fill_null("") for name in (c.OBJECT, c.OBJECT_TYPE, "first_activity", "last_activity")],
            separator=" ",
        )
        .str.to_lowercase()
        .alias("_search")
    )


@dataclass
class ColumnFilter:
    """A filter on one column of the profile; a row is kept if it satisfies every filter.

    Set one of:
    - values: keep rows whose value is one of these (None in the list = missing value);
    - min and/or max: keep rows whose value is in [min, max] (rows without a value are dropped); for timestamp
      columns both are milliseconds since 1970-01-01 (UTC), for the lifespan seconds;
    - text: keep rows whose value contains the text (case-insensitive).

    Example: `ColumnFilter("n_linked", min=2)` keeps objects linked to at least two others;
    `ColumnFilter("object_type", values=["pallet"])` keeps the pallets.
    """

    column: str
    values: list[str | None] | None = None
    min: float | None = None
    max: float | None = None
    text: str | None = None


def filter_expression(schema: pl.Schema, flt: ColumnFilter) -> pl.Expr | None:
    """The polars expression of one column filter (None if the filter sets nothing).

    Args:
        schema: Schema of the profile (to treat timestamp columns as milliseconds).
        flt: The filter.

    Returns:
        pl.Expr | None: Boolean expression.

    Raises:
        ValueError: If the column cannot be filtered.
    """
    if flt.column not in FILTERABLE or flt.column not in schema:
        raise ValueError(f"cannot filter by {flt.column!r}")
    col = pl.col(flt.column)
    parts: list[pl.Expr] = []
    if flt.values is not None:
        known = [v for v in flt.values if v is not None]
        expr = col.cast(pl.String).is_in(known)
        parts.append(expr | col.is_null() if None in flt.values else expr.fill_null(False))
    if flt.min is not None or flt.max is not None:
        value = col.dt.epoch("ms") if schema[flt.column].is_temporal() else col.cast(pl.Float64)
        if flt.min is not None:
            parts.append(value >= flt.min)
        if flt.max is not None:
            parts.append(value <= flt.max)
    if flt.text:
        parts.append(col.cast(pl.String).str.to_lowercase().str.contains(flt.text.lower(), literal=True).fill_null(False))
    return pl.all_horizontal(parts) if parts else None


def query_rows(profile: pl.DataFrame, search: str = "", filters: Sequence[ColumnFilter] = ()) -> pl.DataFrame:
    """The rows of the profile matching the search and all column filters (unsorted).

    Args:
        profile: Output of `object_profile`.
        search: Words that must all occur (case-insensitive substrings) in the `search_text` of a row; empty = every row.
        filters: Column filters (see `ColumnFilter`).

    Returns:
        pl.DataFrame: The matching rows.
    """
    frame = profile.lazy()
    for flt in filters:
        expr = filter_expression(profile.schema, flt)
        if expr is not None:
            frame = frame.filter(expr)
    words = search.lower().split()
    if words:
        frame = (
            frame.with_columns(search_text())
            .filter(pl.all_horizontal(pl.col("_search").str.contains(word, literal=True) for word in words))
            .drop("_search")
        )
    return frame.collect()


def sort_rows(rows: pl.DataFrame, sort_by: str = c.OBJECT, descending: bool = False) -> pl.DataFrame:
    """Sort rows of the profile by one column, nulls last, ties by object id.

    Args:
        rows: Rows of the profile.
        sort_by: A column of `SORTABLE`.
        descending: Sort descending.

    Returns:
        pl.DataFrame: The sorted rows.

    Raises:
        ValueError: If `sort_by` is not sortable.
    """
    if sort_by not in SORTABLE:
        raise ValueError(f"cannot sort by {sort_by!r}")
    by = [sort_by] if sort_by == c.OBJECT else [sort_by, c.OBJECT]
    return rows.sort(by, descending=[descending] + [False] * (len(by) - 1), nulls_last=True)


def query_profile(
    profile: pl.DataFrame,
    search: str = "",
    sort_by: str = c.OBJECT,
    descending: bool = False,
    offset: int = 0,
    limit: int = 25,
    filters: Sequence[ColumnFilter] = (),
) -> tuple[pl.DataFrame, int]:
    """Search, filter, sort and page the profile.

    Args:
        profile: Output of `object_profile`.
        search: See `query_rows`.
        sort_by: A column of `SORTABLE`; nulls last, ties by object id.
        descending: Sort descending.
        offset: First row of the page (0-based).
        limit: Rows per page.
        filters: Column filters (see `ColumnFilter`).

    Returns:
        tuple[pl.DataFrame, int]: The rows of the page and the number of matching rows.

    Raises:
        ValueError: If `sort_by` is not sortable or a filter's column cannot be filtered.
    """
    if sort_by not in SORTABLE:
        raise ValueError(f"cannot sort by {sort_by!r}")
    matching = query_rows(profile, search, filters)
    return sort_rows(matching, sort_by, descending).slice(offset, limit), matching.height


def column_info(profile: pl.DataFrame) -> list[dict]:
    """What the column filters of the table offer: per filterable column its kind and its values or range.

    Kinds: `category` (string column with at most `MAX_CATEGORIES` distinct values: values with their number of
    rows, most frequent first, missing value as None), `text` (other string columns, and the object id), `number` and
    `time` (min and max; time in milliseconds since 1970-01-01 UTC).

    Args:
        profile: Output of `object_profile`.

    Returns:
        list[dict]: Entries with column, kind, values (list of (value, count) or None), min and max (or None).
    """
    info = []
    for name in FILTERABLE:
        dtype = profile.schema[name]
        series = profile[name]
        entry = {"column": name, "kind": "number", "values": None, "min": None, "max": None}
        if dtype == pl.String or dtype == pl.Categorical:
            counts = series.value_counts(sort=True)
            if counts.height <= MAX_CATEGORIES and name != c.OBJECT:
                pairs = sorted(counts.iter_rows(), key=lambda r: (-r[1], r[0] is None, r[0] or ""))
                entry.update(kind="category", values=[(v, int(n)) for v, n in pairs])
            else:
                entry["kind"] = "text"
        else:
            values = series.dt.epoch("ms") if dtype.is_temporal() else series.cast(pl.Float64)
            entry.update(kind="time" if dtype.is_temporal() else "number", min=values.min(), max=values.max())
        info.append(entry)
    return info


def export_frame(rows: pl.DataFrame, columns: Sequence[str]) -> pl.DataFrame:
    """The folded table for an export: the given columns (object always first) of the given rows, in their order.

    Values stay as stored: counts as integers, the lifespan in seconds, timestamps as datetimes.

    Args:
        rows: Rows of the profile (e.g. `sort_rows(query_rows(...))`).
        columns: Columns to export, in table order.

    Returns:
        pl.DataFrame: The export.

    Raises:
        ValueError: If a column cannot be exported.
    """
    wrong = [col for col in columns if col not in FILTERABLE]
    if wrong:
        raise ValueError(f"cannot export {', '.join(map(repr, wrong))}")
    return rows.select([c.OBJECT, *(col for col in dict.fromkeys(columns) if col != c.OBJECT)])


def object_details(frames: InstanceFrames, obj: str) -> dict:
    """What an unfolded row of the object profile shows for one object.

    Example (running example, p6): first event e026 produce, last e031 ship; activities produce, pick, inspect, pack,
    load, ship (1 each); linked objects t1 (e030, e031) and o1 (e028).

    Args:
        frames: Tables of the log.
        obj: The object.

    Returns:
        dict: first_event and last_event (event, activity, time; None without events), activities (activity and
        count, by count, then name) and linked (other object, its object type, the number of shared events and their
        ids in trace order; by count, then id).
    """
    trace = ordered_traces(frames, [obj])
    events = trace.select(c.EVENT, c.ACTIVITY, c.TIME)
    activities = (
        trace.group_by(c.ACTIVITY).len().sort(["len", c.ACTIVITY], descending=[True, False]).rename({"len": "count"})
    )
    linked = (
        frames.e2o.join(trace.select(c.EVENT, POS), on=c.EVENT)
        .filter(pl.col(c.OBJECT) != obj)
        .sort(POS)
        .group_by(c.OBJECT, maintain_order=True)
        .agg(pl.col(c.EVENT).alias("events"))
        .with_columns(pl.col("events").list.len().cast(pl.Int64).alias("count"))
        .join(frames.objects.unique(c.OBJECT, keep="first"), on=c.OBJECT, how="left")
        .sort(["count", c.OBJECT], descending=[True, False])
        .select(c.OBJECT, c.OBJECT_TYPE, "count", "events")
    )
    return {
        "first_event": events.head(1).to_dicts()[0] if events.height else None,
        "last_event": events.tail(1).to_dicts()[0] if events.height else None,
        "activities": activities.to_dicts(),
        "linked": linked.to_dicts(),
    }
