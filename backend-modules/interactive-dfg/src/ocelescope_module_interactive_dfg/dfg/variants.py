"""Step 3: the variant filter, per object type.

A *variant* of an object is the sequence of the activities of its (projected) trace.
The variant threshold $\\pi_{ot} \\in [0, 100]$ (percent) of an object type $ot$ keeps the most frequent variants of
$ot$ until they cover at least $\\pi_{ot}$ % of its objects: variants are ranked by their number of objects
(descending; equally frequent variants by their first occurrence in the log, i.e. the earliest first event of
their objects, Nina 2026-11-15; then by the variant itself), and a variant is kept if the objects of the
variants ranked before it cover less than $\\pi_{ot} / 100 \\cdot |O_{ot}|$.
Ties are not kept together on purpose: in logistics logs most objects often have a variant of their own (all
variants have one object), and keeping ties would then keep every variant for any threshold.
$\\pi_{ot} = 100$ keeps every variant, $\\pi_{ot} = 0$ keeps none.
Default: 80 % (`graph.DEFAULT_VARIANT_THRESHOLD`).
Only the objects of kept variants contribute to the arcs and nodes of the graph.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping

import polars as pl

from . import columns as c

#: Column: time of the first event of an object (and the earliest of a variant's objects).
FIRST_TIME = "first_time"
#: Column: rank of a variant within its object type (1 = most frequent).
RANK = "rank"


def object_variants(traces: pl.DataFrame) -> pl.DataFrame:
    """The variant of every object.

    Args:
        traces: Object traces, sorted by object and position (`traces.object_traces`).

    Returns:
        pl.DataFrame: Columns object, object_type, variant (activities joined by `VARIANT_SEPARATOR`),
        first_time (time of the object's first event).
    """
    return traces.group_by(c.OBJECT, c.OBJECT_TYPE, maintain_order=True).agg(
        pl.col(c.ACTIVITY).sort_by(c.POSITION).str.join(c.VARIANT_SEPARATOR).alias(c.VARIANT),
        pl.col(c.TIME).min().alias(FIRST_TIME),
    )


def variant_ranking(variants: pl.DataFrame) -> pl.DataFrame:
    """The variants of every object type with their number of objects, most frequent first.

    Equally frequent variants are ranked by their first occurrence in the log (the earliest first event of
    their objects; Nina, 2026-11-15), then by the variant itself.

    Args:
        variants: Columns object, object_type, variant, first_time (`object_variants`).

    Returns:
        pl.DataFrame: Columns object_type, variant, objects (count), first_time, rank (1 = most frequent,
        within the object type), covered_before (objects of the paths ranked before it within the object
        type), sorted by object type and rank.
    """
    return (
        variants.group_by(c.OBJECT_TYPE, c.VARIANT)
        .agg(pl.len().alias(c.OBJECTS), pl.col(FIRST_TIME).min())
        .sort([c.OBJECT_TYPE, c.OBJECTS, FIRST_TIME, c.VARIANT], descending=[False, True, False, False])
        .with_columns(
            pl.int_range(1, pl.len() + 1, dtype=pl.UInt32).over(c.OBJECT_TYPE).alias(RANK),
            (pl.col(c.OBJECTS).cum_sum().over(c.OBJECT_TYPE) - pl.col(c.OBJECTS)).alias("covered_before"),
        )
    )


#: Decimals of the exact needed thresholds shown in the unfold of the activity list (Nina, 2026-11-18).
EXACT_DECIMALS = 3


def activity_variant_thresholds(ranking: pl.DataFrame) -> pl.DataFrame:
    """Per object type and activity: the smallest whole variant threshold that keeps a variant containing it.

    The activity is on an included trace as soon as the best-ranked variant $v$ containing it is kept, i.e. for every
    threshold above the share of the objects of the variants ranked before $v$ (`covered_before`): the smallest whole
    percentage is that share rounded down plus 1 (Nina, 2026-11-15, for the activity list). Example: 10 pallets with
    the variants (5, 3, 1, 1 pallets); SC only in the third variant: covered before 8 -> 81 %.
    `needed_exact` is the smallest threshold with `EXACT_DECIMALS` (3) decimals (Nina, 2026-11-18, shown in the
    unfold): the share rounded down to 3 decimals plus 0.001, e.g. 2 of 3 objects before (66.666… %) -> 66.667 %,
    where `needed` says 67 %.

    Args:
        ranking: Ranked variants (`variant_ranking`).

    Returns:
        pl.DataFrame: Columns object_type, activity, needed (whole percent, 1 to 100), needed_exact (percent with 3
        decimals, 0.001 to 100).
    """
    step = 10.0**EXACT_DECIMALS
    total = pl.col(c.OBJECTS).sum().over(c.OBJECT_TYPE)
    return (
        ranking.with_columns((pl.col("covered_before") * 100 / total).alias("share"))
        .with_columns(pl.col(c.VARIANT).str.split(c.VARIANT_SEPARATOR).alias(c.ACTIVITY))
        .explode(c.ACTIVITY)
        .group_by(c.OBJECT_TYPE, c.ACTIVITY)
        .agg(pl.col("share").min())
        .select(
            c.OBJECT_TYPE,
            c.ACTIVITY,
            pl.min_horizontal(pl.col("share").round(6).floor() + 1, pl.lit(100.0)).alias("needed"),
            pl.min_horizontal(
                ((pl.col("share") * step).round(6).floor() + 1) / step, pl.lit(100.0)
            ).round(EXACT_DECIMALS).alias("needed_exact"),
        )
        .sort(c.OBJECT_TYPE, c.ACTIVITY)
    )


def kept_variants(ranking: pl.DataFrame, thresholds: Mapping[str, float]) -> pl.DataFrame:
    """The variants kept by the variant thresholds.

    Args:
        ranking: Ranked variants (`variant_ranking`).
        thresholds: Variant threshold per object type in percent (0 to 100, decimals allowed); a missing type uses
            100 (all variants).

    Returns:
        pl.DataFrame: The rows of `ranking` that are kept.
    """
    threshold = pl.col(c.OBJECT_TYPE).replace_strict(dict(thresholds), default=100.0, return_dtype=pl.Float64)
    total = pl.col(c.OBJECTS).sum().over(c.OBJECT_TYPE)
    # Compared in objects times percent (rounded against floating-point noise), so that e.g. 7 % of 100 objects
    # is exactly 7 objects.
    return ranking.filter(pl.col("covered_before") * 100 < (threshold * total).round(6))


def variant_filter(traces: pl.DataFrame, thresholds: Mapping[str, float]) -> pl.DataFrame:
    """Keep the traces of the objects whose variant is kept by the variant threshold of their object type.

    Args:
        traces: Object traces (`traces.object_traces`, projected by `projection.project_traces`).
        thresholds: Variant threshold per object type in percent; a missing type uses 100 (all variants).

    Returns:
        pl.DataFrame: The rows of `traces` of kept objects, in the same order.
    """
    variants = object_variants(traces)
    kept = kept_variants(variant_ranking(variants), thresholds).select(c.OBJECT_TYPE, c.VARIANT)
    objects = variants.join(kept, on=[c.OBJECT_TYPE, c.VARIANT], how="semi").select(c.OBJECT)
    return traces.join(objects, on=c.OBJECT, how="semi", maintain_order="left")


#: Column: the deselected activity that is added to the projection (`added_activity_thresholds`).
CANDIDATE = "candidate"
#: Separates object type and candidate in the pseudo object types of `added_activity_thresholds`.
PSEUDO_SEPARATOR = "\x1f"


def added_activity_thresholds(
    traces: pl.DataFrame, variants: pl.DataFrame, included: Mapping[str, Collection[str]]
) -> pl.DataFrame:
    """Per object type and deselected activity: the variant threshold it would need if it were selected (alone).

    For a deselected activity $a$ of a selected type $ot$, the traces are projected on the selected activities plus
    $a$; objects without $a$ keep their variant. The needed threshold is then `activity_variant_thresholds` of $a$
    on these variants (Nina, 2026-11-16, for the lower part of the activity list).
    Example: coils project on (roll, crane move); "label" occurs in 2 of 5 coils, which then get the variant
    (roll, label, crane move) of 2 objects, ranked first -> 1 %.

    Implemented with one row per (object, deselected activity of the object): every candidate becomes a pseudo
    object type "type␟activity", so the ranking runs once for all candidates.

    Args:
        traces: Object traces of the selected types before the projection.
        variants: The variants of the projected traces (`object_variants`).
        included: Selected type -> its selected activities.

    Returns:
        pl.DataFrame: Columns object_type, activity, needed, needed_exact (as `activity_variant_thresholds`); only deselected activities of
        selected types that occur in their traces.
    """
    schema = {c.OBJECT_TYPE: pl.String, c.ACTIVITY: pl.String, "needed": pl.Float64, "needed_exact": pl.Float64}
    pairs = pl.DataFrame(
        [(t, a) for t, activities in included.items() for a in activities],
        schema={c.OBJECT_TYPE: pl.String, c.ACTIVITY: pl.String},
        orient="row",
    )
    own = traces.filter(pl.col(c.OBJECT_TYPE).is_in(list(included)))
    # (object, candidate): the deselected activities each object has.
    candidates = (
        own.join(pairs, on=[c.OBJECT_TYPE, c.ACTIVITY], how="anti")
        .select(c.OBJECT, c.OBJECT_TYPE, pl.col(c.ACTIVITY).alias(CANDIDATE))
        .unique()
    )
    if candidates.is_empty():
        return pl.DataFrame(schema=schema)
    selected_rows = own.join(pairs, on=[c.OBJECT_TYPE, c.ACTIVITY], how="semi")
    # Changed objects: their selected events plus the candidate's events.
    changed_rows = pl.concat(
        [
            candidates.join(selected_rows, on=[c.OBJECT, c.OBJECT_TYPE]),
            candidates.join(own, left_on=[c.OBJECT, c.OBJECT_TYPE, CANDIDATE], right_on=[c.OBJECT, c.OBJECT_TYPE, c.ACTIVITY])
            .with_columns(pl.col(CANDIDATE).alias(c.ACTIVITY)),
        ],
        how="diagonal",
    )
    pseudo = pl.concat_str(c.OBJECT_TYPE, pl.lit(PSEUDO_SEPARATOR), CANDIDATE)
    changed = object_variants(changed_rows.with_columns(pseudo.alias(c.OBJECT_TYPE)).sort(c.OBJECT, c.POSITION))
    # Unchanged objects keep their variant, once per candidate of their type.
    per_type = candidates.select(c.OBJECT_TYPE, CANDIDATE).unique()
    unchanged = (
        variants.join(per_type, on=c.OBJECT_TYPE)
        .join(candidates, on=[c.OBJECT, c.OBJECT_TYPE, CANDIDATE], how="anti")
        .with_columns(pseudo.alias(c.OBJECT_TYPE))
        .drop(CANDIDATE)
    )
    ranking = variant_ranking(pl.concat([changed, unchanged.select(changed.columns)]))
    split = pl.col(c.OBJECT_TYPE).str.split_exact(PSEUDO_SEPARATOR, 1)
    return (
        activity_variant_thresholds(ranking)
        .with_columns(split.struct.field("field_0").alias("_type"), split.struct.field("field_1").alias(CANDIDATE))
        .filter(pl.col(c.ACTIVITY) == pl.col(CANDIDATE))
        .select(
            pl.col("_type").alias(c.OBJECT_TYPE),
            c.ACTIVITY,
            pl.col("needed").cast(pl.Float64),
            pl.col("needed_exact").cast(pl.Float64),
        )
        .sort(c.OBJECT_TYPE, c.ACTIVITY)
    )
