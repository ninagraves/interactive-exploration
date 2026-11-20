"""Column names of the frames of the interactive directly-follows graph."""

#: Event id.
EVENT = "event"
#: Timestamp of an event (completion timestamp).
TIME = "time"
#: Activity of an event.
ACTIVITY = "activity"
#: Object type of an object.
OBJECT_TYPE = "object_type"
#: Object id.
OBJECT = "object"
#: Position of an event in the trace of its object, starting at 1.
POSITION = "position"
#: Variant of an object: the activities of its trace, joined by `VARIANT_SEPARATOR`.
VARIANT = "variant"
#: Separator of the activities in a variant (a character that does not occur in activity names).
VARIANT_SEPARATOR = "␞"
#: Source activity of an arc; null = the start node of the object type.
SOURCE = "source"
#: Target activity of an arc; null = the end node of the object type.
TARGET = "target"
#: Number of times an arc is traversed (an object repeating it counts once per traversal).
COUNT = "count"
#: Number of distinct objects (or events, for activity nodes) counted.
OBJECTS = "objects"
#: Number of distinct events counted.
EVENTS = "events"

#: Columns of the OCEL tables of Ocelescope.
OCEL_EID = "ocel:eid"
OCEL_OID = "ocel:oid"
OCEL_TYPE = "ocel:type"
OCEL_ACTIVITY = "ocel:activity"
OCEL_TIMESTAMP = "ocel:timestamp"
