import polars as pl

# Full ancestry, broad -> granular. Path matching uses prefixes of this list.
LEVEL_ORDER = ["level1", "level2", "level3", "level4", "level5", "level6", "level7"]
# Fallback granularities, most granular first; never coarser than level4.
GRANULARITIES = ["level7", "level6", "level5", "level4"]


def reallocate_inactive(lf_data, lf_status, *, active_value="active", drop_reallocated=False):
    out_cols = lf_data.collect_schema().names() + ["status"]

    lf = (
        lf_data
        .join(lf_status, on=["entity", "code"], how="left")
        .with_columns(pl.col("status").fill_null("inactive"))
    )
    active = lf.filter(pl.col("status") == active_value)
    inactive = lf.filter(pl.col("status") != active_value)

    backup = inactive
    cand_cols = []
    for g in GRANULARITIES:
        depth = LEVEL_ORDER.index(g) + 1            # level7 -> 7 cols, level4 -> 4 cols
        path_keys = ["entity"] + LEVEL_ORDER[:depth]  # match on full ancestry, not just the value
        col = f"backup_{g}"
        cand = (
            active
            .group_by(path_keys)
            .agg(
                pl.col("code")
                  .sort_by("amount", descending=True)  # tie-break: active code with most amount
                  .first()
                  .alias(col)
            )
        )
        backup = backup.join(cand, on=path_keys, how="left")
        cand_cols.append(col)

    backup = backup.with_columns(
        pl.coalesce([pl.col(c) for c in cand_cols]).alias("backup_code"),
        pl.coalesce([
            pl.when(pl.col(c).is_not_null()).then(pl.lit(g))
            for c, g in zip(cand_cols, GRANULARITIES)
        ]).alias("matched_level"),
    )

    audit = backup.select(
        "entity", "code",
        pl.col("amount").alias("original_amount"),
        "status", "matched_level", "backup_code",
    )

    redirected = (
        backup
        .filter(pl.col("backup_code").is_not_null())
        .group_by(["entity", "backup_code"])
        .agg(pl.col("amount").sum().alias("_added"))
        .rename({"backup_code": "code"})
    )
    active_out = (
        active
        .join(redirected, on=["entity", "code"], how="left")
        .with_columns((pl.col("amount") + pl.col("_added").fill_null(0)).alias("amount"))
        .select(out_cols)
    )

    inactive_out = backup.with_columns(
        pl.when(pl.col("backup_code").is_not_null()).then(pl.lit(0))
          .otherwise(pl.col("amount")).alias("amount")
    )
    if drop_reallocated:
        inactive_out = inactive_out.filter(pl.col("backup_code").is_null())
    inactive_out = inactive_out.select(out_cols)

    return pl.concat([active_out, inactive_out]), audit
