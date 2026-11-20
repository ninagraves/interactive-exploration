"""Step 7: the whole directly-follows graph, as the response of the page's route.

`directly_follows_graph` runs the steps on plain frames (usable in notebooks and tests);
`log_frames` reads these frames from an OCEL.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass

import polars as pl
from ocelescope import OCEL
from pydantic import BaseModel, Field

from . import columns as c
from .arcs import (
    KEY,
    arc_count_filter,
    arc_share_filter,
    arcs_per_type,
    directly_follows_arcs,
    objects_per_type,
    remove_arcs,
)
from .connectivity import CONNECTING, stay_connected
from .nodes import activity_frequencies, involved_object_types, shown_activities
from .projection import default_activities, project_traces, selected_type_event_counts, type_activity_counts
from .traces import considered_objects, object_traces
from .variants import (
    RANK,
    activity_variant_thresholds,
    added_activity_thresholds,
    object_variants,
    variant_filter,
    variant_ranking,
)

#: Number of object types selected by default: the ones with the most objects (Nina, 2026-11-20).
DEFAULT_OBJECT_TYPES = 5
#: Default arc threshold ("Arcs (projection)") in percent (as in the location module).
DEFAULT_ARC_THRESHOLD = 50.0
#: Default variant threshold in percent, for all selected types (as in the location module).
DEFAULT_VARIANT_THRESHOLD = 80.0
#: Default of "Stay connected".
DEFAULT_STAY_CONNECTED = True


class TypeSetting(BaseModel):
    """Settings of one selected object type.

    Attributes:
        object_type: The object type.
        variant_threshold: Variant threshold in percent (`variants.py`); 100 = all variants; None = the default
            (`DEFAULT_VARIANT_THRESHOLD`).
        arc_threshold: Arc threshold in percent (`arcs.arc_share_filter`); 100 = all arcs.
        arc_count: Arc count (`arcs.arc_count_filter`); None = all arcs.
    """

    object_type: str
    variant_threshold: float | None = Field(None, ge=0, le=100)
    arc_threshold: float = Field(DEFAULT_ARC_THRESHOLD, ge=0, le=100)
    arc_count: int | None = Field(None, ge=0)


class TypeThresholds(BaseModel):
    """Settings of one object type that deviate from the general ones (None = use the general one).

    Attributes:
        object_type: The object type.
        variant_threshold: Own variant threshold in percent, or None.
        arc_threshold: Own arc threshold in percent, or None (Python use; the page applies arc settings itself).
        arc_count: Own arc count, or None (Python use).
    """

    object_type: str
    variant_threshold: float | None = Field(None, ge=0, le=100)
    arc_threshold: float | None = Field(None, ge=0, le=100)
    arc_count: int | None = Field(None, ge=0)


class ArcKey(BaseModel):
    """An arc, identified by its object type and endpoints.

    Attributes:
        object_type: The object type.
        source: Source activity; None = the start node of the object type.
        target: Target activity; None = the end node of the object type.
    """

    object_type: str
    source: str | None = None
    target: str | None = None


class DfgRequest(BaseModel):
    """Settings of the page (sidebar) that need the backend: object types, variants, activities.

    The page applies the arc settings (arc threshold, arc count, arcs removed by hand, Stay connected) itself, in the
    browser (`frontend-modules/interactive-dfg/src/lib/dfgArcs.ts`): the route answers with all arcs
    of the included traces. The arc fields below are for use from Python (`resolve_selection`, notebooks) and ignored
    by the route.

    Attributes:
        object_types: The selected object types; None = the default, the `DEFAULT_OBJECT_TYPES` (5) object types with the
            most objects (`default_selection`).
        variant_threshold: General variant threshold in percent, for every type without an own one; None = the
            default (`DEFAULT_VARIANT_THRESHOLD`).
        arc_threshold: General arc threshold in percent, for every type without an own one.
        arc_count: General arc count per type, for every type without an own one; None = all arcs.
        type_thresholds: Own settings of single object types (kept also while the type is not selected).
        activities: Selected activities per object type (`projection.py`); the events of all other activities
            are removed from the type's traces first. A type that is missing gets the default
            (`projection.default_activities`).
        stay_connected: Connectivity repair on (`connectivity.stay_connected`).
        removed_arcs: Arcs removed by hand (double click on the arc).
    """

    object_types: list[str] | None = None
    variant_threshold: float | None = Field(None, ge=0, le=100)
    arc_threshold: float = Field(DEFAULT_ARC_THRESHOLD, ge=0, le=100)
    arc_count: int | None = Field(None, ge=0)
    type_thresholds: list[TypeThresholds] = Field(default_factory=list)
    activities: dict[str, list[str]] = Field(default_factory=dict)
    stay_connected: bool = DEFAULT_STAY_CONNECTED
    removed_arcs: list[ArcKey] = Field(default_factory=list)


class DfgObjectType(BaseModel):
    """An object type of the log, with what the graph shows of it.

    Attributes:
        object_type: The object type.
        objects: Number of objects of the type.
        selected: True if the type's arcs are shown.
        variant_threshold: Variant threshold used (percent), for selected types.
        kept_objects: Objects whose variant is kept (selected types; 0 otherwise).
        variants: Distinct variants of the type's objects, after the projection (selected types; 0 otherwise).
        kept_variants: Variants kept by the variant threshold.
        arc_threshold: Arc threshold used (percent), for selected types.
        arc_count: Arc count used (None = all), for selected types.
        arcs: Arcs after the variant filter (with start and end arcs).
        threshold_arcs: Arcs left by the arc threshold (the arc count slider counts these).
        shown_arcs: Arcs shown (after arc count, hand removals and the connectivity repair).
    """

    object_type: str
    objects: int
    selected: bool
    variant_threshold: float = 100.0
    kept_objects: int = 0
    variants: int = 0
    kept_variants: int = 0
    arc_threshold: float = DEFAULT_ARC_THRESHOLD
    arc_count: int | None = None
    arcs: int = 0
    threshold_arcs: int = 0
    shown_arcs: int = 0


class DfgTypeCount(BaseModel):
    """Events of an activity node that involve an object type.

    Attributes:
        object_type: The object type.
        events: Counted events of the activity that involve at least one object of the type.
        objects: Distinct objects of the type in these events.
    """

    object_type: str
    events: int
    objects: int


class DfgActivity(BaseModel):
    """An activity node.

    Attributes:
        activity: The activity.
        events: Frequency: events of the activity in the traces of the kept objects (`nodes.py`).
        log_events: All events of the activity in the log.
        object_types: Object types involved in the counted events, most events first.
    """

    activity: str
    events: int
    log_events: int
    object_types: list[DfgTypeCount]


class DfgArc(BaseModel):
    """A kept arc.

    Attributes:
        object_type: The object type whose objects traverse it.
        source: Source activity; None = the start node of the object type.
        target: Target activity; None = the end node of the object type.
        count: Traversals.
        objects: Distinct objects traversing it.
        rank: Position (1 = first) in the arc ranking of its type (`arcs.arc_order`: objects, traversals, first
            occurrence, source, target), among all arcs of the included traces.
        connecting: True if it is shown only because of "Stay connected".
    """

    object_type: str
    source: str | None
    target: str | None
    count: int
    objects: int
    rank: int = 0
    connecting: bool = False


class DfgActivityTypeOption(BaseModel):
    """An activity for one object type, in the unfold of the activity list.

    Attributes:
        object_type: The object type.
        events: Events of the activity with at least one object of the type (`projection.type_activity_counts`).
        selected_type: True if the object type is selected (only then can the activity be (de)selected for it).
        included: True if the activity is selected for this (selected) type; False for unselected types.
        on_included_trace: True if it is on an included trace of the type (projected, variant-filtered).
        variant_threshold_needed: Smallest whole variant threshold of the type that puts it on an included trace
            (`variants.activity_variant_thresholds`); for a deselected activity: the one it would need if it were
            selected (`variants.added_activity_thresholds`). For an activity without events of a selected type also for an
            unselected type: the one it would need if the type were selected with its default activities
            (`unselected_type_thresholds`). None otherwise for an unselected type.
        variant_threshold_needed_exact: The same with up to `variants.EXACT_DECIMALS` decimals (e.g. 66.667 for
            2 of 3 objects covered before it), shown when the activity is unfolded.
    """

    object_type: str
    events: int
    selected_type: bool
    included: bool
    on_included_trace: bool = False
    variant_threshold_needed: float | None = None
    variant_threshold_needed_exact: float | None = None


class DfgActivityOption(BaseModel):
    """An activity of the log, for the activity selection.

    Attributes:
        activity: The activity.
        selected_events: Its events that involve at least one object of a selected type (the list is sorted by this,
            descending).
        log_events: All its events in the log.
        object_types: Per object type with events of the activity: its events and whether the activity is selected
            for it; selected types first, then by events.
        on_included_trace: True if it is on an included trace of a selected type (the upper part of the list).
        variant_threshold_needed: Smallest of the types' `variant_threshold_needed` (None if none).
        variant_threshold_needed_exact: Smallest of the types' `variant_threshold_needed_exact` (None if none).
        easiest_type: The object type with that smallest exact threshold (ties: selected types first, then most
            events, then name); for an activity without events of a selected type (`selected_events` 0) it may be an
            unselected type: the type for which it is "easiest" to include the activity (third part of the list).
    """

    activity: str
    selected_events: int
    log_events: int
    object_types: list[DfgActivityTypeOption]
    on_included_trace: bool = False
    variant_threshold_needed: float | None = None
    variant_threshold_needed_exact: float | None = None
    easiest_type: str | None = None


class DirectlyFollowsGraph(BaseModel):
    """The page's graph.

    Attributes:
        object_types: All object types of the log, most objects first (the order of their colours).
        activities: The shown activity nodes, by name.
        arcs: The shown arcs.
        activity_options: All activities of the log, most events first, for the activity selection.
        variant_default: The default variant threshold of the selection (percent).
        arc_count_max: Largest number of arcs of one selected type left by the arc threshold (slider maximum).
        removed_arcs: The arcs removed by hand that exist in the current graph's traces, with their counts.
    """

    object_types: list[DfgObjectType]
    activities: list[DfgActivity]
    arcs: list[DfgArc]
    activity_options: list[DfgActivityOption]
    variant_default: float = DEFAULT_VARIANT_THRESHOLD
    arc_count_max: int = 0
    removed_arcs: list[DfgArc] = Field(default_factory=list)


@dataclass(frozen=True)
class LogFrames:
    """The frames the graph is computed from.

    Attributes:
        e2o: Columns event, object, object_type (all objects; each pair once).
        events: Columns event, time, activity.
        objects: Columns object, object_type (all objects).
        type_activities: `projection.type_activity_counts` (None = computed when needed).
    """

    e2o: pl.DataFrame
    events: pl.DataFrame
    objects: pl.DataFrame
    type_activities: pl.DataFrame | None = None


def log_frames(ocel: OCEL) -> LogFrames:
    """Read the frames for the graph from the log (Ocelescope's DuckDB tables, read as lazy polars frames).

    Args:
        ocel: The log.

    Returns:
        LogFrames: The frames.
    """
    objects = ocel.objects.pl.select(c.OCEL_OID, c.OCEL_TYPE).collect().rename({c.OCEL_OID: c.OBJECT, c.OCEL_TYPE: c.OBJECT_TYPE})
    e2o = (
        ocel.e2o.pl.select(c.OCEL_EID, c.OCEL_OID)
        .unique()
        .collect()
        .rename({c.OCEL_EID: c.EVENT, c.OCEL_OID: c.OBJECT})
        .join(objects, on=c.OBJECT)
    )
    events = (
        ocel.events.pl.select(c.OCEL_EID, c.OCEL_TIMESTAMP, c.OCEL_ACTIVITY)
        .collect()
        .rename({c.OCEL_EID: c.EVENT, c.OCEL_TIMESTAMP: c.TIME, c.OCEL_ACTIVITY: c.ACTIVITY})
    )
    return LogFrames(e2o=e2o, events=events, objects=objects, type_activities=type_activity_counts(e2o, events, objects))


def default_selection(objects: pl.DataFrame, n: int = DEFAULT_OBJECT_TYPES) -> list[TypeSetting]:
    """The default selection: the `n` object types with the most objects (ties by name), with the default thresholds.

    Example: order (2000), item (8000), package (1500), customer (300), product (40), employee (12): item, order,
    package, customer, product.

    Args:
        objects: All objects, columns object and object_type.
        n: Number of object types (default `DEFAULT_OBJECT_TYPES` = 5; all if the log has fewer).

    Returns:
        list[TypeSetting]: One setting per selected type, most objects first.
    """
    return [TypeSetting(object_type=t) for t in type_overview(objects)[c.OBJECT_TYPE].head(n)]


def resolve_selection(request: DfgRequest, objects: pl.DataFrame) -> list[TypeSetting]:
    """The selected object types with the settings that apply to them.

    Args:
        request: The page's settings.
        objects: All objects, columns object and object_type.

    Returns:
        list[TypeSetting]: One setting per selected type: its own values where given, else the general ones.
    """
    types = request.object_types
    if types is None:
        types = [s.object_type for s in default_selection(objects)]
    own = {t.object_type: t for t in request.type_thresholds}

    def pick(t: str, name: str):
        """The own value of type `t` for setting `name`, else the general one."""
        value = getattr(own[t], name) if t in own else None
        return getattr(request, name) if value is None else value

    return [
        TypeSetting(
            object_type=t,
            variant_threshold=pick(t, "variant_threshold"),
            arc_threshold=pick(t, "arc_threshold"),
            arc_count=pick(t, "arc_count"),
        )
        for t in dict.fromkeys(types)
    ]


def type_overview(objects: pl.DataFrame) -> pl.DataFrame:
    """All object types with their number of objects.

    Args:
        objects: All objects, columns object and object_type.

    Returns:
        pl.DataFrame: Columns object_type, objects; most objects first, then by type.
    """
    return (
        objects.group_by(c.OBJECT_TYPE)
        .agg(pl.len().cast(pl.Int64).alias(c.OBJECTS))
        .sort([c.OBJECTS, c.OBJECT_TYPE], descending=[True, False])
    )


@dataclass(frozen=True)
class IncludedTraces:
    """The results of steps 1 to 3 (`included_traces`).

    Attributes:
        type_activities: `projection.type_activity_counts` of the log.
        included: Selected type -> its selected activities (defaults filled in).
        unprojected: Traces of the selected types before the activity projection.
        variants: The variants of the projected traces (`variants.object_variants`).
        variant_thresholds: Selected type -> the variant threshold used.
        kept: The included traces: projected and variant-filtered (`traces.object_traces` columns).
    """

    type_activities: pl.DataFrame
    included: dict[str, list[str]]
    unprojected: pl.DataFrame
    variants: pl.DataFrame
    variant_thresholds: dict[str, float]
    kept: pl.DataFrame


def included_traces(
    frames: LogFrames,
    selection: Sequence[TypeSetting],
    traces: pl.DataFrame | None = None,
    activities: Mapping[str, Collection[str]] | None = None,
) -> IncludedTraces:
    """Steps 1 to 3: traces of the selected types, activity projection, variant filter.

    Shared by `directly_follows_graph` and the export (`export.py`), so both use the same included traces.

    Args:
        frames: The log's frames.
        selection: Selected object types with settings.
        traces: Precomputed `object_traces` of the selected types; None = compute them.
        activities: Selected activities per object type; a missing type gets `projection.default_activities`.

    Returns:
        IncludedTraces: The intermediate results.
    """
    settings = {s.object_type: s for s in selection}
    if traces is None:
        traces = selected_traces(frames, list(settings))
    type_activities = frames.type_activities
    if type_activities is None:
        type_activities = type_activity_counts(frames.e2o, frames.events, frames.objects)
    included = default_activities(type_activities, [t for t in settings if t not in (activities or {})])
    included.update({t: list(a) for t, a in (activities or {}).items() if t in settings})
    projected = project_traces(traces, included)
    variants = object_variants(projected)
    variant_thresholds = {
        t: DEFAULT_VARIANT_THRESHOLD if s.variant_threshold is None else s.variant_threshold for t, s in settings.items()
    }
    return IncludedTraces(
        type_activities=type_activities,
        included=included,
        unprojected=traces,
        variants=variants,
        variant_thresholds=variant_thresholds,
        kept=variant_filter(projected, variant_thresholds),
    )


def directly_follows_graph(
    frames: LogFrames,
    selection: Sequence[TypeSetting] | None = None,
    traces: pl.DataFrame | None = None,
    activities: Mapping[str, Collection[str]] | None = None,
    stay: bool = DEFAULT_STAY_CONNECTED,
    removed: Collection[tuple[str, str | None, str | None]] = (),
    arc_total: int | None = None,
) -> DirectlyFollowsGraph:
    """The directly-follows graph of the selected object types.

    Order of the steps: projection (the events of deselected activities are removed from the
    traces, per object type), variant filter, arcs, arc threshold, arc count, hand removals, connectivity repair
    ("Stay connected"), nodes. The kept (projected, variant-filtered) traces are the baseline of everything after
    the variant filter: arcs, frequencies and the object types involved are computed on their events only.

    Args:
        frames: The log's frames (`log_frames`).
        selection: Selected object types with settings; None = `default_selection`.
        traces: Precomputed `object_traces` of the selected types (e.g. from a cache); None = compute them.
        activities: Selected activities per object type (`projection.project_traces`); a selected type that is
            missing gets `projection.default_activities`; None = all defaults.
        stay: "Stay connected": every shown arc lies on a start-to-end path (`connectivity.stay_connected`).
        removed: Arcs removed by hand, as (object type, source, target).
        arc_total: Arcs (display) in "general" mode: one limit shared by the types without an own arc count
            (`arcs.arc_count_filter`); None = per type.

    Returns:
        DirectlyFollowsGraph: Object types, activity nodes and shown arcs.
    """
    if selection is None:
        selection = default_selection(frames.objects)
    settings = {s.object_type: s for s in selection}
    steps = included_traces(frames, selection, traces, activities)
    type_activities, included = steps.type_activities, steps.included
    unprojected, variants, variant_thresholds = steps.unprojected, steps.variants, steps.variant_thresholds
    kept_traces = steps.kept
    n_kept = objects_per_type(kept_traces)
    all_arcs = directly_follows_arcs(kept_traces).with_columns(
        pl.int_range(1, pl.len() + 1).over(c.OBJECT_TYPE).alias(RANK)
    )
    threshold_arcs = arc_share_filter(all_arcs, {t: s.arc_threshold for t, s in settings.items()})
    counted_arcs = arc_count_filter(threshold_arcs, {t: s.arc_count for t, s in settings.items()}, arc_total)
    removed = list(removed)
    kept_arcs = remove_arcs(counted_arcs, removed)
    if stay:
        shown_arcs = stay_connected(remove_arcs(all_arcs, removed), kept_arcs)
    else:
        shown_arcs = kept_arcs.with_columns(pl.lit(False).alias(CONNECTING))

    shown = shown_activities(shown_arcs)
    frequencies = activity_frequencies(kept_traces, shown)
    involved = involved_object_types(kept_traces, shown, frames.e2o)
    log_counts = frames.events.group_by(c.ACTIVITY).agg(pl.len().alias(c.EVENTS))
    log_events = dict(zip(log_counts[c.ACTIVITY], log_counts[c.EVENTS], strict=True))
    on_trace = {(t, a) for t, a in kept_traces.select(c.OBJECT_TYPE, c.ACTIVITY).unique().iter_rows()}
    needed = {(t, a): (v, x) for t, a, v, x in activity_variant_thresholds(variant_ranking(variants)).iter_rows()}
    # Deselected activities: the variant threshold they would need if selected.
    needed.update({(t, a): (v, x) for t, a, v, x in added_activity_thresholds(unprojected, variants, included).iter_rows()})
    # Activities without events of a selected type: also the threshold for every unselected type.
    selected_counts = selected_type_event_counts(frames.e2o, frames.events, frames.objects, list(settings))
    without = {a for a in log_events if selected_counts.get(a, 0) == 0}
    if without:
        others = unselected_type_thresholds(frames, type_activities, without, list(settings))
        needed.update({(t, a): (v, x) for t, a, v, x in others.iter_rows()})
    activity_options = _activity_options(type_activities, selected_counts, log_events, included, on_trace, needed)

    kept_variants = object_variants(kept_traces)
    n_variants = _count_per_type(variants.unique([c.OBJECT_TYPE, c.VARIANT]))
    n_kept_variants = _count_per_type(kept_variants.unique([c.OBJECT_TYPE, c.VARIANT]))
    arcs_before = arcs_per_type(all_arcs)
    arcs_threshold = arcs_per_type(threshold_arcs)
    arcs_shown = arcs_per_type(shown_arcs)
    removed_keys = pl.DataFrame(removed, schema={c.OBJECT_TYPE: pl.String, c.SOURCE: pl.String, c.TARGET: pl.String}, orient="row")
    removed_rows = all_arcs.join(removed_keys, on=KEY, how="semi", nulls_equal=True)

    def type_row(row: dict) -> DfgObjectType:
        """The object type of a `type_overview` row, with its numbers if it is selected."""
        t = row[c.OBJECT_TYPE]
        extra = {}
        if t in settings:
            extra = {
                "variant_threshold": round(variant_thresholds[t], 2),
                "kept_objects": n_kept.get(t, 0),
                "variants": n_variants.get(t, 0),
                "kept_variants": n_kept_variants.get(t, 0),
                "arc_threshold": settings[t].arc_threshold,
                "arc_count": settings[t].arc_count,
                "arcs": arcs_before.get(t, 0),
                "threshold_arcs": arcs_threshold.get(t, 0),
                "shown_arcs": arcs_shown.get(t, 0),
            }
        return DfgObjectType(object_type=t, objects=row[c.OBJECTS], selected=t in settings, **extra)

    by_activity: dict[str, list[DfgTypeCount]] = {}
    for row in involved.iter_rows(named=True):
        by_activity.setdefault(row[c.ACTIVITY], []).append(
            DfgTypeCount(object_type=row[c.OBJECT_TYPE], events=row[c.EVENTS], objects=row[c.OBJECTS])
        )
    arc_fields = [*KEY, c.COUNT, c.OBJECTS, RANK]
    return DirectlyFollowsGraph(
        object_types=[type_row(row) for row in type_overview(frames.objects).iter_rows(named=True)],
        activities=[
            DfgActivity(
                activity=row[c.ACTIVITY],
                events=row[c.EVENTS],
                log_events=log_events.get(row[c.ACTIVITY], 0),
                object_types=by_activity.get(row[c.ACTIVITY], []),
            )
            for row in frequencies.iter_rows(named=True)
        ],
        arcs=[DfgArc(**row) for row in shown_arcs.select(*arc_fields, CONNECTING).iter_rows(named=True)],
        activity_options=activity_options,
        variant_default=DEFAULT_VARIANT_THRESHOLD,
        arc_count_max=max(arcs_threshold.values(), default=0),
        removed_arcs=[DfgArc(**row) for row in removed_rows.select(arc_fields).iter_rows(named=True)],
    )


def _activity_options(
    type_activities: pl.DataFrame,
    selected_counts: Mapping[str, int],
    log_events: Mapping[str, int],
    included: Mapping[str, Collection[str]],
    on_trace: Collection[tuple[str, str]] = (),
    needed: Mapping[tuple[str, str], tuple[float, float]] | None = None,
) -> list[DfgActivityOption]:
    """The activity list of the sidebar: every activity with its events of selected types and its counts per type.

    Args:
        type_activities: `projection.type_activity_counts`.
        selected_counts: Activity -> its events with an object of a selected type (`projection.selected_type_event_counts`).
        log_events: Activity -> all its events.
        included: Selected object type -> its selected activities.
        on_trace: (object type, activity) pairs on an included trace.
        needed: (object type, activity) -> (smallest whole variant threshold, smallest threshold with
            `variants.EXACT_DECIMALS` decimals) that puts it on an included trace.

    Returns:
        list[DfgActivityOption]: Most events of selected types first, then most events in the log, then by name.
    """
    per_activity: dict[str, list[DfgActivityTypeOption]] = {}
    for row in type_activities.iter_rows(named=True):
        t = row[c.OBJECT_TYPE]
        need = (needed or {}).get((t, row[c.ACTIVITY]))
        per_activity.setdefault(row[c.ACTIVITY], []).append(
            DfgActivityTypeOption(
                object_type=t,
                events=row[c.EVENTS],
                selected_type=t in included,
                included=row[c.ACTIVITY] in set(included.get(t, ())),
                on_included_trace=(t, row[c.ACTIVITY]) in on_trace,
                variant_threshold_needed=need[0] if need else None,
                variant_threshold_needed_exact=need[1] if need else None,
            )
        )

    def option(a: str, n: int) -> DfgActivityOption:
        """The list entry of activity `a` with `n` events in the log."""
        types = sorted(per_activity.get(a, []), key=lambda o: (not o.selected_type, -o.events, o.object_type))
        values = [o.variant_threshold_needed for o in types if o.variant_threshold_needed is not None]
        exact = [o.variant_threshold_needed_exact for o in types if o.variant_threshold_needed_exact is not None]
        # Easiest type: the smallest exact threshold; ties: selected types first, then most events, then name.
        candidates = [o for o in types if o.variant_threshold_needed_exact is not None]
        easiest = min(candidates, key=lambda o: (o.variant_threshold_needed_exact, not o.selected_type, -o.events, o.object_type), default=None)
        return DfgActivityOption(
            activity=a,
            selected_events=selected_counts.get(a, 0),
            log_events=n,
            object_types=types,
            on_included_trace=any(o.on_included_trace for o in types),
            variant_threshold_needed=min(values) if values else None,
            variant_threshold_needed_exact=min(exact) if exact else None,
            easiest_type=easiest.object_type if easiest is not None else None,
        )

    options = [option(a, n) for a, n in log_events.items()]
    return sorted(options, key=lambda o: (-o.selected_events, -o.log_events, o.activity))


def unselected_type_thresholds(
    frames: LogFrames, type_activities: pl.DataFrame, activities: Collection[str], selected: Collection[str]
) -> pl.DataFrame:
    """For activities without events of a selected type: the variant threshold each unselected type would need.

    Per unselected object type $ot$ with events of such an activity $a$: $ot$ as if it were selected with its default
    activities (`projection.default_activities`); $a$ needs `variants.activity_variant_thresholds` if it is one of
    these defaults, else `variants.added_activity_thresholds` (the defaults plus $a$). The third part of the activity
    list names the type for which such an activity is easiest to include.
    Example (test_activities_without_selected_events_name_the_easiest_type): operators o2 (tea, train), o3 (train,
    handover), o1 (inspect, ..., break), one object each, ranked in this order; "break" is not a default of operator,
    so it is added for o1, whose variant has 2 of 3 operators before it -> 66.667 %.

    Args:
        frames: The log's frames.
        type_activities: `projection.type_activity_counts`.
        activities: The activities without events of a selected type.
        selected: The selected object types (left out).

    Returns:
        pl.DataFrame: Columns object_type, activity, needed, needed_exact (as `variants.activity_variant_thresholds`),
        only the given activities of unselected types.
    """
    schema = {c.OBJECT_TYPE: pl.String, c.ACTIVITY: pl.String, "needed": pl.Float64, "needed_exact": pl.Float64}
    types = (
        type_activities.filter(pl.col(c.ACTIVITY).is_in(list(activities)) & ~pl.col(c.OBJECT_TYPE).is_in(list(selected)))[c.OBJECT_TYPE]
        .unique()
        .sort()
        .to_list()
    )
    if not types:
        return pl.DataFrame(schema=schema)
    traces = selected_traces(frames, types)
    included = default_activities(type_activities, types)
    variants = object_variants(project_traces(traces, included))
    own = activity_variant_thresholds(variant_ranking(variants)).select(
        c.OBJECT_TYPE, c.ACTIVITY, pl.col("needed").cast(pl.Float64), pl.col("needed_exact").cast(pl.Float64)
    )
    return (
        pl.concat([own, added_activity_thresholds(traces, variants, included)])
        .filter(pl.col(c.ACTIVITY).is_in(list(activities)))
        .sort(c.OBJECT_TYPE, c.ACTIVITY)
    )


def selected_traces(frames: LogFrames, object_types: Collection[str]) -> pl.DataFrame:
    """The traces of all objects of the given object types (step 1).

    Args:
        frames: The log's frames.
        object_types: The selected object types.

    Returns:
        pl.DataFrame: `traces.object_traces` of these objects.
    """
    return object_traces(frames.e2o, frames.events, considered_objects(frames.objects, object_types))


def _count_per_type(frame: pl.DataFrame) -> dict[str, int]:
    """Number of rows per object type.

    Args:
        frame: Frame with the column object_type.

    Returns:
        dict[str, int]: object type -> rows.
    """
    counts = frame.group_by(c.OBJECT_TYPE).len()
    return dict(zip(counts[c.OBJECT_TYPE], counts["len"], strict=True))
