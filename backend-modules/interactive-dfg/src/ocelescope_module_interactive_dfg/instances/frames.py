"""The tables of a log that the page "Instances" reads (documented in `docs/pages/instances.md`)."""

from dataclasses import dataclass

import polars as pl
from ocelescope import OCEL

from ocelescope_module_interactive_dfg.dfg import columns as c

#: Columns of the o2o table.
SOURCE, TARGET, QUALIFIER = "source", "target", "qualifier"


@dataclass(frozen=True)
class InstanceFrames:
    """The tables of a log, renamed to the module's column names (eager polars frames).

    Attributes:
        e2o: Columns event, object (unique pairs; an object linked to an event with several qualifiers counts once).
        o2o: Columns source, target, qualifier (unique rows).
        objects: Columns object, object_type (every object of the log, also those without events).
        events: Columns event, time, activity.
    """

    e2o: pl.DataFrame
    o2o: pl.DataFrame
    objects: pl.DataFrame
    events: pl.DataFrame


def instance_frames(ocel: OCEL) -> InstanceFrames:
    """Read the e2o, o2o, object and event tables of a log (Ocelescope's DuckDB tables, read with polars).

    Args:
        ocel: The log.

    Returns:
        InstanceFrames: The tables.
    """
    return InstanceFrames(
        e2o=ocel.e2o.pl.select(pl.col(c.OCEL_EID).alias(c.EVENT), pl.col(c.OCEL_OID).alias(c.OBJECT)).unique().collect(),
        o2o=ocel.o2o.pl.select(
            pl.col("ocel:oid_1").alias(SOURCE), pl.col("ocel:oid_2").alias(TARGET), pl.col("ocel:qualifier").alias(QUALIFIER)
        )
        .unique()
        .collect(),
        objects=ocel.objects.pl.select(pl.col(c.OCEL_OID).alias(c.OBJECT), pl.col(c.OCEL_TYPE).alias(c.OBJECT_TYPE)).collect(),
        events=ocel.events.pl.select(
            pl.col(c.OCEL_EID).alias(c.EVENT), pl.col(c.OCEL_TIMESTAMP).alias(c.TIME), pl.col(c.OCEL_ACTIVITY).alias(c.ACTIVITY)
        ).collect(),
    )
