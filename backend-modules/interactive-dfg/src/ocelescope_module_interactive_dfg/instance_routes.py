"""API routes of the page "Instances" (documented in `docs/pages/instances.md`).

The log's tables and its object profile are cached (small LRU per process, `dfg_routes._cached`), keyed by the log
id and the log version (`dfg_routes.log_version`), so that paging, sorting and filtering the table only rerun the
cheap query step.
"""

from collections import OrderedDict
from datetime import datetime
from typing import Literal

import polars as pl
from fastapi import APIRouter, HTTPException
from ocelescope import OCEL
from ocelescope.resource.default.ocel_mapping import OCELMapping
from ocelescope_backend.app.dependencies import ApiOcel, ApiSession
from pydantic import BaseModel, Field

from ocelescope_module_interactive_dfg.dfg import columns as c
from ocelescope_module_interactive_dfg.dfg_routes import _cached, log_version
from ocelescope_module_interactive_dfg.instances.frames import InstanceFrames, instance_frames
from ocelescope_module_interactive_dfg.instances.object_graph import object_graph
from ocelescope_module_interactive_dfg.instances.profile import (
    ColumnFilter,
    column_info,
    export_frame,
    object_details,
    object_profile,
    query_profile,
    query_rows,
    sort_rows,
)
from ocelescope_module_interactive_dfg.instances.traces import object_traces

router = APIRouter()

#: Caches: tables, object profile and filter options per (log id, log version).
_instance_frames: OrderedDict[tuple[str, str], InstanceFrames] = OrderedDict()
_profiles: OrderedDict[tuple[str, str], pl.DataFrame] = OrderedDict()
_column_infos: OrderedDict[tuple[str, str], list[dict]] = OrderedDict()

#: Columns the table can sort, filter and export by (`profile.SORTABLE`).
ProfileColumn = Literal[
    "object",
    "object_type",
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
]


def _key(session: ApiSession, ocel_id: str) -> tuple[str, str]:
    """Cache key of a log: (log id, log version)."""
    return (ocel_id, log_version(session, ocel_id))


def _frames(session: ApiSession, ocel_id: str, ocel: OCEL) -> InstanceFrames:
    """The log's tables (cached)."""
    return _cached(_instance_frames, _key(session, ocel_id), lambda: instance_frames(ocel))


def _profile(session: ApiSession, ocel_id: str, ocel: OCEL) -> pl.DataFrame:
    """The log's object profile (cached)."""
    return _cached(_profiles, _key(session, ocel_id), lambda: object_profile(_frames(session, ocel_id, ocel)))


class ProfileRow(BaseModel):
    """One row of the object profile (see `instances.profile.object_profile`; lifespan in seconds)."""

    object: str
    object_type: str | None = None
    n_events: int = 0
    n_timestamps: int = 0
    first: datetime | None = None
    last: datetime | None = None
    lifespan: float | None = None
    first_activity: str | None = None
    last_activity: str | None = None
    n_activities: int = 0
    n_shared_events: int = 0
    n_linked: int = 0


class ColumnInfo(BaseModel):
    """What the filter of one column offers (see `instances.profile.column_info`)."""

    column: ProfileColumn
    kind: Literal["category", "text", "number", "time"]
    values: list[tuple[str | None, int]] | None = None
    min: float | None = None
    max: float | None = None


class ProfilePage(BaseModel):
    """A page of the object profile.

    Attributes:
        rows: The rows of the page.
        total: Rows matching search and filters.
        objects: All objects of the log.
        columns: Filter options per column (values or range over all objects).
    """

    rows: list[ProfileRow]
    total: int
    objects: int
    columns: list[ColumnInfo]


class ProfileFilter(BaseModel):
    """A column filter of the table (see `instances.profile.ColumnFilter`)."""

    column: ProfileColumn
    values: list[str | None] | None = None
    min: float | None = None
    max: float | None = None
    text: str | None = None


class ProfileQuery(BaseModel):
    """Search, column filters, sorting and page of the object profile table."""

    search: str = ""
    filters: list[ProfileFilter] = Field(default_factory=list)
    sort_by: ProfileColumn = "object"
    descending: bool = False
    offset: int = 0
    limit: int = 25


class ProfileExportRequest(ProfileQuery):
    """The table as shown, for an export: all matching rows (not only the page), the shown columns.

    Attributes:
        columns: Shown columns in table order (object is always included).
        name: Name of the saved resource (save to session only).
    """

    columns: list[ProfileColumn]
    name: str = "Object profile"


class ProfileCsv(BaseModel):
    """A CSV export of the table."""

    file_name: str
    content: str
    rows: int


class SavedResource(BaseModel):
    """A resource saved to the session."""

    id: str
    name: str
    rows: int


def _filters(query: ProfileQuery) -> list[ColumnFilter]:
    """The column filters of a query as `ColumnFilter`s."""
    return [ColumnFilter(**f.model_dump()) for f in query.filters]


def _shown_rows(profile: pl.DataFrame, request: ProfileExportRequest) -> pl.DataFrame:
    """All rows matching the request, sorted, with the shown columns (the folded table as shown).

    Raises:
        HTTPException: 422 if a column cannot be filtered, sorted or exported.
    """
    try:
        rows = sort_rows(query_rows(profile, request.search, _filters(request)), request.sort_by, request.descending)
        return export_frame(rows, request.columns)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.post("/{ocel_id}/instances/profile", operation_id="getObjectProfile")
def get_object_profile(ocel_id: str, ocel: ApiOcel, session: ApiSession, query: ProfileQuery) -> ProfilePage:
    """A page of the object profile, searched, filtered by column and sorted."""
    profile = _profile(session, ocel_id, ocel)
    try:
        page, total = query_profile(profile, query.search, query.sort_by, query.descending, query.offset, query.limit, _filters(query))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    infos = _cached(_column_infos, _key(session, ocel_id), lambda: column_info(profile))
    return ProfilePage(
        rows=[ProfileRow(**row) for row in page.to_dicts()],
        total=total,
        objects=profile.height,
        columns=[ColumnInfo(**info) for info in infos],
    )


@router.post("/{ocel_id}/instances/profile/csv", operation_id="exportObjectProfileCsv")
def export_object_profile_csv(ocel_id: str, ocel: ApiOcel, session: ApiSession, request: ProfileExportRequest) -> ProfileCsv:
    """The table as shown (all matching rows, shown columns, folded) as CSV text."""
    frame = _shown_rows(_profile(session, ocel_id, ocel), request)
    return ProfileCsv(file_name="object_profile.csv", content=frame.write_csv(), rows=frame.height)


@router.post("/{ocel_id}/instances/profile/save", operation_id="saveObjectProfile")
def save_object_profile(ocel_id: str, ocel: ApiOcel, session: ApiSession, request: ProfileExportRequest) -> SavedResource:
    """Save the table as shown to the session as an Ocelescope "OCEL Mapping" resource.

    The objects are its objects (column ocel:oid), the shown columns its values; events, e2o and o2o stay empty.
    """
    frame = _shown_rows(_profile(session, ocel_id, ocel), request).rename({c.OBJECT: "ocel:oid"})
    mapping = OCELMapping()
    mapping.objects = frame
    name = request.name.strip() or "Object profile"
    return SavedResource(id=session.add_resource(mapping, name), name=name, rows=frame.height)


class DetailEvent(BaseModel):
    """An event in the details of an object."""

    event: str
    activity: str | None = None
    time: datetime | None = None


class ActivityCount(BaseModel):
    """An activity with its number of events."""

    activity: str | None = None
    count: int


class LinkedObject(BaseModel):
    """Another object sharing events with the object."""

    object: str
    object_type: str | None = None
    count: int
    events: list[str]


class ObjectDetails(BaseModel):
    """What an unfolded row of the object profile shows (see `instances.profile.object_details`)."""

    object: str
    first_event: DetailEvent | None = None
    last_event: DetailEvent | None = None
    activities: list[ActivityCount]
    linked: list[LinkedObject]


@router.get("/{ocel_id}/instances/details", operation_id="getObjectDetails")
def get_object_details(ocel_id: str, ocel: ApiOcel, session: ApiSession, object: str) -> ObjectDetails:  # noqa: A002
    """Details of one object for its unfolded row in the object profile."""
    frames = _frames(session, ocel_id, ocel)
    if frames.objects.filter(pl.col(c.OBJECT) == object).is_empty():
        raise HTTPException(status_code=404, detail=f"Not an object of this log: {object}.")
    return ObjectDetails(object=object, **object_details(frames, object))


class SelectionRequest(BaseModel):
    """The selected objects (in the order of the selection)."""

    objects: list[str]


class ObjectGraphNode(BaseModel):
    """A node of the object graph (see `instances.object_graph.ObjectGraph`)."""

    node: str
    object_type: str | None = None
    role: str
    n_events: int
    n_shared: int | None = None


class ArcEvent(BaseModel):
    """An event shared by the two objects of an event arc."""

    event: str
    time: datetime | None = None
    activity: str | None = None


class EventArc(BaseModel):
    """Undirected arc between two objects that share events."""

    source: str
    target: str
    events: list[ArcEvent]
    n_events: int


class O2oArc(BaseModel):
    """Directed o2o relation."""

    source: str
    target: str
    qualifier: str | None = None


class FocalEvent(BaseModel):
    """An event of a selected object with the objects of the graph it involves."""

    event: str
    time: datetime | None = None
    activity: str | None = None
    objects: list[str]


class ObjectGraphResponse(BaseModel):
    """The object graph of the selected objects (selected objects first, then the related ones)."""

    nodes: list[ObjectGraphNode]
    event_arcs: list[EventArc]
    o2o_arcs: list[O2oArc]
    events: list[FocalEvent]
    notes: list[str]


@router.post("/{ocel_id}/instances/object-graph", operation_id="getObjectGraph")
def get_object_graph(ocel_id: str, ocel: ApiOcel, session: ApiSession, request: SelectionRequest) -> ObjectGraphResponse:
    """The object graph of the selected objects: they, every object related to them and all arcs between these."""
    graph = object_graph(_frames(session, ocel_id, ocel), request.objects)
    return ObjectGraphResponse(
        nodes=[ObjectGraphNode(**row) for row in graph.nodes.to_dicts()],
        event_arcs=[EventArc(**row) for row in graph.event_arcs.to_dicts()],
        o2o_arcs=[O2oArc(**row) for row in graph.o2o_arcs.to_dicts()],
        events=[FocalEvent(**row) for row in graph.events.to_dicts()],
        notes=graph.notes,
    )


class TraceObject(BaseModel):
    """Another object of an event: id, object type, and whether it is one of the selected objects."""

    object: str
    object_type: str | None = None
    selected: bool


class TraceEvent(BaseModel):
    """An event of a trace (see `instances.traces.ObjectTraces`)."""

    pos: int
    event: str
    time: datetime | None = None
    activity: str | None = None
    objects: list[TraceObject]


class ObjectTrace(BaseModel):
    """The trace of one selected object."""

    object: str
    object_type: str | None = None
    n_events: int
    events: list[TraceEvent]


class ObjectTracesResponse(BaseModel):
    """The object traces of the selected objects."""

    traces: list[ObjectTrace]
    notes: list[str]


@router.post("/{ocel_id}/instances/traces", operation_id="getObjectTraces")
def get_object_traces(ocel_id: str, ocel: ApiOcel, session: ApiSession, request: SelectionRequest) -> ObjectTracesResponse:
    """One trace per selected object with the other objects of every event."""
    result = object_traces(_frames(session, ocel_id, ocel), request.objects)
    by_object = {o: rows for (o,), rows in result.events.partition_by(c.OBJECT, as_dict=True, maintain_order=True).items()}
    traces = [
        ObjectTrace(
            object=total[c.OBJECT],
            object_type=total[c.OBJECT_TYPE],
            n_events=total["n_events"],
            events=[TraceEvent(**row) for row in by_object[total[c.OBJECT]].drop(c.OBJECT, c.OBJECT_TYPE).to_dicts()]
            if total[c.OBJECT] in by_object
            else [],
        )
        for total in result.totals.to_dicts()
    ]
    return ObjectTracesResponse(traces=traces, notes=result.notes)
